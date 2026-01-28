## Weatherhook

Post U.S. weather alerts to your discord channel using Discord's built-in webhook functionality.

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
* Deletes inactive alert messages
* Dynamic update interval based on alert urgency


### Zone IDs
`all_zones.csv` provides the ID, state, type, and name for all weather zones. You can also look up IDs in files found
below:
* https://www.weather.gov/gis/publiczones
* https://www.weather.gov/gis/ZoneCounty


