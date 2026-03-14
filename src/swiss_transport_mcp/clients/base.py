from __future__ import annotations

from typing import Protocol

from swiss_transport_mcp.models import Connection, Location, Stationboard


class TransportClient(Protocol):
    async def search_locations(
        self,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        loc_type: str = "all",
    ) -> list[Location]: ...

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
    ) -> list[Connection]: ...

    async def get_stationboard(
        self,
        station: str,
        limit: int = 20,
        datetime_str: str | None = None,
        mode: str = "departure",
        transport_types: list[str] | None = None,
    ) -> Stationboard: ...
