#!/usr/bin/env python3
"""
Batch OCR test: process all logbook photos and save raw + processed results.

Usage: cd /home/hcreal/log_book && venv/bin/python scripts/batch_ocr_test.py
"""

import base64
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

# Set credentials before any Google imports
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(Path(__file__).parent.parent / 'service-account.json')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ocr_service import LogbookOCRService

# Force unbuffered output
import functools
print = functools.partial(print, flush=True)


def extract_raw_and_processed(ocr: LogbookOCRService, image_path: str):
    """Call Gemini and return both raw entries and post-processed entries."""
    import google.generativeai as genai

    ocr._init_gemini()
    if not ocr._gemini_initialized:
        raise RuntimeError("Gemini not initialized - check credentials")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    image_part = {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}

    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(
        [ocr.EXTRACTION_PROMPT, image_part],
        generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=8192),
    )

    response_text = response.text.strip()
    if response_text.startswith("```"):
        lines = response_text.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        response_text = '\n'.join(lines)

    parsed = json.loads(response_text)

    if isinstance(parsed, dict):
        expected_rows = parsed.get('total_rows_visible', 0)
        raw_entries = parsed.get('entries', [])
    elif isinstance(parsed, list):
        raw_entries = parsed
        expected_rows = len(raw_entries)
    else:
        return [], [], 0

    # Save raw entries (deep copy before any mutation)
    raw_copy = json.loads(json.dumps(raw_entries))

    # Run full post-processing pipeline
    normalized = [ocr._normalize_entry(e) for e in raw_entries]
    filtered = [e for e in normalized if ocr._is_flight_entry(e)]
    filtered = ocr._normalize_dates(filtered)
    filtered = ocr._fix_aircraft_idents(filtered, None)
    filtered = ocr._fix_aircraft_models(filtered, None)
    filtered = ocr._fix_airport_codes(filtered, None)
    filtered = ocr._fix_type_per_registration(filtered)
    filtered = ocr._migrate_ftd_time(filtered)
    filtered = ocr._extract_multi_leg_routes(filtered)
    filtered = ocr._fix_airport_code_in_route_via(filtered)
    filtered = ocr._clean_remarks(filtered)

    return raw_copy, filtered, expected_rows


def process_all_photos(photo_dir: str, output_dir: str):
    """Process all photos and save results."""
    photos = sorted(Path(photo_dir).glob("*.JPEG"))
    if not photos:
        photos = sorted(Path(photo_dir).glob("*.jpeg"))
    if not photos:
        photos = sorted(Path(photo_dir).glob("*.jpg"))

    print(f"Found {len(photos)} photos to process")

    ocr = LogbookOCRService()
    all_results = {}
    summary = {
        "total_photos": len(photos),
        "total_raw_entries": 0,
        "total_processed_entries": 0,
        "total_filtered_out": 0,
        "errors": [],
        "per_photo": {},
    }

    for i, photo in enumerate(photos):
        name = photo.stem
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(photos)}] Processing {photo.name}...")
        print(f"{'='*60}")

        try:
            start = time.time()
            raw, processed, expected_rows = extract_raw_and_processed(ocr, str(photo))
            elapsed = time.time() - start

            result = {
                "photo": photo.name,
                "expected_rows": expected_rows,
                "raw_entry_count": len(raw),
                "processed_entry_count": len(processed),
                "elapsed_seconds": round(elapsed, 1),
                "raw_entries": raw,
                "processed_entries": processed,
            }

            # Save per-photo result
            result_path = Path(output_dir) / f"{name}.json"
            with open(result_path, 'w') as f:
                json.dump(result, f, indent=2)

            summary["total_raw_entries"] += len(raw)
            summary["total_processed_entries"] += len(processed)
            summary["total_filtered_out"] += len(raw) - len(processed)
            summary["per_photo"][photo.name] = {
                "expected_rows": expected_rows,
                "raw": len(raw),
                "processed": len(processed),
                "filtered": len(raw) - len(processed),
                "elapsed": round(elapsed, 1),
            }

            all_results[photo.name] = result
            print(f"  -> {len(raw)} raw entries, {len(processed)} after processing ({elapsed:.1f}s)")

            # Rate limiting for Gemini API
            if i < len(photos) - 1:
                time.sleep(2)

        except Exception as e:
            print(f"  ERROR: {e}")
            summary["errors"].append({"photo": photo.name, "error": str(e)})
            import traceback
            traceback.print_exc()
            time.sleep(5)

    # Save summary
    summary_path = Path(output_dir) / "_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Photos processed: {summary['total_photos']}")
    print(f"Total raw entries: {summary['total_raw_entries']}")
    print(f"Total processed entries: {summary['total_processed_entries']}")
    print(f"Total filtered out: {summary['total_filtered_out']}")
    print(f"Errors: {len(summary['errors'])}")

    if summary['errors']:
        print("\nErrors:")
        for err in summary['errors']:
            print(f"  {err['photo']}: {err['error']}")

    # Aggregate analysis
    print(f"\n{'='*60}")
    print("AGGREGATE ANALYSIS")
    print(f"{'='*60}")

    all_entries = []
    for name, result in all_results.items():
        for entry in result['processed_entries']:
            entry['_source_photo'] = name
            all_entries.append(entry)

    # Aircraft models
    models = Counter(e.get('aircraft_model', '') for e in all_entries)
    print(f"\nAircraft models ({len(models)} unique):")
    for model, count in models.most_common():
        print(f"  {model or '(empty)'}: {count}")

    # Aircraft idents
    idents = Counter(e.get('aircraft_ident', '') for e in all_entries)
    print(f"\nAircraft idents ({len(idents)} unique):")
    for ident, count in idents.most_common(30):
        print(f"  {ident or '(empty)'}: {count}")

    # Airports
    airports = Counter()
    for e in all_entries:
        if e.get('route_from'):
            airports[e['route_from']] += 1
        if e.get('route_to'):
            airports[e['route_to']] += 1
    print(f"\nAirports ({len(airports)} unique):")
    for apt, count in airports.most_common():
        print(f"  {apt or '(empty)'}: {count}")

    # Date ranges
    dates = [e.get('date', '') for e in all_entries if e.get('date')]
    if dates:
        print(f"\nDate range: {min(dates)} to {max(dates)}")
        bad_dates = [d for d in dates if not re.match(r'^\d{2}/\d{2}/\d{4}$', d)]
        if bad_dates:
            print(f"  Bad date formats: {bad_dates}")

    # Missing fields
    missing = Counter()
    for e in all_entries:
        if not e.get('date'):
            missing['date'] += 1
        if not e.get('aircraft_model'):
            missing['aircraft_model'] += 1
        if not e.get('aircraft_ident'):
            missing['aircraft_ident'] += 1
        if not e.get('route_from'):
            missing['route_from'] += 1
        if not e.get('route_to'):
            missing['route_to'] += 1
        if not e.get('total_duration'):
            missing['total_duration'] += 1
    if missing:
        print(f"\nMissing fields:")
        for field, count in missing.most_common():
            print(f"  {field}: {count} entries")

    return summary


if __name__ == "__main__":
    photo_dir = os.path.expanduser("~/Downloads/logbook_photos")
    output_dir = str(Path(__file__).parent / "ocr_results")
    os.makedirs(output_dir, exist_ok=True)

    process_all_photos(photo_dir, output_dir)
