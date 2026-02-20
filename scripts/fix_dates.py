#!/usr/bin/env python3
"""
Fix logbook dates using two strategies:

1. MAIN CHAIN pages: explicitly identified by tracing the totals_to_date →
   amt_forwarded chain. These represent the main SEL career section (0→1175h).
   For these, use cumulative hours → year calibration.

2. SECONDARY SECTION pages: everything else (MEL, instrument, turboprop, etc.)
   with their own running totals. For early secondary pages (fwd < 30h), hours→year
   still works. For later ones, trust the OCR year.

Within all pages: conservative year rollover (only a single Dec→Jan transition).
"""

import json
import re
from collections import Counter
from pathlib import Path

OCR_RESULTS_DIR = Path(__file__).parent / "ocr_results"

# Main chain pages (traced by following totals_to_date → amt_forwarded)
# These are the primary SEL section, going from 0 to ~1175 career hours.
MAIN_CHAIN_PAGES = {
    "IMG_5045.JPEG",  # fwd=0.0    → total=22.3    (2003)
    "IMG_5046.JPEG",  # fwd=22.3   → total=41.2    (2004)
    "IMG_5047.JPEG",  # fwd=41.2   → total=59.9    (2004)
    "IMG_5048.JPEG",  # fwd=59.9   → total=82.9    (2004)
    "IMG_5049.JPEG",  # fwd=85.3   → total=103.2   (2005)
    "IMG_5050.JPEG",  # fwd=101.7  → total=123.9   (2005)
    "IMG_5051.JPEG",  # fwd=123.9  → total=160.2   (2005)
    "IMG_5052.JPEG",  # fwd=160.2  → total=187.2   (2006)
    "IMG_5056.JPEG",  # fwd=200.7  → total=213.5   (2006)
    "IMG_5057.JPEG",  # fwd=218.9  → total=245.1   (2006-2007)
    "IMG_5058.JPEG",  # fwd=245.1  → total=261.9   (2007)
    "IMG_5060.JPEG",  # fwd=277.2  → total=297.6   (2007)
    "IMG_5061.JPEG",  # fwd=297.6  → total=313.5   (2007-2008)
    "IMG_5062.JPEG",  # fwd=313.5  → total=338.6   (2008)
    "IMG_5064.JPEG",  # fwd=358.6  → total=407.5   (2008-2009)
    "IMG_5066.JPEG",  # fwd=~407.5 → total=~419.3  (2009) [OCR garbled]
    "IMG_5065.JPEG",  # fwd=457.5  → total=478.3   (2009-2010)
    "IMG_5069.JPEG",  # fwd=478.3  → total=506.7   (2010)
    "IMG_5070.JPEG",  # fwd=506.7  → total=538.0   (2010-2011)
    "IMG_5071.JPEG",  # fwd=538.0  → total=556.9   (2011-2012)
    "IMG_5072.JPEG",  # fwd=556.9  → total=594.4   (2012)
    "IMG_5073.JPEG",  # fwd=542.5  → total=577.6   (2011-2012) [parallel branch]
    "IMG_5074.JPEG",  # fwd=629.5  → total=686.3   (2014)
    "IMG_5075.JPEG",  # fwd=686.3  → total=764.1   (2015-2017)
    "IMG_5077.JPEG",  # fwd=770.0  → total=842.3   (2017)
    "IMG_5078.JPEG",  # fwd=894.3  → total=944.8   (2020)
    "IMG_5079.JPEG",  # fwd=892.8  → total=936.1   (2020)
    "IMG_5080.JPEG",  # fwd=936.1  → total=975.0   (2021)
    # Gap from 975 to ~1100 (missing pages)
    "IMG_5085.JPEG",  # fwd=1099.9 → total=1107.3  (2024)
    "IMG_5084.JPEG",  # fwd=1126.5 → total=1152.5  (2024)
    "IMG_5087.JPEG",  # fwd=1126.5 → total=1137.5  (2024)
    "IMG_5088.JPEG",  # fwd=1137.5 → total=1161.2  (2024)
    "IMG_5086.JPEG",  # fwd=1159.9 → total=1174.1  (2025)
}

# Early secondary pages where hours→year still works (section started with career)
EARLY_SECONDARY_PAGES = {
    "IMG_5054.JPEG",  # fwd=10.6   MEL section start (2003-2004)
    "IMG_5055.JPEG",  # fwd=27.3   MEL section (2004)
}

# All other pages are later secondary sections → trust OCR year
# 5053, 5059, 5063, 5067, 5068, 5076, 5081, 5082, 5083, 5089

# Manual overrides for known OCR errors in page totals
PAGE_TOTAL_OVERRIDES = {
    "IMG_5066.JPEG": {"amt_forwarded": 407.5, "totals_to_date": 419.3},
}

