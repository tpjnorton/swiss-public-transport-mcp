from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from mcp.server.fastmcp import Context, FastMCP

from swiss_public_transport_mcp import __version__
from swiss_public_transport_mcp.clients.opendata import OpenDataClient
from swiss_public_transport_mcp.formatters import build_sbb_url
from swiss_public_transport_mcp.service import TransportService
from swiss_public_transport_mcp.tools import (
    BookingLinkInput,
    SearchConnectionsInput,
    SearchLocationsInput,
    StationboardInput,
)


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    async with httpx.AsyncClient(
        base_url=OpenDataClient.BASE_URL,
        timeout=httpx.Timeout(15.0, connect=5.0),
        headers={"User-Agent": f"swiss-public-transport-mcp/{__version__}"},
    ) as http_client:
        client = OpenDataClient(http_client)
        service = TransportService(client)
        yield {"service": service}


mcp = FastMCP(
    "Swiss Public Transport",
    instructions="Real-time Swiss public transport: connections, stationboards, and station search",
    lifespan=app_lifespan,
)


def _get_service(ctx: Context) -> TransportService:
    return ctx.request_context.lifespan_context["service"]


@mcp.tool()
async def search_locations(
    query: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    type: str = "station",
    ctx: Context | None = None,
) -> str:
    """Find Swiss train stations, bus stops, and other transport locations.

    Use this to:
    - Look up a station name (e.g., "Bern", "Zürich HB", "Interlaken")
    - Find stations near GPS coordinates (e.g., near your hotel)
    - Resolve ambiguous names before planning a journey

    Returns station IDs, coordinates, and relevance scores.
    """
    inp = SearchLocationsInput(query=query, latitude=latitude, longitude=longitude, type=type)
    service = _get_service(ctx)
    return await service.search_locations(
        query=inp.query, latitude=inp.latitude, longitude=inp.longitude, loc_type=inp.type
    )


@mcp.tool()
async def plan_journey(
    from_station: str,
    to_station: str,
    via: list[str] | None = None,
    date: str | None = None,
    time: str | None = None,
    is_arrival_time: bool = False,
    transport_types: list[str] | None = None,
    limit: int = 4,
    ctx: Context | None = None,
) -> str:
    """Plan a journey through Switzerland by train, bus, tram, boat, or cableway.

    Use this whenever someone wants to:
    - Travel from A to B (e.g., "how do I get from Zürich to Zermatt?")
    - Plan a multi-stop trip (use `via` for intermediate stops)
    - Find the best connection for a specific date/time
    - Arrive somewhere by a deadline (set `is_arrival_time=True`)
    - Compare route options across different transport types

    Returns real-time schedules with platform numbers, delays, transfers,
    and occupancy levels. Call multiple times with different legs to plan
    a full day itinerary visiting several places.
    """
    inp = SearchConnectionsInput(
        from_station=from_station,
        to_station=to_station,
        via=via,
        date=date,
        time=time,
        is_arrival_time=is_arrival_time,
        transport_types=transport_types,
        limit=limit,
    )
    service = _get_service(ctx)
    return await service.search_connections(
        from_station=inp.from_station,
        to_station=inp.to_station,
        via=inp.via,
        date=inp.date,
        time=inp.time,
        is_arrival_time=inp.is_arrival_time,
        transport_types=inp.transport_types,
        limit=inp.limit,
    )


@mcp.tool()
async def get_stationboard(
    station: str,
    mode: str = "departure",
    limit: int = 15,
    datetime: str | None = None,
    transport_types: list[str] | None = None,
    ctx: Context | None = None,
) -> str:
    """Check what's departing or arriving at a Swiss station right now.

    Use this to:
    - See upcoming departures ("what trains leave from Bern soon?")
    - Check if a specific service is delayed or cancelled
    - Browse arrivals at a station
    - Filter by transport type (trains only, buses only, etc.)

    Returns a live board with times, platforms, destinations, and delay status.
    """
    inp = StationboardInput(
        station=station,
        mode=mode,
        limit=limit,
        datetime=datetime,
        transport_types=transport_types,
    )
    service = _get_service(ctx)
    return await service.get_stationboard(
        station=inp.station,
        limit=inp.limit,
        datetime_str=inp.datetime,
        mode=inp.mode,
        transport_types=inp.transport_types,
    )


@mcp.tool()
async def get_booking_link(
    from_station: str,
    to_station: str,
    date: str | None = None,
    time: str | None = None,
    is_arrival_time: bool = False,
) -> str:
    """Get a direct link to buy tickets on sbb.ch for a specific journey.

    Use this when someone wants to:
    - Buy a ticket ("book me a train from Zürich to Bern")
    - Get a link to the SBB website for a specific route and time
    - Share a timetable link with someone

    Returns a ready-to-click URL that opens SBB's timetable with the search pre-filled.
    """
    inp = BookingLinkInput(
        from_station=from_station,
        to_station=to_station,
        date=date,
        time=time,
        is_arrival_time=is_arrival_time,
    )
    url = build_sbb_url(
        inp.from_station,
        inp.to_station,
        date=inp.date,
        time=inp.time,
        is_arrival_time=inp.is_arrival_time,
    )
    return f"Book your journey from {inp.from_station} to {inp.to_station} on SBB:\n{url}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
