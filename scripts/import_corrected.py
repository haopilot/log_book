#!/usr/bin/env python3
"""
Import date-corrected OCR entries into the SQLite logbook database.

Reads _corrected_entries.json (output of fix_dates.py) and loads all entries
into the logbook SQLite database, stripping internal metadata fields.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.logbook_entry import LogbookEntry
from services.sqlite_storage import SQLiteStorage

CORRECTED_ENTRIES_PATH = Path(__file__).parent / "ocr_results" / "_corrected_entries.json"
DB_PATH = Path(__file__).parent.parent / "logbook.db"


def main():
    # Load corrected entries
    with open(CORRECTED_ENTRIES_PATH) as f:
        entries_data = json.load(f)

    print(f"Loaded {len(entries_data)} corrected entries from {CORRECTED_ENTRIES_PATH.name}")

    # Initialize storage
    storage = SQLiteStorage(db_path=str(DB_PATH))
    existing_count = storage.count()
    print(f"Current database has {existing_count} entries")

    if existing_count > 0:
        print("\nWARNING: Database already has entries!")
        resp = input("Clear existing entries and reimport? (y/N): ").strip().lower()
        if resp != 'y':
            print("Aborted.")
            return
        storage.clear_all()
        print("Cleared existing entries.")

    # Convert to LogbookEntry objects
    logbook_entries = []
    for entry_data in entries_data:
        # Strip internal metadata fields
        entry_data.pop("_original_date", None)
        entry_data.pop("_page", None)

        entry = LogbookEntry(
            date=entry_data.get("date", ""),
            aircraft_model=entry_data.get("aircraft_model", ""),
            aircraft_ident=entry_data.get("aircraft_ident", "").upper(),
            route_from=entry_data.get("route_from", "").upper(),
            route_to=entry_data.get("route_to", "").upper(),
            route_via=entry_data.get("route_via", "").upper(),
            sel=float(entry_data.get("sel") or 0),
            mel=float(entry_data.get("mel") or 0),
            day=float(entry_data.get("day") or 0),
            night=float(entry_data.get("night") or 0),
            cross_country=float(entry_data.get("cross_country") or 0),
            actual_inst=float(entry_data.get("actual_inst") or 0),
            simulated_inst=float(entry_data.get("simulated_inst") or 0),
            num_inst_app=int(entry_data.get("num_inst_app") or 0),
            landings_day=int(entry_data.get("landings_day") or 0),
            landings_night=int(entry_data.get("landings_night") or 0),
            pic=float(entry_data.get("pic") or 0),
            sic=float(entry_data.get("sic") or 0),
            dual_recd=float(entry_data.get("dual_recd") or 0),
            dual_given=float(entry_data.get("dual_given") or 0),
            solo=float(entry_data.get("solo") or 0),
            sim=float(entry_data.get("sim") or 0),
            total_duration=float(entry_data.get("total_duration") or 0),
            remarks=entry_data.get("remarks", ""),
            reviewed=False,  # Mark as needing review
        )
        logbook_entries.append(entry)

    # Bulk insert
    count = storage.bulk_insert(logbook_entries)
    print(f"\nImported {count} entries into {DB_PATH.name}")

    # Verify
    final_count = storage.count()
    totals = storage.get_totals()
    print(f"Database now has {final_count} entries")
    print(f"Total flight time: {totals['total_duration']:.1f}h")
    print(f"Total PIC: {totals['pic']:.1f}h")
    print(f"Total dual received: {totals['dual_recd']:.1f}h")
    print(f"Flights: {totals['flights']}")


if __name__ == "__main__":
    main()
