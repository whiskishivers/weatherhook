import datetime as dt
import logging
import re
import time
from dataclasses import dataclass, field, fields
from typing import ClassVar

import aiohttp
import discord


@dataclass
class Feature:
    """ Base object from API """
    id: str | None = None
    type_name: str | None = None


@dataclass(order=True)
class Alert(Feature):
    """ Represents a NWS alert """
    _alert_colors: ClassVar[dict] = {
        ("Severe", "Expected"): discord.Color.dark_gold(),
        ("Severe", "Future"): discord.Color.dark_gold(),
        ("Severe", "Immediate"): discord.Color.gold(),
        ("Extreme", "Expected"): discord.Color.dark_red(),
        ("Extreme", "Future"): discord.Color.dark_red(),
        ("Extreme", "Immediate"): discord.Color.red()
    }

    event: str = ""
    severity: str = ""
    urgency: str = ""
    # areaDesc: str = ""
    description: str = ""
    headline: str | None = None
    instruction: str | None = None
    response: str | None = None
    senderName: str | None = None
    sent: dt.datetime | str | None = None
    onset: dt.datetime | str | None = None
    # expires: dt.datetime | str | None = None
    ends: dt.datetime | str | None = None
    # effective: dt.datetime | str | None = None
    parameters: dict = field(default_factory=dict)

    # Internal Fields (calculated in __post_init__)
    wmo: str | None = field(default=None, init=False)
    nws_headline: list[str] | None = field(default=None, init=False)

    @classmethod
    def from_api(cls, feature_dict: dict) -> "Alert":
        """
        Factory method: Creates an Alert instance from a single NWS 'feature' dictionary.
        """
        top_id = feature_dict.get("id")
        properties = feature_dict.get("properties", {}).copy()

        # Remove 'id' from properties to avoid "multiple values for keyword argument" error
        properties.pop("id", None)

        # 2. Filter properties to only those that exist in our dataclass fields
        class_fields = {f.name for f in fields(cls)}
        filtered_props = {k: v for k, v in properties.items() if k in class_fields}

        return cls(id=top_id, **filtered_props)

    def __post_init__(self):
        """
        Standardizes types and formatting after the object is created.
        """
        self._parse_wmo()
        self._clean_text_fields()
        self._convert_timestamps()

        # Extract headlines if available in parameters
        self.nws_headline = self.parameters.get("NWSheadline")

    def __repr__(self):
        return f"Alert(id={self.id}, event={self.event})"

    def _parse_wmo(self):
        """Extracts the WMO identifier from parameters."""
        wmo_list = self.parameters.get("WMOidentifier", [])
        if wmo_list and isinstance(wmo_list, list) and len(wmo_list) > 0:
            try:
                parts = wmo_list[0].split(" ")
                if len(parts) >= 2:
                    self.wmo = parts[1][-3:]
            except (IndexError, AttributeError):
                self.wmo = None

    def _clean_text_fields(self):
        """Fixes NWS formatting quirks (excessive spaces and awkward linebreaks)."""

        def clean(s):
            if not s: return s
            s = re.sub(r"\s{4,}", ", ", s).strip()
            return re.sub(r'(?<=[\w,])[ \t]*[\r\n]+[ \t]*(?=[\w,])', " ", s).strip()

        self.description = clean(self.description)
        self.instruction = clean(self.instruction)

    def _convert_timestamps(self):
        """Converts date strings into datetime objects."""
        for field_name in ["sent", "onset", "ends"]:
            val = getattr(self, field_name)
            if isinstance(val, str):
                try:
                    setattr(self, field_name, dt.datetime.fromisoformat(val))
                except (ValueError, TypeError):
                    setattr(self, field_name, None)

    @property
    def embed(self) -> discord.Embed:
        """ Generates a Discord message embed for the alert. """
        color = self._alert_colors.get((self.severity, self.urgency), discord.Color.blue())

        prefix = "\n".join(self.nws_headline) + "\n\n" if self.nws_headline else ""
        full_desc = f"{prefix}{self.description}"

        embed = discord.Embed(
            title=self.event,
            description=full_desc[:4096],
            color=color,
            timestamp=self.sent if isinstance(self.sent, dt.datetime) else None
        )

        if self.instruction and self.response in ("Evacuate", "Execute", "Prepare", "Shelter"):
            embed.add_field(name="Instructions", value=self.instruction[:1024], inline=False)

        if isinstance(self.onset, dt.datetime):
            ts = int(self.onset.timestamp())
            embed.add_field(name="Onset", value=f"<t:{ts}:d> <t:{ts}:t>\n<t:{ts}:R>")

        if isinstance(self.ends, dt.datetime):
            ts = int(self.ends.timestamp())
            embed.add_field(name="End", value=f"<t:{ts}:d> <t:{ts}:t>")

        embed.add_field(name="Severity", value=f"{self.severity} - {self.urgency}")

        if self.wmo:
            author_url = f"https://www.weather.gov/{self.wmo.lower()}"
            embed.set_author(name=self.senderName or "NWS", url=author_url)

        return embed

    @property
    def embed_inactive(self) -> discord.Embed:
        """ Embed style for expired or cancelled alerts. """
        embed = discord.Embed(
            title=self.event,
            url=f"https://alerts.weather.gov/search?id={self.id}",
            description="*This alert is no longer active.*"
        )
        if self.wmo:
            author_url = f"https://www.weather.gov/{self.wmo.lower()}"
            embed.set_author(name=self.senderName or "NWS", url=author_url)
        return embed


class FeatureCollection:

    def __init__(self, title: str | None = None, features: list[Alert] | None = None):
        self.title = title
        self.features = features or []

    @classmethod
    def from_api_response(cls, data: dict) -> "FeatureCollection":
        """ """
        raw_features = data.get("features", [])
        title = data.get("title")

        alert_objects = [
            Alert.from_api(f)
            for f in raw_features
            if f.get("properties", {}).get("@type") == "wx:Alert"
        ]

        return cls(title=title, features=alert_objects)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, index):
        return self.features[index]

    def __iter__(self):
        return iter(self.features)


class ClientAlerts:
    """Resource accessor for NWS Alerts."""

    def __init__(self, parent: 'Client'):
        self.parent = parent

    async def active(self, **params) -> FeatureCollection:
        """ Retrieves active NWS alerts. """
        response_data = await self.parent.get("alerts/active", params=params)
        return FeatureCollection.from_api_response(response_data)


class Client:
    """ Main API Client for NWS. """

    def __init__(self):
        self.headers = {"User-Agent": "python-aiohttp | Discord weather bot"}
        self.session: aiohttp.ClientSession | None = None
        self.alerts = ClientAlerts(self)

    async def initialize_session(self):
        """Initializes the session if it doesn't exist."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)

    async def get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"https://api.weather.gov/{endpoint}"
        await self.initialize_session()

        async with self.session.get(url, params=params) as resp:
            logging.debug(f"GET {resp.url}")
            print(f"{time.strftime('%H:%M:%S')} API GET {resp.status} {resp.reason}")
            resp.raise_for_status()
            return await resp.json()

    async def close(self):
        """ Closes the underlying session. """
        if self.session:
            await self.session.close()


client = Client()
