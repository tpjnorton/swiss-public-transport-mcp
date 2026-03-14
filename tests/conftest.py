from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from swiss_transport_mcp.models import (
    Connection,
    Leg,
    Location,
    Prognosis,
    Stationboard,
    StationboardEntry,
    Stop,
)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.search_locations = AsyncMock(return_value=[])
    client.get_connections = AsyncMock(return_value=[])
    client.get_stationboard = AsyncMock(
        return_value=Stationboard(
            station=sample_location(), entries=[], mode="departure"
        )
    )
    return client


@pytest.fixture
def service(mock_client):
    from swiss_transport_mcp.service import TransportService

    return TransportService(mock_client)


def sample_location(
    id: str = "8507000",
    name: str = "Bern",
    type: str = "station",
    latitude: float | None = 46.9480,
    longitude: float | None = 7.4390,
    score: float | None = None,
    distance: float | None = None,
) -> Location:
    return Location(
        id=id,
        name=name,
        type=type,
        latitude=latitude,
        longitude=longitude,
        score=score,
        distance=distance,
    )


def sample_stop(
    name: str = "Bern",
    id: str = "8507000",
    departure: datetime | None = None,
    arrival: datetime | None = None,
    platform: str | None = None,
    delay_minutes: int | None = None,
    prognosis: Prognosis | None = None,
) -> Stop:
    return Stop(
        station=sample_location(id=id, name=name),
        departure=departure,
        arrival=arrival,
        platform=platform,
        delay_minutes=delay_minutes,
        prognosis=prognosis,
    )


def sample_leg(
    dep_name: str = "Zürich HB",
    arr_name: str = "Bern",
    dep_time: datetime | None = None,
    arr_time: datetime | None = None,
    dep_platform: str | None = "8",
    line_name: str | None = "IC 1",
    category: str | None = "IC",
    direction: str | None = "Genève-Aéroport",
    is_walking: bool = False,
    delay_minutes: int | None = None,
    prognosis: Prognosis | None = None,
    capacity_first: int | None = None,
    capacity_second: int | None = None,
    intermediate_stops: list[Stop] | None = None,
) -> Leg:
    dep_time = dep_time or datetime(2025, 1, 15, 14, 2)
    arr_time = arr_time or datetime(2025, 1, 15, 14, 58)
    return Leg(
        departure=sample_stop(
            name=dep_name,
            departure=dep_time,
            platform=dep_platform,
            delay_minutes=delay_minutes,
            prognosis=prognosis,
        ),
        arrival=sample_stop(name=arr_name, arrival=arr_time),
        line_name=line_name,
        category=category,
        direction=direction,
        is_walking=is_walking,
        capacity_first=capacity_first,
        capacity_second=capacity_second,
        intermediate_stops=intermediate_stops or [],
    )


def sample_connection(
    legs: list[Leg] | None = None,
    duration: timedelta | None = None,
    transfers: int = 0,
) -> Connection:
    legs = legs or [sample_leg()]
    first_leg = legs[0]
    last_leg = legs[-1]
    return Connection(
        departure=first_leg.departure,
        arrival=last_leg.arrival,
        duration=duration or timedelta(minutes=56),
        transfers=transfers,
        legs=legs,
        products=[leg.category for leg in legs if leg.category],
    )


def sample_stationboard_entry(
    name: str = "Zürich HB",
    departure: datetime | None = None,
    platform: str | None = "8",
    line_name: str | None = "IC 1",
    category: str | None = "IC",
    direction: str | None = "Genève-Aéroport",
    delay_minutes: int | None = None,
    prognosis: Prognosis | None = None,
    capacity_first: int | None = None,
    capacity_second: int | None = None,
) -> StationboardEntry:
    departure = departure or datetime(2025, 1, 15, 14, 2)
    return StationboardEntry(
        stop=sample_stop(
            name=name,
            departure=departure,
            platform=platform,
            delay_minutes=delay_minutes,
            prognosis=prognosis,
        ),
        line_name=line_name,
        category=category,
        direction=direction,
        capacity_first=capacity_first,
        capacity_second=capacity_second,
    )


def sample_stationboard(
    station_name: str = "Zürich HB",
    entries: list[StationboardEntry] | None = None,
    mode: str = "departure",
) -> Stationboard:
    return Stationboard(
        station=sample_location(name=station_name),
        entries=entries or [],
        mode=mode,
    )
