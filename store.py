import logging
import os
import stat

import aiosqlite

import wapi

DB_FILENAME = "alerts.db"


async def init_db(db_path: str) -> None:
    """Initialize the database and create the alerts table if it doesn't exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id       TEXT PRIMARY KEY,
                discord_msg_id INTEGER NOT NULL,
                headline       TEXT
            )
        """)
        await db.commit()

    # Restrict file permissions to owner read/write only (600)
    os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)


async def load_alerts(db_path: str) -> dict[str, wapi.Alert]:
    """Load persisted alerts from the database into a dict keyed by alert ID."""
    tracked = {}
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT alert_id, discord_msg_id, headline FROM alerts") as cursor:
            async for row in cursor:
                alert_id, discord_msg_id, headline = row
                alert = wapi.Alert(id=alert_id, headline=headline)
                alert.discord_msg_id = discord_msg_id
                tracked[alert_id] = alert
    return tracked


async def save_alert(db_path: str, alert: wapi.Alert) -> None:
    """Persist a newly posted alert to the database."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO alerts (alert_id, discord_msg_id, headline) VALUES (?, ?, ?)",
                (alert.id, alert.discord_msg_id, alert.headline),
            )
            await db.commit()
    except aiosqlite.Error as e:
        logging.error(f"Failed to save alert {alert.id} to DB: {e}")


async def remove_alert(db_path: str, alert_id: str) -> None:
    """Remove an alert from the database."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM alerts WHERE alert_id = ?", (alert_id,))
            await db.commit()
    except aiosqlite.Error as e:
        logging.error(f"Failed to remove alert {alert_id} from DB: {e}")