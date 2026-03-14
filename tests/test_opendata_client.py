from __future__ import annotations

import httpx
import pytest
import respx

from swiss_transport_mcp.clients.opendata import OpenDataClient
from swiss_transport_mcp.errors import RateLimitError, TransportAPIError

BASE = "https://transport.opendata.ch/v1"


@pytest.fixture
def client():
    http = httpx.AsyncClient(base_url=BASE)
    return OpenDataClient(http)


def _locations_response(*stations):
    return {"stations": list(stations)}


def _station(id="8507000", name="Bern", x=46.948, y=7.439, type="station", score=None):
    return {
        "id": id,
        "name": name,
        "type": type,
        "score": score,
        "coordinate": {"type": "WGS84", "x": x, "y": y},
    }


def _connection_response(connections):
    return {"connections": connections}


def _make_connection(
    from_name="Zürich HB",
    to_name="Bern",
    duration="00d00:56:00",
    transfers=0,
    sections=None,
):
    return {
        "from": {"station": _station(name=from_name), "departure": "2025-01-15T14:02:00+0100"},
        "to": {"station": _station(name=to_name), "arrival": "2025-01-15T14:58:00+0100"},
        "duration": duration,
        "transfers": transfers,
        "sections": sections or [_make_section()],
    }


def _make_section(
    journey=None,
    walk=None,
    dep_name="Zürich HB",
    arr_name="Bern",
    dep_time="2025-01-15T14:02:00+0100",
    arr_time="2025-01-15T14:58:00+0100",
    platform="8",
    prognosis=None,
):
    section = {
        "departure": {
            "station": _station(name=dep_name),
            "departure": dep_time,
            "platform": platform,
            "prognosis": prognosis or {},
        },
        "arrival": {
            "station": _station(name=arr_name),
            "arrival": arr_time,
        },
    }
    if walk is not None:
        section["walk"] = walk
    else:
        section["journey"] = journey or {
            "name": "IC 1",
            "category": "IC",
            "to": "Genève-Aéroport",
            "operator": "SBB",
            "passList": [],
            "capacity1st": None,
            "capacity2nd": None,
        }
    return section


def _stationboard_response(station=None, entries=None):
    return {
        "station": station or _station(name="Zürich HB"),
        "stationboard": entries or [],
    }


def _stationboard_entry(
    name="IC 1",
    category="IC",
    to="Genève-Aéroport",
    departure="2025-01-15T14:02:00+0100",
    platform="8",
    prognosis=None,
):
    return {
        "stop": {
            "station": _station(name="Zürich HB"),
            "departure": departure,
            "platform": platform,
            "prognosis": prognosis,
        },
        "name": name,
        "category": category,
        "to": to,
    }


# --- search_locations ---


@respx.mock
async def test_search_locations_text_query(client):
    respx.get(f"{BASE}/locations").mock(
        return_value=httpx.Response(
            200,
            json=_locations_response(
                _station("8507000", "Bern"),
                _station("8507100", "Bern Wankdorf", x=46.969, y=7.466),
            ),
        )
    )
    result = await client.search_locations(query="Bern")
    assert len(result) == 2
    assert result[0].name == "Bern"
    assert result[0].id == "8507000"
    assert result[1].name == "Bern Wankdorf"


@respx.mock
async def test_search_locations_coordinates(client):
    route = respx.get(f"{BASE}/locations").mock(
        return_value=httpx.Response(200, json=_locations_response(_station()))
    )
    await client.search_locations(latitude=46.948, longitude=7.439)
    # Verify x=lat, y=lon (the API quirk)
    request = route.calls[0].request
    assert "x=46.948" in str(request.url)
    assert "y=7.439" in str(request.url)


# --- get_connections ---


@respx.mock
async def test_get_connections_basic(client):
    respx.get(f"{BASE}/connections").mock(
        return_value=httpx.Response(
            200,
            json=_connection_response([_make_connection(), _make_connection(transfers=1)]),
        )
    )
    result = await client.get_connections("Zürich HB", "Bern")
    assert len(result) == 2
    assert result[0].transfers == 0
    assert result[1].transfers == 1
    assert len(result[0].legs) == 1
    assert result[0].legs[0].line_name == "IC 1"


@respx.mock
async def test_get_connections_via_params(client):
    route = respx.get(f"{BASE}/connections").mock(
        return_value=httpx.Response(200, json=_connection_response([_make_connection()]))
    )
    await client.get_connections("Zürich", "Genève", via=["Bern", "Olten"])
    url = str(route.calls[0].request.url)
    assert "via%5B%5D=Bern" in url or "via[]=Bern" in url
    assert "via%5B%5D=Olten" in url or "via[]=Olten" in url


@respx.mock
async def test_get_connections_walking_section(client):
    walk_section = _make_section(
        walk={"duration": 300},
        journey=None,
        dep_name="Zürich HB",
        arr_name="Zürich Stadelhofen",
    )
    # Need to remove the journey key that _make_section adds
    walk_section.pop("journey", None)
    conn = _make_connection(sections=[walk_section])
    respx.get(f"{BASE}/connections").mock(
        return_value=httpx.Response(200, json=_connection_response([conn]))
    )
    result = await client.get_connections("Zürich HB", "Zürich Stadelhofen")
    assert result[0].legs[0].is_walking is True


@respx.mock
async def test_get_connections_with_delay(client):
    section = _make_section(
        prognosis={"departure": "2025-01-15T14:05:00+0100"},
    )
    conn = _make_connection(sections=[section])
    respx.get(f"{BASE}/connections").mock(
        return_value=httpx.Response(200, json=_connection_response([conn]))
    )
    result = await client.get_connections("Zürich HB", "Bern")
    assert result[0].legs[0].departure.delay_minutes == 3


# --- get_stationboard ---


@respx.mock
async def test_get_stationboard(client):
    respx.get(f"{BASE}/stationboard").mock(
        return_value=httpx.Response(
            200,
            json=_stationboard_response(
                entries=[
                    _stationboard_entry("IC 1", "IC", "Genève-Aéroport"),
                    _stationboard_entry("S3", "S", "Wetzikon"),
                ]
            ),
        )
    )
    result = await client.get_stationboard("Zürich HB")
    assert result.station.name == "Zürich HB"
    assert len(result.entries) == 2
    assert result.entries[0].line_name == "IC 1"
    assert result.entries[1].direction == "Wetzikon"


# --- Error handling ---


@respx.mock
async def test_429_triggers_retry(client):
    route = respx.get(f"{BASE}/locations")
    route.side_effect = [
        httpx.Response(429, text="Too many requests"),
        httpx.Response(200, json=_locations_response(_station())),
    ]
    result = await client.search_locations(query="Bern")
    assert len(result) == 1
    assert route.call_count == 2


@respx.mock
async def test_500_triggers_retry(client):
    route = respx.get(f"{BASE}/locations")
    route.side_effect = [
        httpx.Response(500, text="Server error"),
        httpx.Response(200, json=_locations_response(_station())),
    ]
    result = await client.search_locations(query="Bern")
    assert len(result) == 1
    assert route.call_count == 2


@respx.mock
async def test_404_raises_without_retry(client):
    route = respx.get(f"{BASE}/locations")
    route.side_effect = [httpx.Response(404, text="Not found")]
    with pytest.raises(TransportAPIError, match="Client error: 404"):
        await client.search_locations(query="Bern")
    assert route.call_count == 1
