#!/usr/bin/env python3
"""
Re-process saved OCR results through the improved post-processing pipeline.

Uses the raw_entries saved from batch_ocr_test.py, runs them through the
updated pipeline, and compares before/after.

Usage: cd /home/hcreal/log_book && venv/bin/python scripts/reprocess_ocr.py
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ocr_service import LogbookOCRService

import functools
print = functools.partial(print, flush=True)


def reprocess_all(results_dir: str):
    """Re-process all saved raw entries through the updated pipeline."""
    results_dir = Path(results_dir)
    ocr = LogbookOCRService()

    all_old_entries = []
    all_new_entries = []
    changes = []

    json_files = sorted(results_dir.glob("IMG_*.json"))
    print(f"Found {len(json_files)} result files to reprocess")

    for path in json_files:
        with open(path) as f:
            data = json.load(f)

        raw_entries = data.get('raw_entries', [])
        old_processed = data.get('processed_entries', [])

        if not raw_entries:
            continue

        # Run through updated pipeline
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

        all_old_entries.extend(old_processed)
        all_new_entries.extend(filtered)

        # Track changes
        for old_e, new_e in zip(old_processed, filtered):
            for field in ['aircraft_model', 'aircraft_ident', 'route_from', 'route_to', 'route_via', 'remarks']:
                old_val = old_e.get(field, '')
                new_val = new_e.get(field, '')
                if old_val != new_val:
                    changes.append({
                        'photo': path.name,
                        'date': new_e.get('date', ''),
                        'field': field,
                        'old': old_val,
                        'new': new_val,
                    })

        # Save updated results
        data['processed_entries'] = filtered
        data['processed_entry_count'] = len(filtered)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    # Print change summary
    print(f"\n{'='*60}")
    print("REPROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Old total entries: {len(all_old_entries)}")
    print(f"New total entries: {len(all_new_entries)}")
    print(f"Total field changes: {len(changes)}")

    # Group changes by field
    field_counts = Counter(c['field'] for c in changes)
    print(f"\nChanges by field:")
    for field, count in field_counts.most_common():
        print(f"  {field}: {count}")

    # Show specific changes
    for field in ['aircraft_model', 'route_via', 'remarks']:
        field_changes = [c for c in changes if c['field'] == field]
        if field_changes:
            print(f"\n{field.upper()} changes ({len(field_changes)}):")
            for c in field_changes[:30]:
                old_display = c['old'][:50] if c['old'] else '(empty)'
                new_display = c['new'][:50] if c['new'] else '(empty)'
                print(f"  [{c['date']}] '{old_display}' → '{new_display}'")
            if len(field_changes) > 30:
                print(f"  ... and {len(field_changes) - 30} more")

    # Aggregate analysis of new results
    print(f"\n{'='*60}")
    print("UPDATED AGGREGATE ANALYSIS")
    print(f"{'='*60}")

    # Aircraft models
    models = Counter(e.get('aircraft_model', '') for e in all_new_entries)
    print(f"\nAircraft models ({len(models)} unique):")
    for model, count in models.most_common():
        print(f"  {model or '(empty)'}: {count}")

    # Multi-leg routes
    multi_leg = [e for e in all_new_entries if e.get('route_via')]
    print(f"\nMulti-leg routes: {len(multi_leg)} entries")
    route_counts = Counter(e['route_via'] for e in multi_leg)
    for route, count in route_counts.most_common(20):
        print(f"  {route}: {count}")

    # Entries with empty remarks (cleaned)
    empty_remarks = sum(1 for e in all_new_entries if not e.get('remarks'))
    total = len(all_new_entries)
    print(f"\nRemarks: {total - empty_remarks} with text, {empty_remarks} empty")

    # Generate updated all_entries.txt
    output_path = results_dir / "all_entries.txt"
    with open(output_path, 'w') as f:
        for i, entry in enumerate(all_new_entries, 1):
            route = entry.get('route_via') or f"{entry.get('route_from', '')}-{entry.get('route_to', '')}"
            f.write(f"{i:3d}. {entry.get('date', ''):12s} "
                    f"{entry.get('aircraft_model', ''):8s} "
                    f"{entry.get('aircraft_ident', ''):8s} "
                    f"{route:20s} "
                    f"{entry.get('total_duration', 0):5.1f}h "
                    f"{entry.get('remarks', '')}\n")
    print(f"\nUpdated all_entries.txt with {len(all_new_entries)} entries")


if __name__ == "__main__":
    results_dir = str(Path(__file__).parent / "ocr_results")
    reprocess_all(results_dir)
