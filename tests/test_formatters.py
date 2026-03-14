from __future__ import annotations

from datetime import datetime, timedelta

from swiss_transport_mcp.formatters import (
    _format_duration,
    _format_occupancy,
    format_connections,
    format_locations,
    format_stationboard,
)
from swiss_transport_mcp.models import Prognosis

from .conftest import (
    sample_connection,
    sample_leg,
    sample_location,
    sample_stationboard,
    sample_stationboard_entry,
    sample_stop,
)


# --- format_locations ---


def test_format_locations_normal():
    locs = [
        sample_location(id="8507000", name="Bern"),
        sample_location(id="8507100", name="Bern Wankdorf", latitude=46.969, longitude=7.466),
        sample_location(id="8507200", name="Bern Bümpliz", latitude=46.937, longitude=7.390),
    ]
    result = format_locations(locs)
    assert "Found 3 station(s)" in result
    assert "1. Bern (ID: 8507000)" in result
    assert "2. Bern Wankdorf (ID: 8507100)" in result
    assert "3. Bern Bümpliz (ID: 8507200)" in result


def test_format_locations_empty():
    result = format_locations([])
    assert "No stations found" in result


def test_format_locations_with_distance():
    loc = sample_location(name="Bern", distance=250.0)
    result = format_locations([loc])
    assert "250m away" in result


# --- format_connections ---


def test_format_connections_single_leg_on_time():
    conn = sample_connection()
    result = format_connections([conn], "Zürich HB", "Bern")
    assert "1 connection(s) from Zürich HB to Bern" in result
    assert "14:02" in result
    assert "14:58" in result
    assert "56min" in result
    assert "On time" in result


def test_format_connections_single_leg_delayed():
    prognosis = Prognosis(departure=datetime(2025, 1, 15, 14, 5))
    leg = sample_leg(delay_minutes=3, prognosis=prognosis)
    conn = sample_connection(legs=[leg])
    result = format_connections([conn], "Zürich HB", "Bern")
    assert "+3 min delay" in result
    assert "expected 14:05" in result


def test_format_connections_multi_leg_with_transfer():
    leg1 = sample_leg(
        dep_name="Zürich HB",
        arr_name="Thalwil",
        dep_time=datetime(2025, 1, 15, 14, 15),
        arr_time=datetime(2025, 1, 15, 14, 28),
        line_name="S3",
        category="S",
        direction="Wetzikon",
    )
    leg2 = sample_leg(
        dep_name="Thalwil",
        arr_name="Chur",
        dep_time=datetime(2025, 1, 15, 14, 36),
        arr_time=datetime(2025, 1, 15, 15, 42),
        dep_platform="1",
        line_name="RE",
        category="RE",
        direction="Chur",
    )
    conn = sample_connection(
        legs=[leg1, leg2], duration=timedelta(hours=1, minutes=27), transfers=1
    )
    result = format_connections([conn], "Zürich HB", "Chur")
    assert "2 legs" in result
    assert "Transfers: 1" in result
    assert "Transfer at Thalwil (8 min)" in result
    assert "S3" in result
    assert "RE" in result


def test_format_connections_walking_section():
    leg = sample_leg(
        dep_name="Zürich HB",
        arr_name="Zürich Stadelhofen",
        dep_time=datetime(2025, 1, 15, 14, 0),
        arr_time=datetime(2025, 1, 15, 14, 7),
        is_walking=True,
        line_name=None,
        category=None,
        direction=None,
    )
    conn = sample_connection(legs=[leg], duration=timedelta(minutes=7))
    result = format_connections([conn], "Zürich HB", "Zürich Stadelhofen")
    assert "Walk" in result
    assert "7 min" in result


def test_format_connections_occupancy():
    leg = sample_leg(capacity_first=1, capacity_second=3)
    conn = sample_connection(legs=[leg])
    result = format_connections([conn], "Zürich HB", "Bern")
    assert "●○○" in result
    assert "●●●" in result


def test_format_connections_empty():
    result = format_connections([], "Zürich HB", "Bern")
    assert "No connections found" in result


# --- format_stationboard ---


def test_format_stationboard_normal():
    entries = [
        sample_stationboard_entry(
            line_name="IC 1",
            direction="Genève-Aéroport",
            platform="8",
            departure=datetime(2025, 1, 15, 14, 2),
            prognosis=Prognosis(departure=datetime(2025, 1, 15, 14, 2)),
            delay_minutes=0,
        ),
        sample_stationboard_entry(
            line_name="S3",
            direction="Wetzikon",
            platform="3",
            departure=datetime(2025, 1, 15, 14, 4),
            prognosis=Prognosis(departure=datetime(2025, 1, 15, 14, 4)),
            delay_minutes=0,
        ),
    ]
    board = sample_stationboard(station_name="Zürich HB", entries=entries)
    result = format_stationboard(board)
    assert "Departures from Zürich HB" in result
    assert "IC 1" in result
    assert "S3" in result
    assert "Genève-Aéroport" in result
    assert "On time" in result


def test_format_stationboard_cancelled():
    entry = sample_stationboard_entry(
        line_name="IR 36",
        direction="Basel SBB",
        departure=datetime(2025, 1, 15, 14, 9),
        prognosis=None,
        delay_minutes=None,
    )
    board = sample_stationboard(station_name="Zürich HB", entries=[entry])
    result = format_stationboard(board)
    assert "Cancelled" in result


def test_format_stationboard_delayed():
    entry = sample_stationboard_entry(
        line_name="IC 1",
        direction="Genève-Aéroport",
        departure=datetime(2025, 1, 15, 14, 2),
        prognosis=Prognosis(departure=datetime(2025, 1, 15, 14, 5)),
        delay_minutes=3,
    )
    board = sample_stationboard(station_name="Zürich HB", entries=[entry])
    result = format_stationboard(board)
    assert "+3 min" in result


def test_format_stationboard_empty():
    board = sample_stationboard(station_name="Nowhere", entries=[])
    result = format_stationboard(board)
    assert "No departures found for Nowhere" in result


def test_format_stationboard_arrivals():
    board = sample_stationboard(station_name="Bern", entries=[], mode="arrival")
    result = format_stationboard(board)
    assert "No arrivals found for Bern" in result


# --- _format_duration ---


def test_format_duration_zero():
    assert _format_duration(timedelta()) == "0min"


def test_format_duration_under_60():
    assert _format_duration(timedelta(minutes=45)) == "45min"


def test_format_duration_exactly_60():
    assert _format_duration(timedelta(hours=1)) == "1h"


def test_format_duration_over_60():
    assert _format_duration(timedelta(hours=2, minutes=5)) == "2h 5min"


# --- _format_occupancy ---


def test_format_occupancy_both():
    result = _format_occupancy(1, 3)
    assert "1st ●○○" in result
    assert "2nd ●●●" in result


def test_format_occupancy_none():
    assert _format_occupancy(None, None) is None


def test_format_occupancy_zero():
    assert _format_occupancy(0, 0) is None
