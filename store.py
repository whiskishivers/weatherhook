"""Tiny SQLite store mapping each NWS alert ID to the Discord message announcing it.

This lets the bot delete the right messages after a restart instead of reposting everything.
"""
import logging
import os
import sqlite3
import stat
from contextlib import closing


def load(db_path: str) -> dict[str, int]:
    """Create the table if needed and return {alert_id: discord_msg_id}."""
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS alerts (alert_id TEXT PRIMARY KEY, discord_msg_id INTEGER NOT NULL)"
        )
        db.commit()
        rows = db.execute("SELECT alert_id, discord_msg_id FROM alerts").fetchall()
    os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)  # owner read/write only
    return dict(rows)


def save(db_path: str, alert_id: str, discord_msg_id: int) -> None:
    try:
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO alerts (alert_id, discord_msg_id) VALUES (?, ?)",
                (alert_id, discord_msg_id),
            )
    except sqlite3.Error as e:
        logging.error(f"Failed to save alert {alert_id} to DB: {e}")


def remove(db_path: str, alert_id: str) -> None:
    try:
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("DELETE FROM alerts WHERE alert_id = ?", (alert_id,))
    except sqlite3.Error as e:
        logging.error(f"Failed to remove alert {alert_id} from DB: {e}")