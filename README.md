## Weatherhook

Post U.S. weather alerts to your Discord channel using Discord's built-in webhook functionality.

### Features
* Posts active weather alerts for your chosen zones as rich embeds
* Filters alerts by severity
* Deletes the Discord message when an alert expires or is cancelled
* Polls faster while any active alert has `Immediate` urgency
* Remembers posted alerts across restarts, so nothing is reposted or left behind
* Re-reads `config.yaml` on every poll, so changes take effect without a restart

### Setup
1. Install the requirements: `pip install -r requirements.txt`
2. Edit `config.yaml` to set your zones and severity filter. At least one zone is required.
3. Create a `.env` file next to `bot.py` containing your channel's webhook URL:
   ```
   WEBHOOK_URL=https://discord.com/api/webhooks/webhook_id/webhook_token
   ```
   Webhooks can be created in Discord under Server Settings -> Integrations -> Webhooks.
4. Run `python bot.py`.

### Configuration
All settings live in `config.yaml`:

| Key                     | Description                                                                                                      |
|-------------------------|------------------------------------------------------------------------------------------------------------------|
| `zones`                 | NWS zone or county IDs to watch, such as `VAZ098` or `VAC800`.                                                   |
| `severity`              | Severities to post (`Unknown`, `Minor`, `Moderate`, `Severe`, `Extreme`). Remove the key to receive all of them. |
| `sleep_interval.normal` | Seconds between polls.                                                                                           |
| `sleep_interval.urgent` | Seconds between polls while any active alert has `Immediate` urgency.                                            |
| `log_level`             | `DEBUG`, `INFO`, `WARNING`, or `ERROR`.                                                                          |

### Finding your zone IDs
Request `https://api.weather.gov/points/<latitude>,<longitude>` and look at the `forecastZone` and `county` fields in the response. The last part of each URL is the zone ID.

Full zone lists are also available here:
* https://www.weather.gov/gis/publiczones
* https://www.weather.gov/gis/ZoneCounty

### Files
* `bot.py`: polls the NWS API, builds the embeds, and posts and deletes Discord messages.
* `store.py`: a small SQLite database (`alerts.db`, created automatically) that maps each alert to its Discord message.
* `config.yaml`: your settings.

### Error handling
If the NWS API or Discord can't be reached, the bot logs the problem and retries after 30 seconds. If `config.yaml` is missing or invalid while the bot is running, it logs the problem and keeps retrying until the file is fixed.

*Disclaimer: This project is not affiliated with, endorsed by, or an official product of the National Weather
Service (NWS). It is an independent application that utilizes the public NWS API to provide weather information.*