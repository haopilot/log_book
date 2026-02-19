"""
SQLite storage service for pilot logbook.

Provides thread-safe CRUD operations using SQLite as the primary local store.
Google Sheets is used as backup/sync target via SyncService.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from models.logbook_entry import LogbookEntry


class SQLiteStorage:
    """Thread-safe SQLite storage for logbook entries."""

    def __init__(self, db_path: str = "logbook.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    date TEXT,
                    aircraft_model TEXT,
                    aircraft_ident TEXT,
                    route_from TEXT,
                    route_to TEXT,
                    sel REAL DEFAULT 0,
                    mel REAL DEFAULT 0,
                    day REAL DEFAULT 0,
                    night REAL DEFAULT 0,
                    cross_country REAL DEFAULT 0,
                    actual_inst REAL DEFAULT 0,
                    simulated_inst REAL DEFAULT 0,
                    num_inst_app INTEGER DEFAULT 0,
                    landings_day INTEGER DEFAULT 0,
                    landings_night INTEGER DEFAULT 0,
                    pic REAL DEFAULT 0,
                    sic REAL DEFAULT 0,
                    dual_recd REAL DEFAULT 0,
                    dual_given REAL DEFAULT 0,
                    solo REAL DEFAULT 0,
                    total_duration REAL DEFAULT 0,
                    duration_estimated INTEGER DEFAULT 0,
                    remarks TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # Create indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON entries(date)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_aircraft ON entries(aircraft_ident)"
            )
            conn.commit()

            # Migrate: add columns if they don't exist
            for col, col_def in [
                ("locked", "INTEGER DEFAULT 0"),
                ("reviewed", "INTEGER DEFAULT 1"),
                ("sim", "REAL DEFAULT 0"),
                ("route_via", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE entries ADD COLUMN {col} {col_def}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists

    def add_entry(self, entry: LogbookEntry) -> str:
        """Add a new entry to the database."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO entries (
                    id, date, aircraft_model, aircraft_ident,
                    route_from, route_to, route_via, sel, mel, day, night,
                    cross_country, actual_inst, simulated_inst,
                    num_inst_app, landings_day, landings_night,
                    pic, sic, dual_recd, dual_given, solo, sim,
                    total_duration, duration_estimated, remarks,
                    created_at, updated_at, locked, reviewed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.id,
                    entry.date,
                    entry.aircraft_model,
                    entry.aircraft_ident,
                    entry.route_from,
                    entry.route_to,
                    entry.route_via,
                    entry.sel,
                    entry.mel,
                    entry.day,
                    entry.night,
                    entry.cross_country,
                    entry.actual_inst,
                    entry.simulated_inst,
                    entry.num_inst_app,
                    entry.landings_day,
                    entry.landings_night,
                    entry.pic,
                    entry.sic,
                    entry.dual_recd,
                    entry.dual_given,
                    entry.solo,
                    entry.sim,
                    entry.total_duration,
                    1 if entry.duration_estimated else 0,
                    entry.remarks,
                    entry.created_at,
                    entry.updated_at,
                    1 if entry.locked else 0,
                    1 if entry.reviewed else 0,
                ),
            )
            conn.commit()
        return entry.id

    def get_entry(self, entry_id: str) -> Optional[LogbookEntry]:
        """Get a single entry by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_entry(row)
        return None

    def get_all_entries(self, sort_by_date: bool = True) -> list[LogbookEntry]:
        """Get all entries, optionally sorted by date (most recent first)."""
        with self._get_connection() as conn:
            if sort_by_date:
                # Sort by date descending (most recent first)
                # Handle M/D/YYYY or MM/DD/YYYY format by parsing with instr()
                cursor = conn.execute("""
                    SELECT * FROM entries
                    ORDER BY
                        CASE
                            WHEN date LIKE '%/%/%'
                            THEN substr(date, instr(date, '/') + instr(substr(date, instr(date, '/') + 1), '/') + 1) || '-' ||
                                 printf('%02d', CAST(substr(date, 1, instr(date, '/') - 1) AS INTEGER)) || '-' ||
                                 printf('%02d', CAST(substr(date, instr(date, '/') + 1, instr(substr(date, instr(date, '/') + 1), '/') - 1) AS INTEGER))
                            ELSE date
                        END DESC
                """)
            else:
                cursor = conn.execute("SELECT * FROM entries")
            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def update_entry(self, entry: LogbookEntry) -> bool:
        """Update an existing entry."""
        entry.update_timestamp()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE entries SET
                    date=?, aircraft_model=?, aircraft_ident=?,
                    route_from=?, route_to=?, route_via=?,
                    sel=?, mel=?, day=?, night=?,
                    cross_country=?, actual_inst=?, simulated_inst=?,
                    num_inst_app=?, landings_day=?, landings_night=?,
                    pic=?, sic=?, dual_recd=?, dual_given=?, solo=?, sim=?,
                    total_duration=?, duration_estimated=?, remarks=?,
                    updated_at=?, locked=?, reviewed=?
                WHERE id=?
            """,
                (
                    entry.date,
                    entry.aircraft_model,
                    entry.aircraft_ident,
                    entry.route_from,
                    entry.route_to,
                    entry.route_via,
                    entry.sel,
                    entry.mel,
                    entry.day,
                    entry.night,
                    entry.cross_country,
                    entry.actual_inst,
                    entry.simulated_inst,
                    entry.num_inst_app,
                    entry.landings_day,
                    entry.landings_night,
                    entry.pic,
                    entry.sic,
                    entry.dual_recd,
                    entry.dual_given,
                    entry.solo,
                    entry.sim,
                    entry.total_duration,
                    1 if entry.duration_estimated else 0,
                    entry.remarks,
                    entry.updated_at,
                    1 if entry.locked else 0,
                    1 if entry.reviewed else 0,
                    entry.id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_entry(self, entry_id: str) -> bool:
        """Delete an entry by ID. Refuses to delete locked entries."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM entries WHERE id = ? AND locked = 0", (entry_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_entries(self, entry_ids: list[str]) -> dict:
        """Delete multiple entries, skipping locked ones. Returns deletion details."""
        if not entry_ids:
            return {"deleted": 0, "skipped_locked": 0}
        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(entry_ids))
            cursor = conn.execute(
                f"SELECT COUNT(*) as cnt FROM entries WHERE id IN ({placeholders}) AND locked = 1",
                entry_ids,
            )
            skipped = cursor.fetchone()["cnt"]
            cursor = conn.execute(
                f"DELETE FROM entries WHERE id IN ({placeholders}) AND locked = 0",
                entry_ids,
            )
            conn.commit()
            return {"deleted": cursor.rowcount, "skipped_locked": skipped}

    def toggle_entry_field(self, entry_id: str, field: str, value: bool) -> bool:
        """Toggle a boolean field (locked/reviewed) on an entry."""
        if field not in ("locked", "reviewed"):
            raise ValueError(f"Cannot toggle field: {field}")
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE entries SET {field} = ?, updated_at = ? WHERE id = ?",
                (1 if value else 0, datetime.utcnow().isoformat(), entry_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_totals(self) -> dict:
        """Calculate totals using SQL aggregation (fast!)."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    COALESCE(SUM(sel), 0) as sel,
                    COALESCE(SUM(mel), 0) as mel,
                    COALESCE(SUM(day), 0) as day,
                    COALESCE(SUM(night), 0) as night,
                    COALESCE(SUM(cross_country), 0) as cross_country,
                    COALESCE(SUM(actual_inst), 0) as actual_inst,
                    COALESCE(SUM(simulated_inst), 0) as simulated_inst,
                    COALESCE(SUM(num_inst_app), 0) as num_inst_app,
                    COALESCE(SUM(landings_day), 0) as landings_day,
                    COALESCE(SUM(landings_night), 0) as landings_night,
                    COALESCE(SUM(pic), 0) as pic,
                    COALESCE(SUM(sic), 0) as sic,
                    COALESCE(SUM(dual_recd), 0) as dual_recd,
                    COALESCE(SUM(dual_given), 0) as dual_given,
                    COALESCE(SUM(solo), 0) as solo,
                    COALESCE(SUM(sim), 0) as sim,
                    COALESCE(SUM(total_duration), 0) as total_duration,
                    COUNT(*) as flights
                FROM entries
            """)
            row = cursor.fetchone()
            return dict(row)

    def get_most_recent_flight_date(self) -> Optional[datetime]:
        """Get the most recent flight date."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT date FROM entries
                WHERE date != '' AND date IS NOT NULL
                ORDER BY
                    CASE
                        WHEN date LIKE '%/%/%'
                        THEN substr(date, instr(date, '/') + instr(substr(date, instr(date, '/') + 1), '/') + 1) || '-' ||
                             printf('%02d', CAST(substr(date, 1, instr(date, '/') - 1) AS INTEGER)) || '-' ||
                             printf('%02d', CAST(substr(date, instr(date, '/') + 1, instr(substr(date, instr(date, '/') + 1), '/') - 1) AS INTEGER))
                        ELSE date
                    END DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row and row["date"]:
                try:
                    return datetime.strptime(row["date"], "%m/%d/%Y")
                except ValueError:
                    pass
        return None

    def get_existing_keys(self) -> set[str]:
        """Get set of date|from|to keys for duplicate detection."""
        keys = set()
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT date, route_from, route_to FROM entries")
            for row in cursor.fetchall():
                key = f"{row['date']}|{row['route_from']}|{row['route_to']}"
                keys.add(key)
        return keys

    def bulk_insert(self, entries: list[LogbookEntry]) -> int:
        """Bulk insert entries (for migration). Returns count inserted."""
        count = 0
        with self._get_connection() as conn:
            for entry in entries:
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO entries (
                            id, date, aircraft_model, aircraft_ident,
                            route_from, route_to, route_via, sel, mel, day, night,
                            cross_country, actual_inst, simulated_inst,
                            num_inst_app, landings_day, landings_night,
                            pic, sic, dual_recd, dual_given, solo, sim,
                            total_duration, duration_estimated, remarks,
                            created_at, updated_at, locked, reviewed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            entry.id,
                            entry.date,
                            entry.aircraft_model,
                            entry.aircraft_ident,
                            entry.route_from,
                            entry.route_to,
                            entry.route_via,
                            entry.sel,
                            entry.mel,
                            entry.day,
                            entry.night,
                            entry.cross_country,
                            entry.actual_inst,
                            entry.simulated_inst,
                            entry.num_inst_app,
                            entry.landings_day,
                            entry.landings_night,
                            entry.pic,
                            entry.sic,
                            entry.dual_recd,
                            entry.dual_given,
                            entry.solo,
                            entry.sim,
                            entry.total_duration,
                            1 if entry.duration_estimated else 0,
                            entry.remarks,
                            entry.created_at,
                            entry.updated_at,
                            1 if entry.locked else 0,
                            1 if entry.reviewed else 0,
                        ),
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    pass  # Skip duplicates
            conn.commit()
        return count

    def clear_all(self):
        """Clear all entries (for reload from Sheets)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM entries")
            conn.commit()

    def count(self) -> int:
        """Get total entry count."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM entries")
            return cursor.fetchone()["cnt"]

    def _row_to_entry(self, row: sqlite3.Row) -> LogbookEntry:
        """Convert a database row to LogbookEntry."""
        return LogbookEntry(
            id=row["id"],
            date=row["date"] or "",
            aircraft_model=row["aircraft_model"] or "",
            aircraft_ident=row["aircraft_ident"] or "",
            route_from=row["route_from"] or "",
            route_to=row["route_to"] or "",
            route_via=row["route_via"] or "" if "route_via" in row.keys() else "",
            sel=float(row["sel"] or 0),
            mel=float(row["mel"] or 0),
            day=float(row["day"] or 0),
            night=float(row["night"] or 0),
            cross_country=float(row["cross_country"] or 0),
            actual_inst=float(row["actual_inst"] or 0),
            simulated_inst=float(row["simulated_inst"] or 0),
            num_inst_app=int(row["num_inst_app"] or 0),
            landings_day=int(row["landings_day"] or 0),
            landings_night=int(row["landings_night"] or 0),
            pic=float(row["pic"] or 0),
            sic=float(row["sic"] or 0),
            dual_recd=float(row["dual_recd"] or 0),
            dual_given=float(row["dual_given"] or 0),
            solo=float(row["solo"] or 0),
            sim=float(row["sim"] or 0),
            total_duration=float(row["total_duration"] or 0),
            duration_estimated=bool(row["duration_estimated"]),
            remarks=row["remarks"] or "",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            locked=bool(row["locked"]) if row["locked"] is not None else False,
            reviewed=bool(row["reviewed"]) if row["reviewed"] is not None else True,
        )
