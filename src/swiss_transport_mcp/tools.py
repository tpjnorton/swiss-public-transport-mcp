from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchLocationsInput(BaseModel):
    query: str | None = Field(
        None, description="Station name or partial name (e.g., 'Bern', 'Zurich HB')"
    )
    latitude: float | None = Field(None, description="WGS84 latitude for nearby station search")
    longitude: float | None = Field(None, description="WGS84 longitude for nearby station search")
    type: Literal["all", "station", "poi", "address"] = Field(
        "station", description="Location type filter"
    )


class SearchConnectionsInput(BaseModel):
    from_station: str = Field(..., description="Departure station name or ID")
    to_station: str = Field(..., description="Arrival station name or ID")
    via: list[str] | None = Field(None, description="Intermediate stations (up to 5)", max_length=5)
    date: str | None = Field(None, description="Travel date (YYYY-MM-DD). Defaults to today")
    time: str | None = Field(None, description="Travel time (HH:MM). Defaults to now")
    is_arrival_time: bool = Field(
        False,
        description="If true, the specified time is the desired arrival time, not departure",
    )
    transport_types: list[Literal["train", "tram", "ship", "bus", "cableway"]] | None = Field(
        None, description="Filter by transport type. Omit for all types"
    )
    limit: int = Field(4, description="Number of connections to return (1-6)", ge=1, le=6)


class StationboardInput(BaseModel):
    station: str = Field(..., description="Station name or ID")
    mode: Literal["departure", "arrival"] = Field(
        "departure", description="Show departures or arrivals"
    )
    limit: int = Field(15, description="Number of entries (1-40)", ge=1, le=40)
    datetime: str | None = Field(
        None, description="Date and time (YYYY-MM-DD HH:MM). Defaults to now"
    )
    transport_types: list[Literal["train", "tram", "ship", "bus", "cableway"]] | None = Field(
        None, description="Filter by transport type. Omit for all types"
    )


class BookingLinkInput(BaseModel):
    from_station: str = Field(..., description="Departure station name")
    to_station: str = Field(..., description="Arrival station name")
    date: str | None = Field(None, description="Travel date (YYYY-MM-DD)")
    time: str | None = Field(None, description="Travel time (HH:MM)")
    is_arrival_time: bool = Field(False, description="If true, time is desired arrival time")
