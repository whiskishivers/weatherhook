import asyncio
import logging
import os
import random
import time
from typing import Dict, List

import aiohttp
import discord

import wapi


class AlertTracker(Dict[str, wapi.Alert]):
    """Dict wrapper for tracking active alerts."""

    def new_alerts(self, active_alerts: List[wapi.Alert]) -> list[wapi.Alert]:
        """Determine which active alerts are new (not yet tracked)."""
        new_ids = {alert.id for alert in active_alerts} - self.keys()
        return [i for i in active_alerts if i.id in new_ids]

    def expired_alerts(self, active_alerts: List[wapi.Alert]) -> list[wapi.Alert]:
        """Determine which tracked alerts are no longer active."""
        expired_ids = self.keys() - {alert.id for alert in active_alerts}
        return [i for i in self.values() if i.id in expired_ids]

    def add_alert(self, alert: wapi.Alert):
        self[alert.id] = alert

    def remove_alert(self, alert: wapi.Alert):
        return self.pop(alert.id)

    def has_urgent_alerts(self):
        for i in self.values():
            if i.urgency == "Immediate" or i.severity == "Extreme":
                return True
        return False


async def post_alert(tracker: AlertTracker, webhook: discord.Webhook, alert: wapi.Alert):
    """ Post message and add alert to tracker """
    message = await webhook.send(content=f"{alert.headline}", embed=alert.embed, username=alert.senderName, wait=True)
    logging.info(f"Posted: {alert.id}")
    alert.message_id = message.id
    tracker.add_alert(alert)


async def delete_alert(tracker: AlertTracker, webhook: discord.Webhook, alert: wapi.Alert) -> None:
    """ Delete discord message and remove alert from tracker """
    try:
        await webhook.delete_message(int(alert.message_id))
        logging.info(f"Deleted: {alert.id}")
        tracker.remove_alert(alert)
    except discord.NotFound:
        logging.warning(f"Discord message missing when deleting alert: {alert.event}")


async def discord_sync(active_alerts: List[wapi.Alert], tracker: AlertTracker):
    """ Post and delete alerts based on activity """
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
        tasks = []
        # Delete old alerts
        for alert in tracker.expired_alerts(active_alerts):
            tasks.append(delete_alert(tracker, webhook, alert))

        # Post new alerts
        for alert in tracker.new_alerts(active_alerts):
            tasks.append(post_alert(tracker, webhook, alert))

        await asyncio.gather(*tasks)

        if len(tasks):
            print(f"{time.strftime('%H:%M:%S')} Synced {len(tasks)} alert messages.")


async def fetch_alerts(zones_file: str, client: wapi.Client) -> List[wapi.Alert]:
    """ Get active alerts from NWS API """
    try:
        with open(zones_file, "r") as f:
            zones = ",".join([i.strip() for i in f.readlines() if not i.strip().startswith("#") and len(i.strip())])
        if not zones:
            logging.warning("No zones have been loaded from zones.txt.")
            return []

        alerts = await client.alerts.active(zone=zones, severity="Moderate,Severe,Extreme,Unknown")
        alerts.sort(key=lambda x: (x.onset, x.sent))
        return alerts

    except FileNotFoundError:
        logging.warning(f"Could not find the file '{zones_file}'.")
        return []


async def main():
    w_client = wapi.client
    tracker = AlertTracker()
    zones_file = "zones.txt"
    active_alerts: list[wapi.Alert] | None = None

    while True:
        # Get active alerts
        try:
            active_alerts = await fetch_alerts(zones_file, w_client)
        except aiohttp.ClientResponseError as e:
            logging.error("Got response error when fetching alerts.")
            print(e)
        except aiohttp.ConnectionTimeoutError:
            logging.error(f"Connection timed out when fetching alerts.")

        # Synchronize tracked alerts and adjust sleep timer based on alert urgency
        try:
            await discord_sync(active_alerts, tracker)

            if tracker.has_urgent_alerts():
                sleep_timer = 60.0 - random.uniform(10.0, 0.0)
            else:
                sleep_timer = 300.0 - random.uniform(15.0, 0.0)
            logging.info(f"Sleep timer: {sleep_timer}")
            await asyncio.sleep(sleep_timer)

        except asyncio.CancelledError:
            break


if __name__ == "__main__":
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    LOG_LVL = os.environ.get("LOG_LVL", "30")
    logging.basicConfig(level=int(LOG_LVL), format='%(asctime)s - %(levelname)s - %(message)s')
    if WEBHOOK_URL is None:
        print("WEBHOOK_URL environment variable is not set.")
        logging.critical("WEBHOOK_URL environment var is missing.")
    else:
        asyncio.run(main())
