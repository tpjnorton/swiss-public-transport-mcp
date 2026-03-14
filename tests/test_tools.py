from __future__ import annotations

import pytest
from pydantic import ValidationError

from swiss_transport_mcp.tools import (
    SearchConnectionsInput,
    SearchLocationsInput,
    StationboardInput,
)


def test_search_locations_input_defaults():
    inp = SearchLocationsInput(query="Bern")
    assert inp.query == "Bern"
    assert inp.type == "station"
    assert inp.latitude is None


def test_search_locations_input_coordinates():
    inp = SearchLocationsInput(latitude=46.948, longitude=7.439)
    assert inp.latitude == 46.948
    assert inp.longitude == 7.439


def test_search_connections_input_required():
    with pytest.raises(ValidationError):
        SearchConnectionsInput()


def test_search_connections_input_valid():
    inp = SearchConnectionsInput(from_station="Zürich", to_station="Bern")
    assert inp.from_station == "Zürich"
    assert inp.limit == 4
    assert inp.is_arrival_time is False


def test_search_connections_input_limit_bounds():
    with pytest.raises(ValidationError):
        SearchConnectionsInput(from_station="A", to_station="B", limit=0)
    with pytest.raises(ValidationError):
        SearchConnectionsInput(from_station="A", to_station="B", limit=7)


def test_search_connections_input_all_fields():
    inp = SearchConnectionsInput(
        from_station="Zürich",
        to_station="Genève",
        via=["Bern"],
        date="2025-03-15",
        time="08:30",
        is_arrival_time=True,
        transport_types=["train", "bus"],
        limit=2,
    )
    assert inp.via == ["Bern"]
    assert inp.is_arrival_time is True
    assert inp.transport_types == ["train", "bus"]


def test_stationboard_input_defaults():
    inp = StationboardInput(station="Bern")
    assert inp.mode == "departure"
    assert inp.limit == 15


def test_stationboard_input_required():
    with pytest.raises(ValidationError):
        StationboardInput()


def test_stationboard_input_limit_bounds():
    with pytest.raises(ValidationError):
        StationboardInput(station="Bern", limit=0)
    with pytest.raises(ValidationError):
        StationboardInput(station="Bern", limit=41)
