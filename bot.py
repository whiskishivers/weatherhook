import asyncio
import logging
import os
import random
import time
from typing import Dict, List, NamedTuple

import aiohttp
import discord
from dotenv import load_dotenv

import wapi
import yaml


class Config(NamedTuple):
    zones: str
    severity: str
    log_level: int
    sleep_normal: float
    sleep_urgent: float


class AlertTracker(dict):
    """Dict wrapper for tracking active alerts."""

    def compare(self, active_alerts: list) -> tuple:
        """Determine which active alerts are new (not yet tracked) or expired (not in active alerts)."""
        new_ids = {alert.id for alert in active_alerts} - self.keys()
        new = [i for i in active_alerts if i.id in new_ids]

        expired_ids = self.keys() - {alert.id for alert in active_alerts}
        expired = [i for i in self.values() if i.id in expired_ids]

        return new, expired

    def has_urgent_alerts(self) -> bool:
        """True if any urgent alerts are tracked"""
        return any(alert.urgency == "Immediate" for alert in self.values())


def load_config(config_filepath: str) -> Config:
    """Load and validate configuration from YAML file."""
    with open(config_filepath, "r") as f:
        config = yaml.safe_load(f)

    zones = ",".join(config["filter"]["zones"])

    raw_severity = config["filter"].get("severity")
    severity = ",".join(raw_severity) if raw_severity else ""

    raw_log_level = config.get("log_level", "WARNING")
    log_level = getattr(logging, str(raw_log_level).upper(), logging.WARNING)
    sleep_normal = float(config["sleep_interval"]["normal"])
    sleep_urgent = float(config["sleep_interval"]["urgent"])

    return Config(
        zones=zones,
        severity=severity,
        log_level=log_level,
        sleep_normal=sleep_normal,
        sleep_urgent=sleep_urgent,
    )


async def post_alert(tracker: AlertTracker, webhook: discord.Webhook, alert: wapi.Alert):
    """Post discord message and track the alert."""
    try:
        message = await webhook.send(content=f"{alert.headline}", embed=alert.embed, wait=True)
        print(f"[{time.strftime('%H:%M:%S')}] [+] Posted  : {alert.headline}")
        logging.info(f"Posted: {alert}")
        alert.discord_msg_id = message.id
        tracker[alert.id] = alert
    except discord.HTTPException as e:
        print(f"[{time.strftime('%H:%M:%S')}] [!] Failed to post: {alert.headline} — {e.text}")
        logging.warning(f"Could not post {alert}: {e.text}")


async def delete_alert(tracker: AlertTracker, webhook: discord.Webhook, alert: wapi.Alert) -> None:
    """Delete message."""
    try:
        await webhook.delete_message(int(alert.discord_msg_id))
        print(f"[{time.strftime('%H:%M:%S')}] [-] Expired : {alert.headline}")
        logging.info(f"Deleted: {alert}")
    except discord.HTTPException as e:
        print(f"[{time.strftime('%H:%M:%S')}] [!] Failed to delete: {alert.headline} — {e.text}")
        logging.warning(f"Could not delete {alert}: {e.text}")


async def discord_sync(active_alerts: list, tracker: AlertTracker):
    """Post new alerts and delete inactive alerts."""
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
        tasks = []
        new_alerts, expired_alerts = tracker.compare(active_alerts)

        for alert in expired_alerts:
            tasks.append(delete_alert(tracker, webhook, alert))
            tracker.pop(alert.id)

        for alert in new_alerts:
            tasks.append(post_alert(tracker, webhook, alert))

        await asyncio.gather(*tasks)


async def fetch_alerts(config: Config, client: wapi.Client) -> List[wapi.Alert]:
    """Get active alerts from NWS API."""
    if not config.zones:
        logging.warning("Nothing to do! No zones defined in config.yaml.")
        return []

    kwargs = {"zone": config.zones}
    if config.severity:
        kwargs["severity"] = config.severity
    alerts = await client.alerts.active(**kwargs)
    return sorted(alerts, key=lambda x: x.sent)


async def main():
    nws_client = wapi.nws_client
    tracker = AlertTracker()
    config_file = os.path.join(SCRIPT_DIR, "config.yaml")

    while True:
        # Reload config on every poll to pick up live edits
        try:
            config = load_config(config_file)
        except FileNotFoundError:
            logging.critical(f"Could not find config file: {config_file}")
            await asyncio.sleep(30.0)
            continue
        except (KeyError, TypeError, ValueError) as e:
            logging.critical(f"Invalid config: {e}")
            await asyncio.sleep(30.0)
            continue

        # Apply log level from config
        logging.getLogger().setLevel(config.log_level)

        # Get active alerts
        active_alerts = None
        try:
            active_alerts = await fetch_alerts(config, nws_client)
        except aiohttp.ClientResponseError as e:
            print(f"[{time.strftime('%H:%M:%S')}] [!] API error fetching alerts: {e}")
            logging.error("Got response error when fetching alerts.")
        except aiohttp.ConnectionTimeoutError:
            print(f"[{time.strftime('%H:%M:%S')}] [!] Connection timed out fetching alerts.")
            logging.error("Connection timed out when fetching alerts.")

        if active_alerts is None:
            print(f"[{time.strftime('%H:%M:%S')}] [!] Could not retrieve alerts. Retrying in 30s.")
            await asyncio.sleep(30.0)
            continue

        # Synchronize tracked alerts and adjust sleep timer based on alert urgency
        try:
            await discord_sync(active_alerts, tracker)
            tracked = len(tracker)
            urgent = tracker.has_urgent_alerts()
            if tracker.has_urgent_alerts():
                sleep_timer = config.sleep_urgent + random.uniform(0.0, 1.0)
            else:
                sleep_timer = config.sleep_normal + random.uniform(0.0, 1.0)
            status = "URGENT" if urgent else "normal"
            print(f"[{time.strftime('%H:%M:%S')}] Tracking {tracked} alert(s). Next poll in {sleep_timer:.0f}s [{status}].")
            logging.info(f"Sleeping {sleep_timer:.2f}...")
            await asyncio.sleep(sleep_timer)

        except asyncio.CancelledError:
            break


if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

    # Load .env from the project directory
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if not os.path.exists(env_path):
        print(f"[FATAL] .env file not found at {env_path}")
        raise SystemExit(1)
    load_dotenv(env_path)

    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

    # Bootstrap logging at WARNING until config is loaded on first loop iteration
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

    if WEBHOOK_URL is None:
        print("[FATAL] WEBHOOK_URL is not set in .env.")
        logging.critical("WEBHOOK_URL is missing from .env.")
        raise SystemExit(1)

    # Load config once at startup for a summary printout
    config_file = os.path.join(SCRIPT_DIR, "config.yaml")
    try:
        _cfg = load_config(config_file)
        print(f"[startup] NWS Alert Bot starting.")
        print(f"[startup] Zones    : {_cfg.zones}")
        print(f"[startup] Severity : {_cfg.severity}")
        print(f"[startup] Poll interval — normal: {_cfg.sleep_normal}s  urgent: {_cfg.sleep_urgent}s")
        print(f"[startup] Log level: {logging.getLevelName(_cfg.log_level)}")
    except Exception as e:
        print(f"[FATAL] Could not load config at startup: {e}")
        raise SystemExit(1)

    asyncio.run(main())