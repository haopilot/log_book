"""
Google Sheets integration for Pilot Logbook.

Provides export and sync functionality with Google Sheets.
ASA Standard format.
"""

import os
import pickle
from typing import Optional

from config import Config
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from models.logbook_entry import Logbook, LogbookEntry

# Scopes required for Google Sheets access
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsService:
    """Service for Google Sheets integration."""

    def __init__(
        self,
        credentials_file: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
    ):
        self.credentials_file = credentials_file or Config.GOOGLE_CREDENTIALS_FILE
        self.spreadsheet_id = spreadsheet_id or Config.GOOGLE_SHEETS_ID
        self.service = None
        self._creds = None

    def _get_credentials(self) -> Credentials:
        """Get or refresh Google API credentials."""
        creds = None
        token_file = "token.pickle"

        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Credentials file not found: {self.credentials_file}. "
                        "Download credentials.json from Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        return creds

    def _get_service(self):
        """Get or create Google Sheets service."""
        if self.service is None:
            creds = self._get_credentials()
            self.service = build("sheets", "v4", credentials=creds)
        return self.service

    def export_logbook(self, logbook: Logbook, sheet_name: str = "Logbook") -> dict:
        """
        Export entire logbook to Google Sheets.

        Args:
            logbook: Logbook instance to export
            sheet_name: Name of the sheet tab

        Returns:
            Result dict with success status and details
        """
        if not self.spreadsheet_id:
            return {"success": False, "error": "No spreadsheet ID configured"}

        try:
            service = self._get_service()

            # Prepare data
            entries = logbook.get_all_entries(sort_by_date=True)
            totals = logbook.get_totals()

            # Create headers and data rows
            headers = LogbookEntry.get_sheets_headers()
            data_rows = [entry.to_sheets_row() for entry in entries]

            # Add totals row matching ASA format
            totals_row = [
                "TOTALS",
                "",
                "",
                "",
                "",
                round(totals["sel"], 1) if totals["sel"] else "",
                round(totals["mel"], 1) if totals["mel"] else "",
                round(totals["day"], 1) if totals["day"] else "",
                round(totals["night"], 1) if totals["night"] else "",
                round(totals["cross_country"], 1) if totals["cross_country"] else "",
                round(totals["actual_inst"], 1) if totals["actual_inst"] else "",
                round(totals["simulated_inst"], 1) if totals["simulated_inst"] else "",
                totals["num_inst_app"] if totals["num_inst_app"] else "",
                totals["landings_day"] if totals["landings_day"] else "",
                totals["landings_night"] if totals["landings_night"] else "",
                round(totals["pic"], 1) if totals["pic"] else "",
                round(totals["sic"], 1) if totals["sic"] else "",
                round(totals["dual_recd"], 1) if totals["dual_recd"] else "",
                round(totals["dual_given"], 1) if totals["dual_given"] else "",
                round(totals["solo"], 1) if totals["solo"] else "",
                round(totals["total_duration"], 1) if totals["total_duration"] else "",
                f"{totals['flights']} flights",
            ]

            # Combine all data
            all_data = [headers] + data_rows + [totals_row]

            # Check if sheet exists, create if not
            self._ensure_sheet_exists(sheet_name)

            # Clear existing data
            range_name = f"{sheet_name}!A1:V1000"
            service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            # Write new data
            body = {"values": all_data}
            result = (
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A1",
                    valueInputOption="USER_ENTERED",
                    body=body,
                )
                .execute()
            )

            # Format the header row
            self._format_header_row(sheet_name)

            return {
                "success": True,
                "updated_cells": result.get("updatedCells", 0),
                "rows": len(data_rows),
                "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}",
            }

        except HttpError as e:
            return {"success": False, "error": f"Google API error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _ensure_sheet_exists(self, sheet_name: str):
        """Create sheet if it doesn't exist."""
        try:
            service = self._get_service()
            spreadsheet = (
                service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            )

            sheet_exists = any(
                sheet["properties"]["title"] == sheet_name
                for sheet in spreadsheet.get("sheets", [])
            )

            if not sheet_exists:
                request = {
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {
                                    "title": sheet_name,
                                }
                            }
                        }
                    ]
                }
                service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id, body=request
                ).execute()

        except HttpError:
            pass

    def _format_header_row(self, sheet_name: str):
        """Format the header row (bold, background color)."""
        try:
            service = self._get_service()

            spreadsheet = (
                service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            )

            sheet_id = None
            for sheet in spreadsheet.get("sheets", []):
                if sheet["properties"]["title"] == sheet_name:
                    sheet_id = sheet["properties"]["sheetId"]
                    break

            if sheet_id is None:
                return

            requests = [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.2,
                                    "green": 0.3,
                                    "blue": 0.6,
                                },
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 1.0,
                                        "green": 1.0,
                                        "blue": 1.0,
                                    },
                                    "bold": True,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
            ]

            service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"requests": requests}
            ).execute()

        except HttpError:
            pass
