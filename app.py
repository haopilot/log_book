"""
Pilot Logbook - Web Application

A web-based pilot logbook using ASA Standard format.
Uses SQLite for local storage with Google Sheets as backup.
"""

import os
from datetime import datetime

from config import Config
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from models.logbook_entry import Logbook, LogbookEntry
from services.sqlite_storage import SQLiteStorage
from services.sync_service import SyncService

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY


def init_storage():
    """Initialize SQLite storage and sync from Google Sheets."""
    storage = SQLiteStorage(db_path=Config.SQLITE_DB_PATH)
    sync_service = SyncService(storage)

    # On startup, load from Google Sheets (the authoritative source on Render.com)
    if Config.GOOGLE_SHEETS_ID:
        result = sync_service.load_from_sheets()
        if result.get("success"):
            print(f"✓ Loaded {result.get('count', 0)} entries from Google Sheets into SQLite")
        else:
            error_msg = result.get("error", "Unknown error")
            print(f"Warning: Could not load from Sheets: {error_msg}")
            # Continue with empty or existing SQLite data
    else:
        print("Google Sheets not configured, using local SQLite only")

    return storage, sync_service


# Global storage instances
storage, sync_service = init_storage()


def save_to_sheets():
    """Sync local SQLite data to Google Sheets (backup)."""
    if Config.GOOGLE_SHEETS_ID:
        result = sync_service.export_to_sheets()
        if result.get("success"):
            print(f"✓ Synced to Google Sheets")
        else:
            error_msg = result.get("error", "Unknown error")
            print(f"Warning: Sheets sync failed: {error_msg}")


def parse_float(value, default=0.0):
    """Safely parse a float value."""
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        return default


def parse_int(value, default=0):
    """Safely parse an int value."""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


@app.route("/")
def index():
    """Main logbook view - summary list."""
    entries = storage.get_all_entries(sort_by_date=True)
    totals = storage.get_totals()
    return render_template(
        "logbook.html",
        entries=entries,
        totals=totals,
    )


@app.route("/entry/new")
def new_entry():
    """New flight entry page with defaults."""
    defaults = {
        "id": "",
        "date": datetime.now().strftime("%m/%d/%Y"),
        "aircraft_model": Config.DEFAULT_AIRCRAFT_TYPE,
        "aircraft_ident": Config.DEFAULT_TAIL_NUMBER,
        "route_from": Config.DEFAULT_DEPARTURE,
        "route_to": "",
        "sel": "",
        "mel": "",
        "day": "",
        "night": "",
        "cross_country": "",
        "actual_inst": "",
        "simulated_inst": "",
        "num_inst_app": "",
        "landings_day": "",
        "landings_night": "",
        "pic": "",
        "sic": "",
        "dual_recd": "",
        "dual_given": "",
        "solo": "",
        "total_duration": "",
        "remarks": "",
    }
    return render_template("entry.html", entry=defaults, is_new=True)


@app.route("/entry/<entry_id>")
def view_entry(entry_id):
    """View/edit a specific flight entry."""
    entry = storage.get_entry(entry_id)
    if not entry:
        return redirect(url_for("index"))
    return render_template("entry.html", entry=entry.to_dict(), is_new=False)


@app.route("/api/entries", methods=["GET"])
def get_entries():
    """Get all logbook entries."""
    entries = storage.get_all_entries(sort_by_date=True)
    return jsonify([e.to_dict() for e in entries])


@app.route("/api/entries/<entry_id>", methods=["GET"])
def get_entry(entry_id):
    """Get a specific logbook entry."""
    entry = storage.get_entry(entry_id)
    if entry:
        return jsonify(entry.to_dict())
    return jsonify({"error": "Entry not found"}), 404


