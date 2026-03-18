"""
Google Sheets backup/restore service.

Uses the Google Sheets REST API v4 directly via `requests`,
avoiding the google-api-python-client dependency.
"""

import re
from typing import Optional

import requests

from config import Config
from models.logbook_entry import LogbookEntry, normalize_airport


def _normalize_route_via(route_via: str) -> str:
    """Normalize a multi-leg route string to ICAO codes."""
    if not route_via:
        return ""
    legs = [normalize_airport(leg.strip()) for leg in route_via.split("-") if leg.strip()]
    return "-".join(legs)


SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleSheetsError(Exception):
    """Raised when a Sheets API call fails."""
    pass


class GoogleSheetsService:
    """Backup and restore logbook entries to/from Google Sheets."""

    def __init__(self, refresh_token: str):
        if not refresh_token:
            raise GoogleSheetsError(
                "No Google refresh token. Please sign in with Google first."
            )
        self.refresh_token = refresh_token
        self._access_token: Optional[str] = None

    def _get_access_token(self) -> str:
        """Exchange refresh token for a fresh access token."""
        if self._access_token:
            return self._access_token

        resp = requests.post(TOKEN_URL, data={
            "client_id": Config.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": Config.GOOGLE_OAUTH_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        })

        if resp.status_code != 200:
            raise GoogleSheetsError(
                f"Failed to refresh Google token: {resp.text[:300]}"
            )

        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def _api_call(self, method: str, url: str, **kwargs) -> dict:
        """Make an API call with automatic token refresh on 401."""
        resp = getattr(requests, method)(url, headers=self._headers(), **kwargs)

        if resp.status_code == 401:
            self._access_token = None
            resp = getattr(requests, method)(url, headers=self._headers(), **kwargs)

        if resp.status_code not in (200, 201):
            raise GoogleSheetsError(
                f"Google API error {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json()

    # ── Backup ─────────────────────────────────────────────

    def _create_spreadsheet(self, title: str) -> tuple[str, int]:
        """Create a new Google Sheet. Returns (spreadsheet ID, sheet ID)."""
        body = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Logbook"}}],
        }
        data = self._api_call("post", SHEETS_API, json=body)
        grid_id = data["sheets"][0]["properties"]["sheetId"]
        return data["spreadsheetId"], grid_id

    def _get_sheet_id(self, spreadsheet_id: str) -> int:
        """Get the sheet ID of the first sheet in a spreadsheet."""
        url = f"{SHEETS_API}/{spreadsheet_id}?fields=sheets.properties"
        data = self._api_call("get", url)
        return data["sheets"][0]["properties"]["sheetId"]

    def backup(self, entries: list[LogbookEntry], sheet_id: Optional[str] = None,
               user_name: str = "") -> str:
        """
        Write all entries to a Google Sheet (full overwrite).

        Creates a new spreadsheet if sheet_id is None.
        Returns the spreadsheet ID.
        """
        grid_id = None
        if not sheet_id:
            title = f"Pilot Logbook - {user_name}".strip(" -") if user_name else "Pilot Logbook Backup"
            sheet_id, grid_id = self._create_spreadsheet(title)

        if grid_id is None:
            grid_id = self._get_sheet_id(sheet_id)

        # Build data: headers + rows
        headers = LogbookEntry.get_sheets_headers()
        rows = [headers] + [e.to_sheets_row() for e in entries]

        # Clear existing data
        clear_url = f"{SHEETS_API}/{sheet_id}/values/Logbook!A:Z:clear"
        self._api_call("post", clear_url)

        # Write all data
        update_url = (
            f"{SHEETS_API}/{sheet_id}/values/Logbook!A1"
            f"?valueInputOption=USER_ENTERED"
        )
        self._api_call("put", update_url, json={"values": rows})

        # Format header row (bold, light gray background, frozen)
        format_body = {
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": grid_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.9, "green": 0.9, "blue": 0.9,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            }, {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": grid_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }],
        }
        batch_url = f"{SHEETS_API}/{sheet_id}:batchUpdate"
        self._api_call("post", batch_url, json=format_body)

        return sheet_id

    # ── Restore ────────────────────────────────────────────

    @staticmethod
    def extract_sheet_id(url_or_id: str) -> str:
        """Extract spreadsheet ID from a Google Sheets URL or raw ID."""
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
        if match:
            return match.group(1)
        if re.match(r"^[a-zA-Z0-9_-]+$", url_or_id):
            return url_or_id
        raise GoogleSheetsError(f"Could not extract Sheet ID from: {url_or_id}")

    def restore(self, sheet_id: str, existing_keys: dict[str, dict]) -> list[LogbookEntry]:
        """
        Read entries from a Google Sheet and return new LogbookEntry objects.
        Skips rows whose date|from|to key already exists in existing_keys.
        """
        url = f"{SHEETS_API}/{sheet_id}/values/A:Z"
        data = self._api_call("get", url)
        rows = data.get("values", [])

        if not rows:
            return []

        headers = [h.strip().lower() for h in rows[0]]
        header_map = self._build_header_map(headers)

        new_entries = []
        for row in rows[1:]:
            if not row or not any(cell.strip() for cell in row):
                continue

            entry = self._row_to_entry(row, header_map)
            if entry is None:
                continue

            from models.logbook_entry import make_entry_key
            key = make_entry_key(entry.date, entry.route_from, entry.route_to)
            if key in existing_keys:
                continue

            existing_keys[key] = {"id": entry.id, "source": "sheets"}
            new_entries.append(entry)

        return new_entries

    @staticmethod
    def _build_header_map(headers: list[str]) -> dict[str, int]:
        """Map header names to column indices, tolerating variations."""
        known = {
            "date": "date",
            "aircraft make & model": "aircraft_model",
            "aircraft make and model": "aircraft_model",
            "make & model": "aircraft_model",
            "aircraft ident": "aircraft_ident",
            "ident": "aircraft_ident",
            "tail": "aircraft_ident",
            "from": "route_from",
            "departure": "route_from",
            "to": "route_to",
            "arrival": "route_to",
            "route": "route_via",
            "sel": "sel",
            "single engine land": "sel",
            "mel": "mel",
            "multi engine land": "mel",
            "day": "day",
            "night": "night",
            "cross country": "cross_country",
            "xc": "cross_country",
            "actual inst": "actual_inst",
            "actual instrument": "actual_inst",
            "sim inst": "simulated_inst",
            "simulated inst": "simulated_inst",
            "simulated instrument": "simulated_inst",
            "hood": "simulated_inst",
            "# appr": "num_inst_app",
            "approaches": "num_inst_app",
            "num approaches": "num_inst_app",
            "day ldg": "landings_day",
            "day landings": "landings_day",
            "night ldg": "landings_night",
            "night landings": "landings_night",
            "pic": "pic",
            "sic": "sic",
            "dual recd": "dual_recd",
            "dual received": "dual_recd",
            "dual given": "dual_given",
            "solo": "solo",
            "sim/ftd": "sim",
            "simulator": "sim",
            "ftd": "sim",
            "total": "total_duration",
            "total time": "total_duration",
            "total duration": "total_duration",
            "remarks": "remarks",
            "source": "source",
        }
        mapping = {}
        for idx, header in enumerate(headers):
            field_name = known.get(header)
            if field_name:
                mapping[field_name] = idx
        return mapping

    @staticmethod
    def _row_to_entry(row: list[str], header_map: dict[str, int]) -> Optional[LogbookEntry]:
        """Convert a sheet row to a LogbookEntry using the header map."""
        def get(field: str, default: str = "") -> str:
            idx = header_map.get(field)
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return default

        def get_float(field: str) -> float:
            val = get(field)
            if not val:
                return 0.0
            try:
                return float(val)
            except ValueError:
                return 0.0

        def get_int(field: str) -> int:
            val = get(field)
            if not val:
                return 0
            try:
                return int(float(val))
            except ValueError:
                return 0

        date = get("date")
        if not date:
            return None

        return LogbookEntry(
            date=date,
            aircraft_model=get("aircraft_model"),
            aircraft_ident=get("aircraft_ident").upper(),
            route_from=normalize_airport(get("route_from")),
            route_to=normalize_airport(get("route_to")),
            route_via=_normalize_route_via(get("route_via")),
            sel=get_float("sel"),
            mel=get_float("mel"),
            day=get_float("day"),
            night=get_float("night"),
            cross_country=get_float("cross_country"),
            actual_inst=get_float("actual_inst"),
            simulated_inst=get_float("simulated_inst"),
            num_inst_app=get_int("num_inst_app"),
            landings_day=get_int("landings_day"),
            landings_night=get_int("landings_night"),
            pic=get_float("pic"),
            sic=get_float("sic"),
            dual_recd=get_float("dual_recd"),
            dual_given=get_float("dual_given"),
            solo=get_float("solo"),
            sim=get_float("sim"),
            total_duration=get_float("total_duration"),
            remarks=get("remarks"),
            source=get("source", "manual"),
            reviewed=False,
        )