# Career calibration: (cumulative_hours, year)
HOUR_YEAR_CALIBRATION = [
    (0, 2003.5),       # Jun 2003 - start of flying
    (22.3, 2004.0),    # Page 5045 end - Jan 2004
    (41.2, 2004.3),    # Page 5046 end - May 2004
    (59.9, 2004.7),    # Page 5047 end - Sep 2004
    (82.9, 2004.9),    # Page 5048 end - Nov 2004
    (103, 2005.1),     # ~Feb 2005
    (124, 2005.5),     # ~mid 2005
    (160, 2005.8),     # ~late 2005
    (187, 2006.0),     # ~2006
    (250, 2007.0),     # ~2007
    (340, 2008.0),     # ~2008
    (410, 2009.0),     # ~2009
    (480, 2010.0),     # ~2010
    (560, 2012.0),     # ~2012 (rate slows)
    (630, 2014.0),     # ~2014
    (690, 2015.0),     # ~2015
    (770, 2017.0),     # ~2017
    (840, 2019.0),     # ~2019
    (940, 2021.0),     # ~2021
    (975, 2022.0),     # ~2022
    (1050, 2023.0),    # ~2023
    (1110, 2024.0),    # ~2024
    (1175, 2025.0),    # ~2025
]


def hours_to_year(hours):
    """Estimate calendar year from cumulative flight hours."""
    if hours <= HOUR_YEAR_CALIBRATION[0][0]:
        return HOUR_YEAR_CALIBRATION[0][1]
    if hours >= HOUR_YEAR_CALIBRATION[-1][0]:
        return HOUR_YEAR_CALIBRATION[-1][1]
    for i in range(len(HOUR_YEAR_CALIBRATION) - 1):
        h0, y0 = HOUR_YEAR_CALIBRATION[i]
        h1, y1 = HOUR_YEAR_CALIBRATION[i + 1]
        if h0 <= hours <= h1:
            frac = (hours - h0) / (h1 - h0) if h1 != h0 else 0
            return y0 + frac * (y1 - y0)
    return HOUR_YEAR_CALIBRATION[-1][1]


def get_page_fwd(page, page_totals):
    """Get amt_forwarded with overrides for known OCR errors."""
    if page in PAGE_TOTAL_OVERRIDES and "amt_forwarded" in PAGE_TOTAL_OVERRIDES[page]:
        return PAGE_TOTAL_OVERRIDES[page]["amt_forwarded"]
    fwd = page_totals[page]["amt_forwarded"]
    if fwd > 10000:
        return None
    return fwd


def get_ocr_year(entries):
    """Get the most common OCR year from entries on a page."""
    years = []
    for e in entries:
        m = re.match(r'\d{1,2}/\d{1,2}/(\d{4})', e.get("date", ""))
        if m:
            years.append(int(m.group(1)))
    if not years:
        return None
    return Counter(years).most_common(1)[0][0]


def compute_base_year(page, page_totals, entries, method):
    """Compute the base year for a page using the specified method."""
    if method == "hours":
        fwd = get_page_fwd(page, page_totals)
        if fwd is None:
            fwd = 500
        est = hours_to_year(fwd)
        base = int(est)

        # Refine: if fractional > 0.7 and first month is Jan-Mar, bump year
        first_month = None
        for e in entries:
            m = re.match(r'(\d{1,2})/\d{1,2}/\d{4}', e.get("date", ""))
            if m:
                first_month = int(m.group(1))
                break
        frac = est - base
        if first_month and first_month <= 3 and frac > 0.7:
            base += 1

        return base, est

    else:  # method == "ocr"
        ocr_year = get_ocr_year(entries)
        if ocr_year:
            return ocr_year, float(ocr_year)
        # Fallback
        fwd = get_page_fwd(page, page_totals) or 500
        est = hours_to_year(fwd)
        return int(est), est


def fix_page_dates(entries, base_year, page_img):
    """
    Fix dates for entries on a page with conservative year rollover.
    Only allows a single Dec→Jan transition per page.
    """
    entry_months = []
    for e in entries:
        m = re.match(r'(\d{1,2})/\d{1,2}/\d{4}', e.get("date", ""))
        entry_months.append(int(m.group(1)) if m else None)

    # Find a single Dec→Jan rollover point
    rollover_idx = None
    valid = [(i, m) for i, m in enumerate(entry_months) if m is not None]

    for j in range(len(valid) - 1):
        idx_a, month_a = valid[j]
        idx_b, month_b = valid[j + 1]
        if month_a >= 10 and month_b <= 3:
            if rollover_idx is None:
                rollover_idx = idx_b
            else:
                # Multiple rollovers → don't do any
                rollover_idx = None
                break

    result = []
    for idx, entry in enumerate(entries):
        date_str = entry.get("date", "")
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if not match:
            entry["_page"] = page_img
            result.append(entry)
            continue

        month = int(match.group(1))
        day = int(match.group(2))

        if rollover_idx is not None and idx >= rollover_idx:
            year = base_year + 1
        else:
            year = base_year

        entry["_original_date"] = date_str
        entry["date"] = f"{month:02d}/{day:02d}/{year}"
        entry["_page"] = page_img
        result.append(entry)

    return result


def load_page_totals():
    with open(OCR_RESULTS_DIR / "_page_totals.json") as f:
        return json.load(f)


