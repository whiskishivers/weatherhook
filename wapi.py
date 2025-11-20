import datetime as dt
import logging
import re
import time
import typing
from dataclasses import dataclass, field
from typing import ClassVar

import aiohttp
import discord


class FeatureCollection:
    """ Collection object for API features. """

    def __init__(self, fcoll: dict | None = None):
        if fcoll is None:
            fcoll = {}

        # Composition: Hold the features as a list attribute
        self.features: list[Feature | Alert] = []
        self.title: str | None = fcoll.get("title")

        # Process features safely
        raw_features = fcoll.get("features", [])

        for feature in raw_features:
            # Safely get the type attribute
            feature_type = feature.get("properties", {}).get("@type")

            match feature_type:
                case "wx:Alert":
                    self.features.append(Alert(feature))
                case _:
                    self.features.append(Feature(feature))

    def __repr__(self):
        return f"FeatureCollection(title='{self.title}', count={len(self.features)})"

    # Helper methods for list-like behavior
    def __len__(self):
        return len(self.features)

    def __getitem__(self, index):
        return self.features[index]

    def __iter__(self):
        return iter(self.features)

    def sort(self, *args, **kwargs):
        return self.features.sort(*args, **kwargs)


class Feature:
    """ Base object from API """

    id: str | None = None
    type_name: str | None = None

    def __init__(self, feature: dict):
        properties = feature.get("properties", {})
        self.id = feature.get("id")

        # Assign properties
        for k, v in properties.items():
            # Rename the reserved keyword
            if k == "@type":
                self.type_name = v
            else:
                setattr(self, k, v)

    def __repr__(self):
        return f"Feature(id='{self.id}')"


@dataclass(order=True, init=False)
class Alert(Feature):
    _alert_colors: ClassVar[dict] = {
        ("Severe", "Expected"): discord.Color.dark_gold(),
        ("Severe", "Future"): discord.Color.dark_gold(),
        ("Severe", "Immediate"): discord.Color.gold(),
        ("Extreme", "Expected"): discord.Color.dark_red(),
        ("Extreme", "Future"): discord.Color.dark_red(),
        ("Extreme", "Immediate"): discord.Color.red()
    }

    affectedZones: list
    areaDesc: str
    description: str
    headline: str
    message_id: str
    event: str
    instruction: typing.Optional[str]
    parameters: dict
    response: str
    senderName: str
    severity: str
    urgency: str
    zones: typing.Any
    effective: typing.Optional[dt.datetime] = field(default=None)
    ends: typing.Optional[dt.datetime] = field(default=None)
    expires: typing.Optional[dt.datetime] = field(default=None)
    onset: typing.Optional[dt.datetime] = field(default=None)
    sent: typing.Optional[dt.datetime] = field(default=None)
    nws_headline: typing.Optional[list[str]] = field(default=None, init=False)
    wmo: typing.Optional[str] = field(default=None, init=False)


    def __init__(self, alert_feature: dict):
        # Init up and down and everywhere
        super().__init__(alert_feature)
        self.__post_init__()

    def __post_init__(self):
        properties = getattr(self, "properties", {})

        self.nws_headline = self.parameters.get("NWSHeadline")

        # Extract WMO identifier
        wmo_list = self.parameters.get("WMOidentifier")
        if wmo_list and isinstance(wmo_list, list) and len(wmo_list) > 0:
            try:
                parts = wmo_list[0].split(" ")
                if len(parts) >= 2:
                    self.wmo = parts[1][-3:]
            except IndexError:
                self.wmo = None

        if self.description is not None:
            # Clean up awful formatting when "columns" are in the text
            self.description = re.sub(r"\s{4,}", ", ", self.description).strip()

        # Convert date fields to datetime objects
        for field_name in ("sent", "effective", "onset", "expires", "ends"):
            date_str = properties.get(field_name)
            if date_str is None or date_str == "":
                setattr(self, field_name, None)
                continue
            try:
                setattr(self, field_name, dt.datetime.fromisoformat(date_str))
            except ValueError:
                setattr(self, field_name, None)

    def __repr__(self):
        return f"Alert(event='{self.event}', sender='{self.senderName}')"

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
    """Resource accessor for NWS Alerts."""

    def __init__(self, parent):
        self.parent = parent

    async def active(self, **params) -> FeatureCollection:
        """
        Retrieves active NWS alerts.
        Documentation typically uses 'alerts/active' endpoint.
        """
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
