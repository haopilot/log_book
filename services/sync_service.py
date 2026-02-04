"""
Synchronization service between SQLite and Google Sheets.

Handles loading data from Sheets into SQLite on startup,
and exporting SQLite data back to Sheets as backup.
"""

import threading
from datetime import datetime
from typing import Optional

from config import Config
from services.sqlite_storage import SQLiteStorage


class SyncService:
    """Manages synchronization between SQLite (local) and Google Sheets (backup)."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage
        self._sync_lock = threading.Lock()
        self._last_sync: Optional[datetime] = None
        self._pending_sync = False

    def load_from_sheets(self) -> dict:
        """
        Load data from Google Sheets into SQLite.
        Called on startup to populate local cache from authoritative source.
        """
        if not Config.GOOGLE_SHEETS_ID:
            return {"success": False, "error": "Google Sheets not configured"}

        try:
            from services.google_sheets import GoogleSheetsService

            sheets_service = GoogleSheetsService()
            result = sheets_service.import_logbook()

            if result.get("success") and result.get("entries"):
                # Clear local and bulk insert from Sheets
                self.storage.clear_all()
                count = self.storage.bulk_insert(result["entries"])
                self._last_sync = datetime.utcnow()
                return {
                    "success": True,
                    "count": count,
                    "message": f"Loaded {count} entries from Google Sheets",
                }
            elif result.get("success"):
                # Sheets is empty but accessible
                self.storage.clear_all()
                self._last_sync = datetime.utcnow()
                return {"success": True, "count": 0, "message": "Google Sheets is empty"}
            else:
                return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def export_to_sheets(self) -> dict:
        """
        Export SQLite data to Google Sheets.
        Called after mutations to keep Sheets in sync as backup.
        """
        if not Config.GOOGLE_SHEETS_ID:
            return {"success": False, "error": "Google Sheets not configured"}

        with self._sync_lock:
            try:
                from models.logbook_entry import Logbook
                from services.google_sheets import GoogleSheetsService

                # Build Logbook object from SQLite for export
                # (GoogleSheetsService expects a Logbook object)
                logbook = Logbook()
                for entry in self.storage.get_all_entries(sort_by_date=False):
                    logbook.entries[entry.id] = entry

                sheets_service = GoogleSheetsService()
                result = sheets_service.export_logbook(logbook)

                if result.get("success"):
                    self._last_sync = datetime.utcnow()
                    self._pending_sync = False

                return result
            except Exception as e:
                return {"success": False, "error": str(e)}

    def mark_dirty(self):
        """Mark that local data has changed and needs sync to Sheets."""
        self._pending_sync = True

    def needs_sync(self) -> bool:
        """Check if sync to Sheets is pending."""
        return self._pending_sync

    def get_last_sync(self) -> Optional[datetime]:
        """Get timestamp of last successful sync."""
        return self._last_sync

    def get_sync_status(self) -> dict:
        """Get current sync status for diagnostics."""
        return {
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "pending_sync": self._pending_sync,
            "sheets_configured": bool(Config.GOOGLE_SHEETS_ID),
            "local_count": self.storage.count(),
        }
