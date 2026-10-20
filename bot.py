"""Weatherhook: post active NWS alerts for your zones to a Discord webhook, and delete them when they expire."""
import asyncio
import datetime as dt
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import NamedTuple

import aiohttp
import discord
import yaml
from dotenv import load_dotenv

import store

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.yaml")
DB_PATH = os.path.join(SCRIPT_DIR, "alerts.db")

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
HEADERS = {"User-Agent": "python-aiohttp | Discord weather bot"}
RETRY_DELAY = 30.0  # seconds to wait after a failed poll or a bad config
MIN_SLEEP = 5.0     # never poll more often than this

COLORS = {
    ("Severe", "Expected"): discord.Color.dark_gold(),
    ("Severe", "Future"): discord.Color.dark_gold(),
    ("Severe", "Immediate"): discord.Color.gold(),
    ("Extreme", "Expected"): discord.Color.dark_red(),
    ("Extreme", "Future"): discord.Color.dark_red(),
    ("Extreme", "Immediate"): discord.Color.red(),
}


def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ─── Config ──────────────────────────────────────────────────────────────────

class Config(NamedTuple):
    zones: str
    severity: str
    log_level: int
    sleep_normal: float
    sleep_urgent: float


def load_config(path: str) -> Config:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    return Config(
        zones=",".join(cfg["zones"]),
        severity=",".join(cfg.get("severity") or []),
        log_level=getattr(logging, str(cfg.get("log_level", "WARNING")).upper(), logging.WARNING),
        sleep_normal=float(cfg["sleep_interval"]["normal"]),
        sleep_urgent=float(cfg["sleep_interval"]["urgent"]),
    )


# ─── Alerts ──────────────────────────────────────────────────────────────────

def _parse_time(value: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _clean(text: str | None) -> str | None:
    """Fix NWS formatting quirks: runs of spaces, extra blank lines, mid-sentence line breaks."""
    if not text:
        return text
    text = re.sub(r"[ \t]{4,}", ", ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<=[^.!?:\n])[ \t]*\n[ \t]*(?=[a-z])", " ", text)
    return text.strip()


def _office(props: dict) -> str | None:
    """Issuing office code (e.g. 'AKQ') from the WMO identifier ('WWUS51 KAKQ 201530')."""
    ident = (props.get("parameters") or {}).get("WMOidentifier") or []
    parts = ident[0].split(" ") if ident else []
    return parts[1][-3:] if len(parts) >= 2 else None


@dataclass
class Alert:
    id: str
    event: str | None
    headline: str | None
    description: str | None
    instruction: str | None
    response: str | None
    severity: str | None
    urgency: str | None
    sender_name: str | None
    sent: dt.datetime | None
    onset: dt.datetime | None
    ends: dt.datetime | None
    office: str | None

    @classmethod
    def from_feature(cls, feature: dict) -> "Alert":
        p = feature["properties"]
        return cls(
            id=feature["id"],
            event=p.get("event"),
            headline=p.get("headline"),
            description=_clean(p.get("description")),
            instruction=_clean(p.get("instruction")),
            response=p.get("response"),
            severity=p.get("severity"),
            urgency=p.get("urgency"),
            sender_name=p.get("senderName"),
            sent=_parse_time(p.get("sent")),
            onset=_parse_time(p.get("onset")),
            ends=_parse_time(p.get("ends")),
            office=_office(p),
        )

    @property
    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.event,
            description=(self.description or "")[:4096],
            color=COLORS.get((self.severity, self.urgency), discord.Color.blue()),
            timestamp=self.sent,
        )
        if self.instruction and self.response in ("Evacuate", "Shelter"):
            embed.add_field(name="Instructions", value=self.instruction[:1024], inline=False)
        if self.onset:
            ts = int(self.onset.timestamp())
            embed.add_field(name="Onset", value=f"<t:{ts}:d> <t:{ts}:t>\n<t:{ts}:R>")
        if self.ends:
            ts = int(self.ends.timestamp())
            embed.add_field(name="End", value=f"<t:{ts}:d> <t:{ts}:t>\n<t:{ts}:R>")
        embed.add_field(name="Severity", value=f"{self.severity} - {self.urgency}")
        if self.office:
            embed.set_author(name=self.sender_name or "NWS", url=f"https://www.weather.gov/{self.office.lower()}")
        return embed


