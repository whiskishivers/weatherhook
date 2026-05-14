import datetime as dt
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, ClassVar

import aiohttp
import discord


class FeatureCollection:
    """ Collection of features provided by api """

    def __init__(self, title: str | None = None, features: list | None = None):
        self.title = title
        self.features = features or []

    @classmethod
    def from_api(cls, data: dict) -> "FeatureCollection":
        """ Convert raw response from a dict to an instance """
        raw_features = data.get("features", [])
        title = data.get("title")

        features = [Feature.from_api(f) for f in raw_features]

        return cls(title=title, features=features)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, index):
        return self.features[index]

    def __iter__(self):
        return iter(self.features)

@dataclass
class Feature:
    """ low level data object from api """
    id: str | None = None
    wx_type: str | None = None

    _registry: ClassVar[Dict] = {}

    def __init_subclass__(cls, wx_type=None, **kwargs):
        """ Add a feature class to the registry upon run time """
        super().__init_subclass__(**kwargs)
        if wx_type:
            Feature._registry[wx_type] = cls

    @classmethod
    def from_api(cls, feature: dict):
        """ Create class from feature registry """
        props = feature.get("properties", {})
        wx_type = props.get("@type")
        target_class = Feature._registry.get(wx_type, cls)
        return target_class._build(feature)

    @classmethod
    def _build(cls, top_level: dict):
        """Base builder: extracts common fields"""
        return cls(id=top_level.get("id"))

@dataclass
class Alert(Feature, wx_type="wx:Alert"):
    """ NWS weather alert object """
    discord_msg_id: int | None = None
    description: str | None = None
    event: str | None = None
    ends: dt.datetime | str | None = None
    headline: str | None = None
    instruction: str | None = None
    nws_headline: str | None = None
    onset: dt.datetime | str | None = None
    parameters: dict | None = None
    response: str | None = None
    sender_name: str | None = None
    sent: dt.datetime | str | None = None
    severity: str | None = None
    urgency: str | None = None
    _alert_colors: ClassVar[dict] = {
        ("Severe", "Expected"): discord.Color.dark_gold(),
        ("Severe", "Future"): discord.Color.dark_gold(),
        ("Severe", "Immediate"): discord.Color.gold(),
        ("Extreme", "Expected"): discord.Color.dark_red(),
        ("Extreme", "Future"): discord.Color.dark_red(),
        ("Extreme", "Immediate"): discord.Color.red()
    }

    @classmethod
    def _build(cls, top_level: dict):
        """Alert builder"""
        props = top_level["properties"]
        return cls(
            id=top_level.get("id"),
            wx_type=props.get("@type"),
            description=props.get("description"),
            ends=props.get("ends"),
            event=props.get("event"),
            headline=props.get("headline"),
            instruction=props.get("instruction"),
            nws_headline=props.get("parameters", {}).get("NWSheadline"),
            onset=props.get("onset"),
            parameters=props.get("parameters"),
            response=props.get("response"),
            sender_name=props.get("senderName"),
            sent=props.get("sent"),
            severity=props.get("severity"),
            urgency=props.get("urgency")
        )

    def __post_init__(self):
        """ Cleans up inputs """
        self._clean_text_fields()
        self._convert_date_fields()
        self._parse_wmo_identifier()

    def __repr__(self):
        return f"Alert(event={self.event})"

    def _clean_text_fields(self):
        """ Fixes NWS formatting quirks (excessive spaces and awkward linebreaks) """
        def clean(s):
            if not s: return s
            s = re.sub(r"\s{4,}", ", ", s).strip()
            return re.sub(r'(?<=\w)[ \t]*[\r\n]+[ \t]*(?=\w)', " ", s).strip()

        self.description = clean(self.description)
        self.instruction = clean(self.instruction)

        if self.nws_headline:
            self.nws_headline = "\n".join(self.nws_headline)

    def _convert_date_fields(self):
        """ Datetime objects for date fields """
        for field_name in ["sent", "onset", "ends"]:
            val = getattr(self, field_name)
            if isinstance(val, str):
                try:
                    setattr(self, field_name, dt.datetime.fromisoformat(val))
                except (ValueError, TypeError):
                    setattr(self, field_name, None)

    def _parse_wmo_identifier(self):
        """ Extracts the WMO office identifier from parameters """
        self.wmo = None
        if not self.parameters:
            return

        wmo_list = self.parameters.get("WMOidentifier", [])
        if wmo_list and isinstance(wmo_list, list) and len(wmo_list) > 0:
            try:
                parts = wmo_list[0].split(" ")
                if len(parts) >= 2:
                    self.wmo = parts[1][-3:]
            except (IndexError, AttributeError):
                self.wmo = None

    @property
    def embed(self) -> discord.Embed:
        """ Discord message embed object """
        color = self._alert_colors.get((self.severity, self.urgency), discord.Color.blue())

        prefix = self.nws_headline + "\n\n" if self.nws_headline else ""
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
            embed.add_field(name="End", value=f"<t:{ts}:d> <t:{ts}:t>\n<t:{ts}:R>")

        embed.add_field(name="Severity", value=f"{self.severity} - {self.urgency}")

        if self.wmo:
            author_url = f"https://www.weather.gov/{self.wmo.lower()}"
            embed.set_author(name=self.sender_name or "NWS", url=author_url)

        return embed



class ClientAlerts:
    """ Resource accessor for NWS Alerts """

    def __init__(self, parent: 'Client'):
        self.parent = parent

    async def active(self, **params) -> FeatureCollection:
        """ Retrieves active NWS alerts """
        response_data = await self.parent.get("alerts/active", params=params)
        return FeatureCollection.from_api(response_data)


class Client:
    """ Main API Client for NWS """

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


nws_client = Client()
