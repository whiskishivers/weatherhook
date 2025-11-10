## Weatherhook

Post U.S. weather alerts to your discord channel using the channel's webhook URL.

### Required packages
* discordpy
* aiohttp

### Setup
1. Create the `zones.txt` file in the script directory with one forecast/county zone ID per line.
Zone IDs can be found at the [NWS Alerts](https://alerts.weather.gov) page.
2. Set `WEBHOOK_URL` environment variable to your channel's webhook url.
   Webhooks can be created through Discord -> Server Settings -> Integrations -> Webhooks.
3. Run bot.py.

### Features
* Posts alerts that are moderate, severe, or extreme in severity
* Automatic deletion of canceled or expired messages
* Dynamic update interval based on alert urgency
* Message embeds contain alert info, timelines, and are colored based on severity


