from __future__ import annotations

from swiss_transport_mcp.clients.base import TransportClient
from swiss_transport_mcp.errors import AmbiguousStationError, TransportAPIError
from swiss_transport_mcp.formatters import format_connections, format_locations, format_stationboard


class TransportService:
    def __init__(self, client: TransportClient):
        self._client = client

    async def search_locations(
        self,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        loc_type: str = "all",
    ) -> str:
        try:
            locations = await self._client.search_locations(
                query=query, latitude=latitude, longitude=longitude, loc_type=loc_type
            )
            return format_locations(locations)
        except TransportAPIError as e:
            return f"Error searching locations: {e}"

    async def search_connections(
        self,
        from_station: str,
        to_station: str,
        via: list[str] | None = None,
        date: str | None = None,
        time: str | None = None,
        is_arrival_time: bool = False,
        transport_types: list[str] | None = None,
        limit: int = 4,
    ) -> str:
        try:
            connections = await self._client.get_connections(
                from_station=from_station,
                to_station=to_station,
                via=via,
                date=date,
                time=time,
                is_arrival_time=is_arrival_time,
                transport_types=transport_types,
                limit=limit,
            )
            return format_connections(connections, from_station, to_station)
        except AmbiguousStationError as e:
            lines = ["Multiple stations match. Did you mean:"]
            for i, loc in enumerate(e.candidates, 1):
                lines.append(f"  {i}. {loc.name} (ID: {loc.id})")
            lines.append("Please retry with a more specific name or station ID.")
            return "\n".join(lines)
        except TransportAPIError as e:
            return f"Error finding connections: {e}"

    async def get_stationboard(
        self,
        station: str,
        limit: int = 20,
        datetime_str: str | None = None,
        mode: str = "departure",
        transport_types: list[str] | None = None,
    ) -> str:
        try:
            board = await self._client.get_stationboard(
                station=station,
                limit=limit,
                datetime_str=datetime_str,
                mode=mode,
                transport_types=transport_types,
            )
            return format_stationboard(board)
        except AmbiguousStationError as e:
            lines = ["Multiple stations match. Did you mean:"]
            for i, loc in enumerate(e.candidates, 1):
                lines.append(f"  {i}. {loc.name} (ID: {loc.id})")
            lines.append("Please retry with a more specific name or station ID.")
            return "\n".join(lines)
        except TransportAPIError as e:
            return f"Error fetching stationboard: {e}"
