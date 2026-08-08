# services/db_backup.py
"""Daily SQLite backup, uploaded to Google Drive via rclone.

Runs alongside the EOD report (runners/paper_trading/eod_scheduler.py) at
settings.eod_report_time — trades are the most valuable thing in this app,
and the OneDrive-synced quantpulse.db has already been corrupted once by a
live SQLite write colliding with cloud sync. To avoid repeating that: never
hand the live file to anything. SQLite's own backup API produces a
consistent point-in-time copy while the app keeps writing to the live db,
and only that already-closed copy gets uploaded.
"""

import os
import sqlite3
import subprocess
from datetime import date
from typing import Optional

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Only sqlite database URLs are backed up, got: {database_url}")
    return database_url[len(prefix):]


def snapshot_database(database_url: str, backup_dir: str, backup_date: Optional[date] = None) -> str:
    """Writes backup_dir/quantpulse_<YYYYMMDD>.db via SQLite's backup API
    (safe to call while the live db is being written to) and returns its
    path. Re-running for the same day overwrites that day's snapshot.
    """
    backup_date = backup_date or date.today()
    os.makedirs(backup_dir, exist_ok=True)
    dest_path = os.path.join(backup_dir, f"quantpulse_{backup_date.strftime('%Y%m%d')}.db")

    source = sqlite3.connect(_sqlite_path(database_url))
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()

    return dest_path


def upload_to_drive(local_path: str, remote: str) -> None:
    """`rclone copy` the already-written snapshot up to Google Drive."""
    result = subprocess.run(
        ["rclone", "copy", local_path, remote],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rclone copy failed: {result.stderr.strip()}")


def backup_database_to_drive(database_url: str, backup_dir: str, remote: str) -> str:
    """Snapshot + upload. Returns the remote destination for logging."""
    local_path = snapshot_database(database_url, backup_dir)
    upload_to_drive(local_path, remote)
    destination = f"{remote}/{os.path.basename(local_path)}"
    logger.info("Database backed up to %s", destination)
    return destination