async def fetch_alerts(session: aiohttp.ClientSession, config: Config) -> list[Alert]:
    """Get active alerts for the configured zones, oldest first."""
    params = {"zone": config.zones}
    if config.severity:
        params["severity"] = config.severity

    async with session.get(NWS_ALERTS_URL, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()

    alerts = [Alert.from_feature(f) for f in data.get("features", [])]
    return sorted(alerts, key=lambda a: a.sent or dt.datetime.min.replace(tzinfo=dt.timezone.utc))


# ─── Discord sync ────────────────────────────────────────────────────────────

async def post_alert(webhook: discord.Webhook, alert: Alert, tracked: dict[str, int]) -> None:
    try:
        message = await webhook.send(content=alert.headline or alert.event, embed=alert.embed, wait=True)
    except discord.HTTPException as e:
        logging.warning(f"Could not post {alert.event}: {e.text}")
        return
    tracked[alert.id] = message.id
    store.save(DB_PATH, alert.id, message.id)
    say(f"[+] Posted  : {alert.headline or alert.event}")


async def delete_alert(webhook: discord.Webhook, alert_id: str, tracked: dict[str, int]) -> None:
    try:
        await webhook.delete_message(tracked[alert_id])
        say(f"[-] Deleted : {alert_id}")
    except discord.HTTPException as e:
        logging.warning(f"Could not delete message for {alert_id}: {e.text}")
    # Stop tracking either way; if the message is already gone there's nothing left to retry.
    del tracked[alert_id]
    store.remove(DB_PATH, alert_id)


async def sync(webhook: discord.Webhook, alerts: list[Alert], tracked: dict[str, int]) -> None:
    """Delete messages for expired alerts and post messages for new ones."""
    active_ids = {a.id for a in alerts}
    for alert_id in [i for i in tracked if i not in active_ids]:
        await delete_alert(webhook, alert_id, tracked)
    for alert in alerts:
        if alert.id not in tracked:
            await post_alert(webhook, alert, tracked)


# ─── Main loop ───────────────────────────────────────────────────────────────

async def main(webhook_url: str) -> None:
    tracked = store.load(DB_PATH)
    if tracked:
        say(f"[startup] Restored {len(tracked)} alert(s) from previous session.")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)

        while True:
            loop_start = time.monotonic()

            # Config is re-read every poll, so edits take effect without a restart.
            try:
                config = load_config(CONFIG_PATH)
            except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as e:
                logging.critical(f"Invalid or missing config ({CONFIG_PATH}): {e!r}")
                await asyncio.sleep(RETRY_DELAY)
                continue
            logging.getLogger().setLevel(config.log_level)

            try:
                alerts = await fetch_alerts(session, config)
                await sync(webhook, alerts, tracked)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                logging.error(f"Poll failed ({e!r}). Retrying in {RETRY_DELAY:.0f}s.")
                await asyncio.sleep(RETRY_DELAY + random.uniform(0.0, 1.0))
                continue

            urgent = any(a.urgency == "Immediate" for a in alerts)
            base_sleep = config.sleep_urgent if urgent else config.sleep_normal
            sleep_for = max(MIN_SLEEP, base_sleep - (time.monotonic() - loop_start))

            next_poll = time.strftime("%H:%M:%S", time.localtime(time.time() + sleep_for))
            say(f"Tracking {len(tracked)} alert(s). Next poll at {next_poll} [{'urgent' if urgent else 'normal'}].")
            await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        raise SystemExit("[FATAL] WEBHOOK_URL is not set. Put it in a .env file next to bot.py.")

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

    try:
        cfg = load_config(CONFIG_PATH)
    except Exception as e:
        raise SystemExit(f"[FATAL] Could not load {CONFIG_PATH}: {e!r}")
    say("[startup] Weatherhook starting.")
    say(f"[startup] Zones: {cfg.zones}  Severity: {cfg.severity or 'all'}")
    say(f"[startup] Poll interval - normal: {cfg.sleep_normal}s  urgent: {cfg.sleep_urgent}s")

    try:
        asyncio.run(main(webhook_url))
    except KeyboardInterrupt:
        say("Bot shut down.")