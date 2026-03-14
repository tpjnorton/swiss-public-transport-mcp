from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Location:
    id: str
    name: str
    type: str
    latitude: float | None = None
    longitude: float | None = None
    score: float | None = None
    distance: float | None = None


@dataclass
class Prognosis:
    departure: datetime | None = None
    arrival: datetime | None = None
    platform: str | None = None
    capacity_first: int | None = None
    capacity_second: int | None = None


@dataclass
class Stop:
    station: Location
    arrival: datetime | None = None
    departure: datetime | None = None
    platform: str | None = None
    delay_minutes: int | None = None
    prognosis: Prognosis | None = None


@dataclass
class Leg:
    departure: Stop
    arrival: Stop
    line_name: str | None = None
    category: str | None = None
    direction: str | None = None
    operator: str | None = None
    is_walking: bool = False
    intermediate_stops: list[Stop] = field(default_factory=list)
    capacity_first: int | None = None
    capacity_second: int | None = None


@dataclass
class Connection:
    departure: Stop
    arrival: Stop
    duration: timedelta
    transfers: int
    legs: list[Leg]
    products: list[str]


@dataclass
class StationboardEntry:
    stop: Stop
    line_name: str | None = None
    category: str | None = None
    direction: str | None = None
    operator: str | None = None
    capacity_first: int | None = None
    capacity_second: int | None = None


@dataclass
class Stationboard:
    station: Location
    entries: list[StationboardEntry]
    mode: str = "departure"
