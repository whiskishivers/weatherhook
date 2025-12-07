## Weatherhook

Post U.S. weather alerts to your discord channel using Discord's built-in webhook URL functionality.

### Required packages
* discordpy
* aiohttp

### Setup
1. Modify the `zones.txt` file in the script directory with one forecast/county zone ID per line.
2. Set `WEBHOOK_URL` environment variable to your channel's webhook url.
   Webhooks can be created through Discord -> Server Settings -> Integrations -> Webhooks.
3. Run bot.py.

### Features
* Posts moderate, severe, and extreme alerts
* Automatically deletes alerts that become inactive
* Dynamic update interval based on alert urgency
* Alert information is embedded with the chat message

### Zone IDs
Forecast and county zone IDs can be searched for in files found here:
* https://www.weather.gov/gis/publiczones
* https://www.weather.gov/gis/ZoneCounty


