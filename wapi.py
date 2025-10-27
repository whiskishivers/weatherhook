import datetime as dt
import logging
import re
import time
from dataclasses import dataclass

import aiohttp
import discord


class FeatureCollection(list):
    """ Default object from API """

    def __init__(self, fcoll=None):
        super().__init__()
        self.title = fcoll.get("title")
        for feature in fcoll["features"]:
            match feature["properties"]["@type"]:
                case "wx:Alert":
                    self.append(Alert(feature))
                case _:
                    self.append(Feature(feature))

    def __repr__(self):
        return f"FeatureCollection({self.title})"


class Feature:
    id: str = None

    def __init__(self, feature):
        for k, v in feature["properties"].items():
            setattr(self, k, v)

    def __repr__(self):
        return f"Feature({self.id})"


@dataclass(order=True)
class Alert(Feature):
    affectedZones: list
    areaDesc: str
    description: str
    headline: str
    message_id: str
    effective: dt.datetime
    ends: dt.datetime
    event: str
    expires: dt.datetime
    instruction: str
    parameters: dict
    response: str
    senderName: str
    sent: dt.datetime
    onset: dt.datetime
    severity: str
    urgency: str
    wmo: str | None
    zones: FeatureCollection
    _alert_colors = {("Severe", "Expected"): discord.Color.dark_gold(),
                     ("Severe", "Future"): discord.Color.dark_gold(),
                     ("Severe", "Immediate"): discord.Color.gold(),
                     ("Extreme", "Expected"): discord.Color.dark_red(),
                     ("Extreme", "Future"): discord.Color.dark_red(),
                     ("Extreme", "Immediate"): discord.Color.red()}

    def __init__(self, alert_feature):
        super().__init__(alert_feature)
        # pull out required parameters
        self.nws_headline = self.parameters.get("NWSheadline")
        try:
            self.wmo = self.parameters["WMOidentifier"][0].split(" ")[1][-3:]
        except (KeyError, TypeError):
            self.wmo = None

        # Make awful space formatting be comma-separated instead
        if self.description is not None:
            self.description = re.sub(r"\s{4,}", ", ", self.description).strip()

        # Change required date strings to datetime objects
        for i in ("sent", "effective", "onset", "expires", "ends"):
            try:
                setattr(self, i, dt.datetime.fromisoformat(alert_feature["properties"][i]))
            except TypeError:  # null
                setattr(self, i, None)

    def __repr__(self):
        return f"Alert({self.event})"

    @property
    def embed(self) -> discord.Embed:
        """ Discord message embed """
        color = self._alert_colors.get((self.severity, self.urgency))
        description = ""
        # Get full description for urgent alerts, otherwise use headline
        if self.urgency == "Immediate" or self.nws_headline is None:
            description += self.description[:4096]
        elif self.nws_headline:
            description += f"{"\n".join(self.nws_headline)}"

        embed = discord.Embed(color=color, title=self.event, url=f"https://alerts.weather.gov/search?id={self.id}",
                              description=description, timestamp=self.sent)
        # Embed Fields
        #Include instructions if alert response calls for action
        if self.instruction and self.response in ("Evacuate", "Execute", "Shelter"):
            instructions = re.sub(r"(?<!\n)\n(?!\n)", " ", self.instruction).strip()
            embed.add_field(name="Instructions", value=instructions[:1024], inline=False)

        embed.add_field(name="Severity", value=f"{self.severity} - {self.urgency}")

        if self.onset is not None:
            embed.add_field(name="Onset", value=f"<t:{int(self.onset.timestamp())}:R>")
        if self.ends is not None:
            embed.add_field(name="Ends", value=f"<t:{int(self.ends.timestamp())}:R>")
        if self.wmo:
            author_url = f"https://www.weather.gov/{self.wmo.lower()}"
            embed.set_author(name=self.senderName, url=author_url)
        return embed

    @property
    def embed_inactive(self) -> discord.Embed:
        """ Discord message embed for inactive alerts """
        embed = discord.Embed(title=self.event, url=f"https://alerts.weather.gov/search?id={self.id}",
                              description="*This alert is no longer active.*")
        if self.wmo:
            author_url = f"https://www.weather.gov/{self.wmo.lower()}"
            embed.set_author(name=self.senderName, url=author_url)
        return embed


class ClientAlerts:
    def __init__(self, parent):
        self.parent = parent

    async def active(self, **params) -> FeatureCollection[Alert]:
        return FeatureCollection(await self.parent.get(f"alerts/active", params=params))


class Client:
    def __init__(self):
        self.headers = {"User-Agent": "python-aiohttp | Discord weather bot"}
        self.session = None
        self.alerts = ClientAlerts(self)

    async def initialize_session(self):
        """Initializes the session."""
        self.session = aiohttp.ClientSession()

    async def get(self, endpoint, params=None) -> dict:
        url = f"https://api.weather.gov/{endpoint}"
        if self.session is None:
            await self.initialize_session()

        async with self.session.get(url, params=params, headers=self.headers) as resp:
            logging.debug(f"GET {resp.url}")
            print(f"{time.strftime('%H:%M:%S')} API GET {resp.status} {resp.reason}")
            resp.raise_for_status()
            try:
                return await resp.json()
            except aiohttp.ClientResponseError as e:
                raise e


client = Client()
