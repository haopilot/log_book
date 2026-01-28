# Pilot Logbook - Automatic Flight Log Generator

Automatically generates FAA-compliant pilot logbook entries from FlightAware data.

## Features

- **FlightAware Integration**: Fetches flight data by aircraft tail number (N-number)
- **FAA-Compliant Entries**: Generates logbook entries meeting FAR 61.51 requirements
- **Automatic Calculations**:
  - Day/Night flight time based on sunrise/sunset
  - Instrument time from weather conditions
  - Approaches from flight track data
  - Cross-country time determination
- **Google Sheets Storage**: Store and sync logbook entries
- **Web UI**: View, edit, and manage logbook entries
- **Auto-Scan**: Detect new flights automatically

## FAA Logbook Requirements (FAR 61.51)

Each logbook entry includes:
- Date of flight
- Total flight time or lesson time
- Location/Route (departure and arrival airports)
- Aircraft make, model, and identification (N-number)
- Name of safety pilot (if required)
- Type of pilot experience/training:
  - Solo
  - PIC (Pilot in Command)
  - SIC (Second in Command)
  - Flight training received
  - Instrument (actual/simulated)
  - Night
  - Cross-country
  - Landings (day/night)
  - Approaches (type and location)

## Setup

1. **FlightAware API Key**
   - Sign up at https://flightaware.com/commercial/aeroapi/
   - Get your API key

2. **Google Sheets API**
   - Enable Google Sheets API in Google Cloud Console
   - Download credentials.json

3. **Environment Variables**
   Create a `.env` file:
   ```
   FLIGHTAWARE_API_KEY=your_api_key
   GOOGLE_SHEETS_ID=your_spreadsheet_id
   AIRCRAFT_TAIL_NUMBER=N790TB
   ```

4. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the Application**
   ```bash
   python app.py
   ```

## Project Structure

```
log_book/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
├── models/
│   └── logbook_entry.py   # Logbook data model
├── services/
│   ├── flightaware.py     # FlightAware API integration
│   ├── google_sheets.py   # Google Sheets integration
│   ├── sun_calculator.py  # Sunrise/sunset calculations
│   └── weather.py         # Weather data processing
├── templates/
│   └── logbook.html       # Web UI template
└── static/
    └── styles.css         # UI styles
```

## API Endpoints

- `GET /` - Logbook web interface
- `GET /api/flights` - List all logbook entries
- `GET /api/flights/<id>` - Get specific flight entry
- `POST /api/flights/scan` - Scan for new flights
- `PUT /api/flights/<id>` - Update flight entry
- `DELETE /api/flights/<id>` - Delete flight entry
- `POST /api/flights/export` - Export to Google Sheets
- `POST /api/flights/sync` - Sync with Google Sheets

## Usage

1. Open the web interface at `http://localhost:5051`
2. Enter your aircraft tail number
3. Click "Scan for Flights" to fetch recent flights
4. Review and edit auto-generated entries
5. Export to Google Sheets

## License

MIT License
