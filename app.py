"""
Pilot Logbook - Web Application

A web-based pilot logbook using ASA Standard format.
"""

import os
from datetime import datetime

from config import Config
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from models.logbook_entry import Logbook, LogbookEntry

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY


def init_logbook():
    """Initialize logbook from Google Sheets or local file."""
    logbook_instance = Logbook()

    # Try loading from Google Sheets if configured
    if Config.GOOGLE_SHEETS_ID:
        try:
            from services.google_sheets import GoogleSheetsService
            sheets_service = GoogleSheetsService()
            result = sheets_service.import_logbook()

            if result.get("success") and result.get("entries"):
                print(f"✓ Loaded {len(result['entries'])} entries from Google Sheets")
                for entry in result["entries"]:
                    logbook_instance.add_entry(entry)
                return logbook_instance
            else:
                print("Google Sheets configured but empty or error, loading from local file")
        except Exception as e:
            print(f"Could not load from Google Sheets: {e}, loading from local file")

    # Fall back to local file
    if os.path.exists(Config.DATA_FILE):
        logbook_instance = Logbook.load_from_file(Config.DATA_FILE)
        print(f"✓ Loaded logbook from {Config.DATA_FILE}")
    else:
        print("No existing logbook found, starting fresh")

    return logbook_instance


# Global logbook instance
logbook = init_logbook()


def save_logbook():
    """Save logbook to file and Google Sheets if configured."""
    # Save to local file
    logbook.save_to_file(Config.DATA_FILE)

    # Also save to Google Sheets if configured
    if Config.GOOGLE_SHEETS_ID:
        try:
            from services.google_sheets import GoogleSheetsService
            sheets_service = GoogleSheetsService()
            result = sheets_service.export_logbook(logbook)
            if result.get("success"):
                print(f"✓ Synced {result.get('rows', 0)} entries to Google Sheets")
        except Exception as e:
            print(f"Warning: Could not sync to Google Sheets: {e}")


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
    entries = logbook.get_all_entries(sort_by_date=True)
    totals = logbook.get_totals()
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
    entry = logbook.get_entry(entry_id)
    if not entry:
        return redirect(url_for("index"))
    return render_template("entry.html", entry=entry.to_dict(), is_new=False)


@app.route("/api/entries", methods=["GET"])
def get_entries():
    """Get all logbook entries."""
    entries = logbook.get_all_entries(sort_by_date=True)
    return jsonify([e.to_dict() for e in entries])


@app.route("/api/entries/<entry_id>", methods=["GET"])
def get_entry(entry_id):
    """Get a specific logbook entry."""
    entry = logbook.get_entry(entry_id)
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

    logbook.add_entry(entry)
    save_logbook()
    return jsonify({"id": entry.id, "message": "Entry created"}), 201


@app.route("/api/entries/<entry_id>", methods=["PUT"])
def update_entry(entry_id):
    """Update an existing logbook entry."""
    entry = logbook.get_entry(entry_id)
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

    logbook.update_entry(entry)
    save_logbook()
    return jsonify({"message": "Entry updated"})


@app.route("/api/entries/<entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    """Delete a logbook entry."""
    if logbook.delete_entry(entry_id):
        save_logbook()
        return jsonify({"message": "Entry deleted"})
    return jsonify({"error": "Entry not found"}), 404


@app.route("/api/totals", methods=["GET"])
def get_totals():
    """Get logbook totals."""
    return jsonify(logbook.get_totals())


@app.route("/api/export/json", methods=["GET"])
def export_json():
    """Export logbook as JSON file."""
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

    entries = logbook.get_all_entries(sort_by_date=True)

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
    global logbook

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = file.read().decode("utf-8")
        imported = Logbook.from_json(content)

        for entry_id, entry in imported.entries.items():
            logbook.entries[entry_id] = entry

        save_logbook()
        return jsonify(
            {"message": f"Imported {len(imported.entries)} entries", "success": True}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/export/sheets", methods=["POST"])
def export_to_sheets():
    """Export logbook to Google Sheets."""
    from services.google_sheets import GoogleSheetsService

    if not Config.GOOGLE_SHEETS_ID:
        return (
            jsonify(
                {"success": False, "error": "Google Sheets ID not configured in .env"}
            ),
            400,
        )

    try:
        service = GoogleSheetsService()
        result = service.export_logbook(logbook)
        return jsonify(result)
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
        existing_entries = logbook.get_all_entries() or []
        existing_keys = set()
        for entry in existing_entries:
            key = f"{entry.date}|{entry.route_from}|{entry.route_to}"
            existing_keys.add(key)

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
    """Stream FlightAware search results incrementally using Server-Sent Events."""
    import json

    from flask import Response
    from services.flightaware import FlightAwareService

    if not Config.FLIGHTAWARE_API_KEY:
        def error_stream():
            yield f"data: {json.dumps({'error': 'FlightAware API key not configured'})}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')

    tail_number = request.args.get("tail_number") or Config.DEFAULT_TAIL_NUMBER
    months_back = int(request.args.get("months_back") or 12)

    # Get existing entries for duplicate checking
    existing_entries = logbook.get_all_entries() or []
    existing_keys = set()
    for entry in existing_entries:
        key = f"{entry.date}|{entry.route_from}|{entry.route_to}"
        existing_keys.add(key)

    def generate():
        service = FlightAwareService()

        try:
            # Stream flights as they're fetched
            for flight in service.get_flights_as_logbook_entries_streaming(
                tail_number=tail_number,
                months_back=months_back,
            ):
                # Check if already imported
                route_from = flight.get('route_from') or ''
                route_to = flight.get('route_to') or ''
                date = flight.get('date') or ''
                key = f"{date}|{route_from}|{route_to}"
                flight["already_imported"] = key in existing_keys

                yield f"data: {json.dumps({'flight': flight})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


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
    data = request.json
    flights = data.get("flights", [])

    if not flights:
        return jsonify({"success": False, "error": "No flights to import"}), 400

    imported_count = 0
    for flight_data in flights:
        # Remove the already_imported and fa_flight_id fields before creating entry
        flight_data.pop("already_imported", None)
        flight_data.pop("fa_flight_id", None)

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

        logbook.add_entry(entry)
        imported_count += 1

    save_logbook()
    return jsonify({
        "success": True,
        "message": f"Imported {imported_count} flight(s)",
        "imported": imported_count,
    })


if __name__ == "__main__":
    print(f"Starting Pilot Logbook on http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