@app.route("/api/entries", methods=["POST"])
def create_entry():
    """Create a new logbook entry."""
    data = request.json
    entry = LogbookEntry(
        date=data.get("date", ""),
        aircraft_model=data.get("aircraft_model", ""),
        aircraft_ident=data.get("aircraft_ident", "").upper(),
        route_from=data.get("route_from", "").upper(),
        route_to=data.get("route_to", "").upper(),
        sel=parse_float(data.get("sel")),
        mel=parse_float(data.get("mel")),
        day=parse_float(data.get("day")),
        night=parse_float(data.get("night")),
        cross_country=parse_float(data.get("cross_country")),
        actual_inst=parse_float(data.get("actual_inst")),
        simulated_inst=parse_float(data.get("simulated_inst")),
        num_inst_app=parse_int(data.get("num_inst_app")),
        landings_day=parse_int(data.get("landings_day")),
        landings_night=parse_int(data.get("landings_night")),
        pic=parse_float(data.get("pic")),
        sic=parse_float(data.get("sic")),
        dual_recd=parse_float(data.get("dual_recd")),
        dual_given=parse_float(data.get("dual_given")),
        solo=parse_float(data.get("solo")),
        total_duration=parse_float(data.get("total_duration")),
        remarks=data.get("remarks", ""),
    )

    storage.add_entry(entry)
    save_to_sheets()
    return jsonify({"id": entry.id, "message": "Entry created"}), 201


@app.route("/api/entries/<entry_id>", methods=["PUT"])
def update_entry(entry_id):
    """Update an existing logbook entry."""
    entry = storage.get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404

    data = request.json

    entry.date = data.get("date", entry.date)
    entry.aircraft_model = data.get("aircraft_model", entry.aircraft_model)
    entry.aircraft_ident = data.get("aircraft_ident", entry.aircraft_ident).upper()
    entry.route_from = data.get("route_from", entry.route_from).upper()
    entry.route_to = data.get("route_to", entry.route_to).upper()
    entry.sel = parse_float(data.get("sel"), entry.sel)
    entry.mel = parse_float(data.get("mel"), entry.mel)
    entry.day = parse_float(data.get("day"), entry.day)
    entry.night = parse_float(data.get("night"), entry.night)
    entry.cross_country = parse_float(data.get("cross_country"), entry.cross_country)
    entry.actual_inst = parse_float(data.get("actual_inst"), entry.actual_inst)
    entry.simulated_inst = parse_float(data.get("simulated_inst"), entry.simulated_inst)
    entry.num_inst_app = parse_int(data.get("num_inst_app"), entry.num_inst_app)
    entry.landings_day = parse_int(data.get("landings_day"), entry.landings_day)
    entry.landings_night = parse_int(data.get("landings_night"), entry.landings_night)
    entry.pic = parse_float(data.get("pic"), entry.pic)
    entry.sic = parse_float(data.get("sic"), entry.sic)
    entry.dual_recd = parse_float(data.get("dual_recd"), entry.dual_recd)
    entry.dual_given = parse_float(data.get("dual_given"), entry.dual_given)
    entry.solo = parse_float(data.get("solo"), entry.solo)
    entry.total_duration = parse_float(data.get("total_duration"), entry.total_duration)
    entry.remarks = data.get("remarks", entry.remarks)

    storage.update_entry(entry)
    save_to_sheets()
    return jsonify({"message": "Entry updated"})


