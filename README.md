## Weatherhook

Post U.S. weather alerts to your discord channel using Discord's built-in webhook functionality.

### Required packages
* discordpy
* aiohttp
* pyyaml
* python-dotenv
* aiosqlite

### Setup
1. Modify `config.yaml` to add zones and severity filters. At least one zone is required.
2. Set `WEBHOOK_URL` environment variable to your channel's webhook url in your `.env` file. 
   * Example: ```WEBHOOK_URL=https://discord.com/api/webhooks/webhook_id/webhook_token```
   * Webhooks can be created through Discord -> Server Settings -> Integrations -> Webhooks.

3. Run bot.py.

### Features
* Posts moderate, severe, and extreme alerts
* Deletes alerts when they become inactive
* Update interval changes based on alert urgency
* Persists tracked alerts across restarts via a local SQLite database (`alerts.db`)

### Zone IDs
`all_zones.csv` provides the ID, state, type, and name for all weather zones. You can also look up IDs in files found
below:
* https://www.weather.gov/gis/publiczones
* https://www.weather.gov/gis/ZoneCounty

Disclaimer: This project is not affiliated with, endorsed by, or an official product of the National Weather
Service (NWS). It is an independent application that utilizes the public NWS API to provide weather information.