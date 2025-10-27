## Weatherhook

Post U.S. weather alerts to your discord channel using the channel's webhook URL.

### Required modules
* discordpy
* aiohttp

### Setup
1. Create the `zones.txt` file in the working directory with one forecast/county zone ID per line.
2. Set `WEBHOOK_URL` environment variable to your channel's webhook url.
   Webhooks can be created through Discord -> Server Settings -> Integrations -> Webhooks.
3. Run bot.py.

### Features
* Posts alerts considered moderate, severe, or extreme
* Automatically deletes canceled or expired messages
* Updates the channel every 5 minutes, or every minute during urgent events
* Message embeds are utilized

### Zone IDs
The National Weather Service assigns unique IDs to county and forecast zone in the U.S. You can look up IDs at the
[NWS Alerts page](https://alerts.weather.gov/).