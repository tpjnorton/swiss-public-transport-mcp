from __future__ import annotations

import re
from datetime import datetime, timedelta

import httpx

from swiss_public_transport_mcp import __version__
from swiss_public_transport_mcp.errors import RateLimitError, TransportAPIError, retry_on_transient
from swiss_public_transport_mcp.models import (
    Connection,
    Leg,
    Location,
    Prognosis,
    Stationboard,
    StationboardEntry,
    Stop,
)

TRANSPORT_TYPE_MAP = {
    "train": "train",
    "tram": "tram",
    "ship": "ship",
    "bus": "bus",
    "cableway": "cableway",
}


class OpenDataClient:
    BASE_URL = "https://transport.opendata.ch/v1"

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"User-Agent": f"swiss-public-transport-mcp/{__version__}"},
        )

    async def _request(self, path: str, params: list[tuple[str, str]]) -> dict:
        response = await self._client.get(path, params=params)
        if response.status_code == 429:
            raise RateLimitError("Rate limited by transport API", status_code=429)
        if response.status_code >= 500:
            raise TransportAPIError(
                f"Server error: {response.status_code}", status_code=response.status_code
            )
        if response.status_code >= 400:
            raise TransportAPIError(
                f"Client error: {response.status_code}", status_code=response.status_code
            )
        return response.json()

    @retry_on_transient()
    async def search_locations(
        self,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        loc_type: str = "all",
    ) -> list[Location]:
        params: list[tuple[str, str]] = []
        if query:
            params.append(("query", query))
        if latitude is not None:
            params.append(("x", str(latitude)))  # API quirk: x = latitude
        if longitude is not None:
            params.append(("y", str(longitude)))  # API quirk: y = longitude
        if loc_type != "all":
            params.append(("type", loc_type))

        data = await self._request("/locations", params)
        return [self._parse_location(s) for s in data.get("stations", []) if s]

    @retry_on_transient()
    async def get_connections(
        self,
        from_station: str,
        to_station: str,
        via: list[str] | None = None,
        date: str | None = None,
        time: str | None = None,
        is_arrival_time: bool = False,
        transport_types: list[str] | None = None,
        limit: int = 4,
    ) -> list[Connection]:
        params: list[tuple[str, str]] = [
            ("from", from_station),
            ("to", to_station),
            ("limit", str(limit)),
            ("isArrivalTime", "1" if is_arrival_time else "0"),
        ]
        if date:
            params.append(("date", date))
        if time:
            params.append(("time", time))
        if via:
            for v in via:
                params.append(("via[]", v))
        if transport_types:
            for t in transport_types:
                api_val = TRANSPORT_TYPE_MAP.get(t, t)
                params.append(("transportations[]", api_val))

        data = await self._request("/connections", params)
        return [self._parse_connection(c) for c in data.get("connections", [])]

    @retry_on_transient()
    async def get_stationboard(
        self,
        station: str,
        limit: int = 20,
        datetime_str: str | None = None,
        mode: str = "departure",
        transport_types: list[str] | None = None,
    ) -> Stationboard:
        params: list[tuple[str, str]] = [
            ("station", station),
            ("limit", str(limit)),
            ("type", mode),  # API param is "type", not "mode"
        ]
        if datetime_str:
            params.append(("datetime", datetime_str))
        if transport_types:
            for t in transport_types:
                api_val = TRANSPORT_TYPE_MAP.get(t, t)
                params.append(("transportations[]", api_val))

        data = await self._request("/stationboard", params)

        station_data = data.get("station", {})
        station_loc = (
            self._parse_location(station_data)
            if station_data
            else Location(id="", name=station, type="station")
        )
        entries = [self._parse_stationboard_entry(e) for e in data.get("stationboard", [])]
        return Stationboard(station=station_loc, entries=entries, mode=mode)

    # --- Parsing helpers ---

    def _parse_location(self, data: dict) -> Location:
        coordinate = data.get("coordinate") or {}
        return Location(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            type=data.get("type", "station"),
            latitude=coordinate.get("x"),  # API quirk: x = lat
            longitude=coordinate.get("y"),  # API quirk: y = lon
            score=data.get("score"),
            distance=data.get("distance"),
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            # API returns ISO 8601 format like "2024-01-15T14:02:00+0100"
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def _parse_prognosis(self, data: dict | None) -> Prognosis | None:
        if not data:
            return None
        dep = self._parse_datetime(data.get("departure"))
        arr = self._parse_datetime(data.get("arrival"))
        plat = data.get("platform")
        cap1 = data.get("capacity1st")
        cap2 = data.get("capacity2nd")
        if dep is None and arr is None and plat is None and cap1 is None and cap2 is None:
            return None
        return Prognosis(
            departure=dep,
            arrival=arr,
            platform=plat,
            capacity_first=cap1,
            capacity_second=cap2,
        )

    def _parse_stop(self, data: dict | None) -> Stop:
        if not data:
            return Stop(station=Location(id="", name="", type="station"))

        station_data = data.get("station") or {}
        station = self._parse_location(station_data)
        arrival = self._parse_datetime(data.get("arrival"))
        departure = self._parse_datetime(data.get("departure"))
        platform = data.get("platform")
        prognosis = self._parse_prognosis(data.get("prognosis"))

        delay_minutes = None
        if prognosis and prognosis.departure and departure:
            diff = (prognosis.departure - departure).total_seconds()
            delay_minutes = int(diff) // 60
        elif prognosis and prognosis.arrival and arrival:
            diff = (prognosis.arrival - arrival).total_seconds()
            delay_minutes = int(diff) // 60

        return Stop(
            station=station,
            arrival=arrival,
            departure=departure,
            platform=platform,
            delay_minutes=delay_minutes,
            prognosis=prognosis,
        )

    def _parse_duration(self, duration_str: str | None) -> timedelta:
        if not duration_str:
            return timedelta()
        match = re.match(r"(\d+)d(\d+):(\d+):(\d+)", duration_str)
        if match:
            days, hours, minutes, seconds = (int(g) for g in match.groups())
            return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        return timedelta()

    def _parse_section(self, data: dict) -> Leg:
        departure = self._parse_stop(data.get("departure"))
        arrival = self._parse_stop(data.get("arrival"))

        journey = data.get("journey")
        walk = data.get("walk")

        if walk is not None:
            return Leg(
                departure=departure,
                arrival=arrival,
                is_walking=True,
            )

        line_name = None
        category = None
        direction = None
        operator = None
        capacity_first = None
        capacity_second = None
        intermediate_stops: list[Stop] = []

        if journey:
            line_name = journey.get("name")
            category = journey.get("category")
            direction = journey.get("to")
            operator = journey.get("operator")
            capacity_first = journey.get("capacity1st")
            capacity_second = journey.get("capacity2nd")

            for stop_data in journey.get("passList", [])[1:-1]:  # skip first/last (dep/arr)
                intermediate_stops.append(self._parse_stop(stop_data))

        return Leg(
            departure=departure,
            arrival=arrival,
            line_name=line_name,
            category=category,
            direction=direction,
            operator=operator,
            is_walking=False,
            intermediate_stops=intermediate_stops,
            capacity_first=capacity_first,
            capacity_second=capacity_second,
        )

    def _parse_connection(self, data: dict) -> Connection:
        sections = data.get("sections", [])
        legs = [self._parse_section(s) for s in sections]

        dep = self._parse_stop(data.get("from"))
        arr = self._parse_stop(data.get("to"))
        duration = self._parse_duration(data.get("duration"))
        transfers = data.get("transfers", 0)

        products = list(dict.fromkeys(leg.category for leg in legs if leg.category))

        return Connection(
            departure=dep,
            arrival=arr,
            duration=duration,
            transfers=transfers,
            legs=legs,
            products=products,
        )

    def _parse_stationboard_entry(self, data: dict) -> StationboardEntry:
        stop = self._parse_stop(data.get("stop"))
        # For stationboard, departure/arrival are at the top level too
        if not stop.departure:
            stop.departure = self._parse_datetime(data.get("departure"))
        if not stop.arrival:
            stop.arrival = self._parse_datetime(data.get("arrival"))

        return StationboardEntry(
            stop=stop,
            line_name=data.get("name"),
            category=data.get("category"),
            direction=data.get("to"),
            operator=data.get("operator"),
            capacity_first=data.get("capacity1st"),
            capacity_second=data.get("capacity2nd"),
        )