@app.route("/api/entries/<entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    """Delete a logbook entry."""
    if storage.delete_entry(entry_id):
        save_to_sheets()
        return jsonify({"message": "Entry deleted"})
    return jsonify({"error": "Entry not found"}), 404


@app.route("/api/entries/batch", methods=["DELETE"])
def batch_delete_entries():
    """Delete multiple logbook entries in a batch."""
    data = request.json
    entry_ids = data.get("entry_ids", [])

    if not entry_ids:
        return jsonify({"error": "No entry IDs provided"}), 400

    deleted_count = storage.delete_entries(entry_ids)
    save_to_sheets()

    return jsonify({
        "success": True,
        "deleted": deleted_count,
        "message": f"Deleted {deleted_count} entries"
    })


@app.route("/api/totals", methods=["GET"])
def get_totals():
    """Get logbook totals."""
    return jsonify(storage.get_totals())


@app.route("/api/export/json", methods=["GET"])
def export_json():
    """Export logbook as JSON file."""
    # Build Logbook object for JSON export
    logbook = Logbook()
    for entry in storage.get_all_entries():
        logbook.entries[entry.id] = entry

    json_data = logbook.to_json()
    filename = f"logbook_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(filename, "w") as f:
        f.write(json_data)

    return send_file(
        filename,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    """Export logbook as CSV file."""
    import csv
    from io import StringIO

    entries = storage.get_all_entries(sort_by_date=True)

    output = StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow(LogbookEntry.get_sheets_headers())

    # Write data rows
    for entry in entries:
        writer.writerow(entry.to_sheets_row())

    output.seek(0)
    filename = f"logbook_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(filename, "w") as f:
        f.write(output.getvalue())

    return send_file(
        filename,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/import/json", methods=["POST"])
def import_json():
    """Import logbook entries from JSON."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = file.read().decode("utf-8")
        imported = Logbook.from_json(content)

        # Add all entries to SQLite
        for entry in imported.entries.values():
            storage.add_entry(entry)

        save_to_sheets()
        return jsonify(
            {"message": f"Imported {len(imported.entries)} entries", "success": True}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/export/sheets", methods=["POST"])
def export_to_sheets():
    """Export logbook to Google Sheets."""
    if not Config.GOOGLE_SHEETS_ID:
        return (
            jsonify(
                {"success": False, "error": "Google Sheets ID not configured in .env"}
            ),
            400,
        )

    result = sync_service.export_to_sheets()
    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/api/sync/status", methods=["GET"])
def get_sync_status():
    """Get current sync status."""
    return jsonify(sync_service.get_sync_status())


@app.route("/api/sync/reload", methods=["POST"])
def reload_from_sheets():
    """Force reload data from Google Sheets."""
    result = sync_service.load_from_sheets()
    return jsonify(result)


# ============== FlightAware Integration ==============


@app.route("/import")
def import_page():
    """FlightAware import page."""
    return render_template(
        "import.html",
        tail_number=Config.DEFAULT_TAIL_NUMBER,
    )


@app.route("/api/flightaware/search", methods=["POST"])
def search_flightaware():
    """Search FlightAware for flights by tail number."""
    from services.flightaware import FlightAwareService

    if not Config.FLIGHTAWARE_API_KEY:
        return jsonify({
            "success": False,
            "error": "FlightAware API key not configured. Set FLIGHTAWARE_API_KEY in .env"
        }), 400

    data = request.json or {}
    tail_number = data.get("tail_number") or Config.DEFAULT_TAIL_NUMBER
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    months_back = data.get("months_back") or 12

    try:
        service = FlightAwareService()
        flights = service.get_flights_as_logbook_entries(
            tail_number=tail_number,
            start_date=start_date,
            end_date=end_date,
            months_back=months_back,
        )

        # Ensure flights is a list
        if flights is None:
            flights = []

        # Check which flights are already in logbook (by date + route)
        existing_keys = storage.get_existing_keys()

        # Mark flights as already imported or new
        for flight in flights:
            route_from = flight.get('route_from') or ''
            route_to = flight.get('route_to') or ''
            date = flight.get('date') or ''
            key = f"{date}|{route_from}|{route_to}"
            flight["already_imported"] = key in existing_keys

        return jsonify({
            "success": True,
            "flights": flights,
            "count": len(flights),
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/flightaware/search/stream", methods=["GET"])
def search_flightaware_stream():
    """Stream FlightAware search results using OPTIMIZED batch import.

    Uses aggressive batching and minimal processing to avoid timeouts.
    Yields flights in batches for maximum performance.
    """
    import json

    from flask import Response
    from services.flightaware_optimized import OptimizedFlightAwareService

    if not Config.FLIGHTAWARE_API_KEY:
        def error_stream():
            yield f"data: {json.dumps({'error': 'FlightAware API key not configured'})}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')

    tail_number = request.args.get("tail_number") or Config.DEFAULT_TAIL_NUMBER

    # Get most recent flight date and existing keys from SQLite (always fresh)
    most_recent_date = storage.get_most_recent_flight_date()
    existing_keys = storage.get_existing_keys()

    def generate():
        import sys
        service = OptimizedFlightAwareService()
        flight_count = 0
        search_meta = {}
        search_summary = {}
        warnings = []

        try:
            yield ": keepalive\n\n"
            sys.stdout.flush()

            for result in service.stream_flights_ultra_fast(
                tail_number=tail_number,
                most_recent_flight_date=most_recent_date,
                existing_keys=existing_keys,
            ):
                # Handle metadata
                if result.get('_meta'):
                    search_meta = result['_meta']
                    yield f"data: {json.dumps({'meta': search_meta})}\n\n"
                    sys.stdout.flush()
                    continue

                # Handle warnings
                if result.get('_warning'):
                    warnings.append(result['_warning'])
                    yield f"data: {json.dumps({'warning': result['_warning']})}\n\n"
                    sys.stdout.flush()
                    continue

                # Handle summary
                if result.get('_summary'):
                    search_summary = result['_summary']
                    continue

                # Handle keepalive
                if result.get('_keepalive'):
                    yield ": keepalive\n\n"
                    sys.stdout.flush()
                    continue

                # Handle batch of flights
                if result.get('_batch'):
                    batch = result['_batch']
                    for flight in batch:
                        # Check if already imported
                        route_from = flight.get('route_from') or ''
                        route_to = flight.get('route_to') or ''
                        date = flight.get('date') or ''
                        key = f"{date}|{route_from}|{route_to}"
                        flight["already_imported"] = key in existing_keys

                        flight_count += 1
                        yield f"data: {json.dumps({'flight': flight})}\n\n"

                    # Heartbeat after each batch
                    yield ": heartbeat\n\n"
                    sys.stdout.flush()

            done_payload = {
                'done': True,
                'total': flight_count,
                'is_incremental': search_meta.get('is_incremental', False),
                'search_range': f"{search_meta.get('start_date', '?')} to {search_meta.get('end_date', '?')}",
                'api_errors': search_summary.get('api_errors', 0),
                'windows_searched': search_summary.get('windows_attempted', 0),
            }
            if warnings:
                done_payload['warnings'] = warnings
            yield f"data: {json.dumps(done_payload)}\n\n"
        except Exception as e:
            print(f"Error in streaming: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection'] = 'keep-alive'
    return response


@app.route("/api/flightaware/enrich", methods=["POST"])
def enrich_flights():
    """Enrich flight entries with airport lookups and calculations.

    This is phase 2 of the two-phase import process.
    Accepts a batch of flights for efficient processing.
    """
    from services.flightaware_optimized import OptimizedFlightAwareService

    data = request.json
    flights = data.get("flights", [])

    if not flights:
        return jsonify({"success": False, "error": "No flight data provided"}), 400

    try:
        service = OptimizedFlightAwareService()
        enriched = service.enrich_batch(flights)
        return jsonify({
            "success": True,
            "flights": enriched
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/approaches/<airport_code>", methods=["GET"])
def get_approaches(airport_code):
    """Get instrument approaches for an airport."""
    from services.airport_approaches import get_approaches_for_airport

    approaches = get_approaches_for_airport(airport_code)
    return jsonify({
        "success": True,
        "airport": airport_code.upper(),
        "approaches": approaches,
    })


@app.route("/api/flightaware/import", methods=["POST"])
def import_flightaware():
    """Import selected flights from FlightAware into logbook."""
    from services.flightaware_optimized import OptimizedFlightAwareService

    data = request.json
    flights = data.get("flights", [])

    if not flights:
        return jsonify({"success": False, "error": "No flights to import"}), 400

    # Enrich flights with airport data and night hours
    service = OptimizedFlightAwareService()
    flights = service.enrich_batch(flights)

    imported_count = 0
    for flight_data in flights:
        # Remove metadata fields that shouldn't be saved to database
        flight_data.pop("already_imported", None)
        flight_data.pop("fa_flight_id", None)
        flight_data.pop("duration_estimated", None)
        flight_data.pop("imc_estimated", None)

        entry = LogbookEntry(
            date=flight_data.get("date", ""),
            aircraft_model=flight_data.get("aircraft_model", ""),
            aircraft_ident=flight_data.get("aircraft_ident", "").upper(),
            route_from=flight_data.get("route_from", "").upper(),
            route_to=flight_data.get("route_to", "").upper(),
            sel=parse_float(flight_data.get("sel")),
            mel=parse_float(flight_data.get("mel")),
            day=parse_float(flight_data.get("day")),
            night=parse_float(flight_data.get("night")),
            cross_country=parse_float(flight_data.get("cross_country")),
            actual_inst=parse_float(flight_data.get("actual_inst")),
            simulated_inst=parse_float(flight_data.get("simulated_inst")),
            num_inst_app=parse_int(flight_data.get("num_inst_app")),
            landings_day=parse_int(flight_data.get("landings_day")),
            landings_night=parse_int(flight_data.get("landings_night")),
            pic=parse_float(flight_data.get("pic")),
            sic=parse_float(flight_data.get("sic")),
            dual_recd=parse_float(flight_data.get("dual_recd")),
            dual_given=parse_float(flight_data.get("dual_given")),
            solo=parse_float(flight_data.get("solo")),
            total_duration=parse_float(flight_data.get("total_duration")),
            remarks=flight_data.get("remarks", ""),
        )

        storage.add_entry(entry)
        imported_count += 1

    save_to_sheets()
    return jsonify({
        "success": True,
        "message": f"Imported {imported_count} flight(s)",
        "imported": imported_count,
    })


@app.route("/scan")
def scan_page():
    """Render logbook scanning interface."""
    return render_template("scan.html")


@app.route("/api/logbook/scan/upload", methods=["POST"])
def upload_scan():
    """
    Accept image upload, extract flight entries using Gemini AI.

    Accepts multipart/form-data with 'image' file.
    Returns extracted flight entries as JSON.
    """
    import uuid
    from services.ocr_service import LogbookOCRService

    if 'image' not in request.files:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    try:
        # Save temp file
        temp_path = f"/tmp/logbook_{uuid.uuid4()}.jpg"
        file.save(temp_path)

        # Extract flight data using Gemini AI (multimodal LLM)
        print(f"Starting Gemini extraction for: {temp_path}")
        ocr_service = LogbookOCRService()
        entries, expected_rows, actual_rows = ocr_service.extract_flights_with_gemini(temp_path)

        # Cleanup
        os.remove(temp_path)

        if not entries:
            return jsonify({
                "success": False,
                "error": "No flight entries detected. Please ensure the image shows a logbook page with flight data."
            }), 400

        # Build warning if rows are missing
        warning = None
        if expected_rows > actual_rows:
            warning = f"Expected {expected_rows} rows but only extracted {actual_rows}. Some rows may be missing."

        print(f"Successfully extracted {actual_rows} of {expected_rows} entries")
        return jsonify({
            "success": True,
            "warning": warning,
            "entries": entries,
            "count": len(entries),
        })

    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/logbook/scan/import", methods=["POST"])
def import_scanned():
    """
    Import scanned logbook entries into database.

    Accepts JSON with 'entries' array.
    Returns imported count and entry IDs for undo.
    """
    data = request.json
    entries = data.get("entries", [])

    if not entries:
        return jsonify({"success": False, "error": "No entries to import"}), 400

    entry_ids = []
    for entry_data in entries:
        # Remove metadata
        entry_data.pop("_raw", None)

        # Create entry
        entry = LogbookEntry(
            date=entry_data.get("date", ""),
            aircraft_model=entry_data.get("aircraft_model", ""),
            aircraft_ident=entry_data.get("aircraft_ident", "").upper(),
            route_from=entry_data.get("route_from", "").upper(),
            route_to=entry_data.get("route_to", "").upper(),
            sel=parse_float(entry_data.get("sel")),
            mel=parse_float(entry_data.get("mel")),
            day=parse_float(entry_data.get("day")),
            night=parse_float(entry_data.get("night")),
            cross_country=parse_float(entry_data.get("cross_country")),
            actual_inst=parse_float(entry_data.get("actual_inst")),
            simulated_inst=parse_float(entry_data.get("simulated_inst")),
            num_inst_app=parse_int(entry_data.get("num_inst_app")),
            landings_day=parse_int(entry_data.get("landings_day")),
            landings_night=parse_int(entry_data.get("landings_night")),
            pic=parse_float(entry_data.get("pic")),
            sic=parse_float(entry_data.get("sic")),
            dual_recd=parse_float(entry_data.get("dual_recd")),
            dual_given=parse_float(entry_data.get("dual_given")),
            solo=parse_float(entry_data.get("solo")),
            total_duration=parse_float(entry_data.get("total_duration")),
            remarks=entry_data.get("remarks", ""),
        )

        entry_id = storage.add_entry(entry)
        entry_ids.append(entry_id)

    save_to_sheets()

    return jsonify({
        "success": True,
        "imported": len(entry_ids),
        "entry_ids": entry_ids,
        "message": f"Imported {len(entry_ids)} flight(s) from scanned logbook"
    })


if __name__ == "__main__":
    print(f"Starting Pilot Logbook on http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
