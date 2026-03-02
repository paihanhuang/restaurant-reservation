"""SQLite database provider implementation."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.providers.base import Database


class SQLiteDatabase(Database):
    """SQLite implementation of the Database interface."""

    def __init__(self, db_path: str = "data/reservations.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a new SQLite connection with row factory."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def initialize(self) -> None:
        """Run migration scripts to create/update schema."""
        migration_dir = Path(__file__).parent.parent / "db" / "migrations"
        conn = self._get_connection()
        try:
            for sql_file in sorted(migration_dir.glob("*.sql")):
                sql = sql_file.read_text()
                conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()

    async def create_reservation(self, reservation: dict) -> None:
        conn = self._get_connection()
        try:
            cols = ", ".join(reservation.keys())
            placeholders = ", ".join(["?"] * len(reservation))
            conn.execute(
                f"INSERT INTO reservations ({cols}) VALUES ({placeholders})",
                list(reservation.values()),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_reservation(self, reservation_id: str) -> dict | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    async def update_reservation(self, reservation_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [reservation_id]
        conn = self._get_connection()
        try:
            conn.execute(
                f"UPDATE reservations SET {set_clause} WHERE reservation_id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    async def list_reservations_by_status(
        self, status: str, older_than_minutes: int | None = None
    ) -> list[dict]:
        conn = self._get_connection()
        try:
            if older_than_minutes is not None:
                cutoff = (datetime.utcnow() - timedelta(minutes=older_than_minutes)).isoformat()
                rows = conn.execute(
                    "SELECT * FROM reservations WHERE status = ? AND updated_at < ?",
                    (status, cutoff),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM reservations WHERE status = ?",
                    (status,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def log_state_transition(self, transition: dict) -> None:
        conn = self._get_connection()
        try:
            cols = ", ".join(transition.keys())
            placeholders = ", ".join(["?"] * len(transition))
            conn.execute(
                f"INSERT INTO state_transitions ({cols}) VALUES ({placeholders})",
                list(transition.values()),
            )
            conn.commit()
        finally:
            conn.close()

    async def log_call(self, call_log: dict) -> None:
        conn = self._get_connection()
        try:
            cols = ", ".join(call_log.keys())
            placeholders = ", ".join(["?"] * len(call_log))
            conn.execute(
                f"INSERT INTO call_logs ({cols}) VALUES ({placeholders})",
                list(call_log.values()),
            )
            conn.commit()
        finally:
            conn.close()

    async def append_transcript_turn(
        self, reservation_id: str, call_sid: str, turn: dict
    ) -> None:
        conn = self._get_connection()
        try:
            record = {
                "reservation_id": reservation_id,
                "call_sid": call_sid,
                **turn,
            }
            cols = ", ".join(record.keys())
            placeholders = ", ".join(["?"] * len(record))
            conn.execute(
                f"INSERT INTO transcript_turns ({cols}) VALUES ({placeholders})",
                list(record.values()),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_transcript(self, reservation_id: str) -> list[dict]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM transcript_turns WHERE reservation_id = ? ORDER BY turn_number",
                (reservation_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def list_all_reservations(self) -> list[dict]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM reservations ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
