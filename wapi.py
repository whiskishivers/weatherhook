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

    def __init__(self, raw_collection: dict | None = None):
        if raw_collection is None:
            raw_collection = {}

        # Composition: Hold the features as a list attribute
        self.features: list[Feature | Alert] = []
        self.title: str | None = raw_collection.get("title")

        # Process features safely
        raw_features = raw_collection.get("features", [])

        for feature in raw_features:
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
    message_id: str  # discord message id
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
        super().__init__(alert_feature)

        self.nws_headline = self.parameters.get("NWSheadline")

        # Extract WMO identifier
        wmo_list = self.parameters.get("WMOidentifier")
        if wmo_list and isinstance(wmo_list, list) and len(wmo_list) > 0:
            try:
                parts = wmo_list[0].split(" ")
                if len(parts) >= 2:
                    self.wmo = parts[1][-3:]
            except IndexError:
                self.wmo = None

        # Fix formatting for description and instruction fields
        if self.description:
            # Clean up awful formatting when spacing is used for columns
            self.description = re.sub(r"\s{4,}", ", ", self.description).strip()
            # Remove linebreaks between letters/digits, commas, periods
            self.description = re.sub(r'(?<=[\w,.])[ \t]*[\r\n]+[ \t]*(?=[\w,.])', " ", self.description).strip()
        if self.instruction:
            self.instruction = re.sub(r'(?<=[\w,.])[ \t]*[\r\n]+[ \t]*(?=[\w,.])', " ", self.instruction).strip()

        # Convert date fields to datetime objects
        for field_name in ("sent", "effective", "onset", "expires", "ends"):
            val = getattr(self, field_name, None)
            if not isinstance(val, str) or not val:
                setattr(self, field_name, None)
                continue
            try:
                setattr(self, field_name, dt.datetime.fromisoformat(val))
            except ValueError:
                setattr(self, field_name, None)

    def __repr__(self):
        return f"Alert(event='{self.event}')"

    def __str__(self):
        return self.__repr__()

    @property
    def embed(self) -> discord.Embed:
        """ Discord message embed """
        color = self._alert_colors.get((self.severity, self.urgency))
        if self.nws_headline is not None:
            headline = "\n".join(self.nws_headline) + "\n"
        else:
            headline = ""

        description = (headline + self.description)

        embed = discord.Embed(color=color, title=self.event,
                              description=description[:4096], timestamp=self.sent)

        # Include instructions if alert response calls for action
        if self.instruction and self.response in ("Evacuate", "Execute", "Shelter"):
            embed.add_field(name="Instructions", value=self.instruction[:1024], inline=False)

        # Timestamp fields
        if self.onset:
            onset_ts = int(self.onset.timestamp())
            embed.add_field(name="Onset", value=f"<t:{onset_ts}:d> <t:{onset_ts}:t>")
        if self.ends:
            ends_ts = int(self.ends.timestamp())
            embed.add_field(name="End", value=f"<t:{ends_ts}:d> <t:{ends_ts}:t>")

        embed.add_field(name="Severity", value=f"{self.severity} - {self.urgency}")

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
