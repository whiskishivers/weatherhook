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
* Posts active weather alerts to your discord channel utilizing rich embeds
* Alerts may be filtered based on severity
* Deletes alerts when they become inactive
* Update interval changes based on alert urgency
* Optional web UI


### Web UI
`webui.py` runs a basic HTTP server to provide a user interface for the bot. Run it alongside the bot from the same
working directory and then point your web browser to `http://localhost:5001`. It allows you to monitor status and make
changes to the bot configuration.

Note: The web UI has no authentication and is entirely optional. Do not expose it publicly.

### Zone IDs
`all_zones.csv` provides the ID, state, type, and name for all weather zones and is used by the web ui for zone search.
If this file becomes out of date, you can look up current zones in the files found below:
* https://www.weather.gov/gis/publiczones
* https://www.weather.gov/gis/ZoneCounty

*Disclaimer: This project is not affiliated with, endorsed by, or an official product of the National Weather
Service (NWS). It is an independent application that utilizes the public NWS API to provide weather information.*

