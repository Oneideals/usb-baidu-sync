"""SQLite database engine for tracking USB volumes and incremental file fingerprints."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from usb_baidu_sync.fingerprint import calculate_fast_hash


class SyncDatabase:
    """Manages SQLite tables for volume registry and file upload fingerprints."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            base_dir = Path.home() / "Library" / "Application Support" / "USBBaiduSync"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "sync_records.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Create tables and indices if not existing."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS usb_volumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    volume_uuid TEXT UNIQUE,
                    volume_name TEXT NOT NULL,
                    mount_path TEXT NOT NULL,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_synced_at TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS file_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    volume_uuid TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    fast_hash TEXT NOT NULL,
                    remote_path TEXT NOT NULL,
                    upload_status TEXT NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT,
                    UNIQUE(volume_uuid, rel_path)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_volume_rel
                ON file_fingerprints(volume_uuid, rel_path)
                """
            )
            conn.commit()

    def upsert_volume(self, volume_uuid: str, volume_name: str, mount_path: str) -> None:
        """Record or update USB volume information."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usb_volumes (volume_uuid, volume_name, mount_path, last_synced_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(volume_uuid) DO UPDATE SET
                    volume_name = excluded.volume_name,
                    mount_path = excluded.mount_path,
                    last_synced_at = CURRENT_TIMESTAMP
                """,
                (volume_uuid, volume_name, mount_path),
            )
            conn.commit()

    def get_file_record(self, volume_uuid: str, rel_path: str) -> dict[str, Any] | None:
        """Fetch existing fingerprint record for a file in a volume."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM file_fingerprints
                WHERE volume_uuid = ? AND rel_path = ?
                """,
                (volume_uuid, rel_path),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def evaluate_file(
        self,
        volume_uuid: str,
        rel_path: str,
        file_path: Path,
        size: int,
        mtime: float,
    ) -> tuple[bool, str]:
        """Perform two-level incremental evaluation.

        Returns (need_upload, reason):
        - (True, "NEW_FILE"): Never uploaded before
        - (True, "PREVIOUS_FAILED"): Uploaded previously but failed/interrupted
        - (False, "METADATA_MATCH"): Size and mtime match previous SUCCESS record
        - (False, "HASH_MATCH"): Content hash matches previous record (mtime updated)
        - (True, "HASH_MISMATCH"): Content has changed
        """
        record = self.get_file_record(volume_uuid, rel_path)
        if not record:
            return True, "NEW_FILE"

        if record["upload_status"] != "SUCCESS":
            return True, "PREVIOUS_FAILED"

        # Tier 1: Fast metadata check (size & mtime within 1 second tolerance)
        if record["file_size"] == size and abs(record["mtime"] - mtime) < 1.0:
            return False, "METADATA_MATCH"

        # Tier 2: Content hash verification
        current_hash = calculate_fast_hash(file_path, size)
        if current_hash == record["fast_hash"]:
            # Content didn't change, only mtime touched -> update mtime in DB and skip
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE file_fingerprints
                    SET mtime = ?
                    WHERE id = ?
                    """,
                    (mtime, record["id"]),
                )
                conn.commit()
            return False, "HASH_MATCH"

        return True, "HASH_MISMATCH"

    def record_upload_success(
        self,
        volume_uuid: str,
        volume_name: str,
        rel_path: str,
        file_size: int,
        mtime: float,
        fast_hash: str,
        remote_path: str,
    ) -> None:
        """Record a successfully uploaded file into fingerprints."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO file_fingerprints (
                    volume_uuid, rel_path, file_size, mtime,
                    fast_hash, remote_path, upload_status,
                    uploaded_at, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(volume_uuid, rel_path) DO UPDATE SET
                    file_size = excluded.file_size,
                    mtime = excluded.mtime,
                    fast_hash = excluded.fast_hash,
                    remote_path = excluded.remote_path,
                    upload_status = 'SUCCESS',
                    uploaded_at = CURRENT_TIMESTAMP,
                    error_message = NULL
                """,
                (volume_uuid, rel_path, file_size, mtime, fast_hash, remote_path),
            )
            conn.commit()

    def record_upload_status(
        self,
        volume_uuid: str,
        rel_path: str,
        status: str,
        error_msg: str | None = None,
        remote_path: str = "",
        file_size: int = 0,
        mtime: float = 0.0,
        fast_hash: str = "",
    ) -> None:
        """Record failed or interrupted upload status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO file_fingerprints (
                    volume_uuid, rel_path, file_size, mtime,
                    fast_hash, remote_path, upload_status,
                    uploaded_at, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(volume_uuid, rel_path) DO UPDATE SET
                    upload_status = excluded.upload_status,
                    error_message = excluded.error_message
                """,
                (volume_uuid, rel_path, file_size, mtime, fast_hash, remote_path, status, error_msg),
            )
            conn.commit()