def load_page_entries(img_name):
    json_path = OCR_RESULTS_DIR / f"{img_name.replace('.JPEG', '.json')}"
    if not json_path.exists():
        return []
    with open(json_path) as f:
        data = json.load(f)
    return data.get("processed_entries") or data.get("raw_entries", [])


def sort_entries_by_date(entries):
    """Sort entries chronologically by date."""
    def date_key(entry):
        m = re.match(r'(\d{2})/(\d{2})/(\d{4})', entry.get("date", ""))
        if m:
            return (int(m.group(3)), int(m.group(1)), int(m.group(2)))
        return (9999, 99, 99)
    return sorted(entries, key=date_key)


def main():
    page_totals = load_page_totals()

    print("=" * 70)
    print("Fixing logbook dates (main chain + secondary sections)")
    print("=" * 70)

    # ─── Classify pages ───────────────────────────────────────────────
    all_pages = set(page_totals.keys())
    secondary_ocr = all_pages - MAIN_CHAIN_PAGES - EARLY_SECONDARY_PAGES

    print(f"\nMain chain:        {len(MAIN_CHAIN_PAGES)} pages (hours→year)")
    print(f"Early secondary:   {len(EARLY_SECONDARY_PAGES)} pages (hours→year)")
    print(f"Later secondary:   {len(secondary_ocr)} pages (trust OCR year)")
    for p in sorted(secondary_ocr):
        num = p.replace("IMG_", "").replace(".JPEG", "")
        fwd = get_page_fwd(p, page_totals) or 0
        entries = load_page_entries(p)
        ocr = get_ocr_year(entries)
        print(f"  {num}: fwd={fwd:7.1f}h  OCR year={ocr}")

    # ─── Process all pages ────────────────────────────────────────────
    print(f"\n{'Page':<8} {'Fwd':>7} {'~Year':>6} {'OCR':>5} {'Method':>8} {'Base':>5} {'#Ent':>5}")
    print("-" * 55)

    all_entries = []

    # Sort pages by fwd hours for display
    pages_with_fwd = []
    for page in page_totals:
        fwd = get_page_fwd(page, page_totals)
        pages_with_fwd.append((page, fwd if fwd is not None else 500))
    pages_with_fwd.sort(key=lambda x: x[1])

    for page_img, fwd in pages_with_fwd:
        entries = load_page_entries(page_img)
        if not entries:
            continue

        if page_img in MAIN_CHAIN_PAGES or page_img in EARLY_SECONDARY_PAGES:
            method = "hours"
        else:
            method = "ocr"

        base_year, est = compute_base_year(page_img, page_totals, entries, method)
        ocr_year = get_ocr_year(entries)
        page_num = page_img.replace("IMG_", "").replace(".JPEG", "")

        print(f"  {page_num:<6} {fwd:7.1f} {est:6.1f} {ocr_year or '?':>5} "
              f"{method:>8} {base_year:>5} {len(entries):>5}")

        fixed = fix_page_dates(entries, base_year, page_img)
        all_entries.extend(fixed)

    # Sort chronologically
    all_entries = sort_entries_by_date(all_entries)

    # ─── Summary ──────────────────────────────────────────────────────
    print(f"\nTotal entries: {len(all_entries)}")

    year_counts = {}
    for entry in all_entries:
        m = re.match(r'\d{2}/\d{2}/(\d{4})', entry.get("date", ""))
        if m:
            yr = m.group(1)
            year_counts[yr] = year_counts.get(yr, 0) + 1

    print("\nYear distribution:")
    for yr in sorted(year_counts.keys()):
        print(f"  {yr}: {year_counts[yr]} entries")

    corrections = 0
    for entry in all_entries:
        orig = entry.get("_original_date", "")
        current = entry.get("date", "")
        if orig and current and orig != current:
            corrections += 1
    print(f"\nTotal corrections: {corrections}")

    # ─── Save JSON ────────────────────────────────────────────────────
    output_path = OCR_RESULTS_DIR / "_corrected_entries.json"
    with open(output_path, 'w') as f:
        json.dump(all_entries, f, indent=2)
    print(f"\nSaved corrected entries to {output_path}")

    # ─── Save readable text ──────────────────────────────────────────
    txt_path = OCR_RESULTS_DIR / "corrected_entries.txt"
    with open(txt_path, 'w') as f:
        for i, entry in enumerate(all_entries, 1):
            date = entry.get("date", "?")
            model = entry.get("aircraft_model", "?")
            ident = entry.get("aircraft_ident", "?")
            route_from = entry.get("route_from", "?")
            route_to = entry.get("route_to", "?")
            dur = entry.get("total_duration", 0)
            orig = entry.get("_original_date", "")
            page = entry.get("_page", "?").replace("IMG_", "").replace(".JPEG", "")
            flag = " ***" if orig and orig != date else ""
            route = f"{route_from}-{route_to}"
            f.write(f"{i:4d}. {date}  {model:<9s} {ident:<9s} "
                    f"{route:<25s} {dur:5.1f}h [p{page}]{flag}\n")

    print(f"Saved readable text to {txt_path}")


if __name__ == "__main__":
    main()
