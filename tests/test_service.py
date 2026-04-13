from __future__ import annotations

from swiss_public_transport_mcp.errors import AmbiguousStationError, TransportAPIError

from .conftest import sample_connection, sample_location, sample_stationboard

# --- search_locations ---


async def test_search_locations_delegates(mock_client, service):
    locs = [sample_location(name="Bern"), sample_location(name="Bern Wankdorf")]
    mock_client.search_locations.return_value = locs

    result = await service.search_locations(query="Bern")
    mock_client.search_locations.assert_called_once_with(
        query="Bern", latitude=None, longitude=None, loc_type="all"
    )
    assert "Bern" in result
    assert "Bern Wankdorf" in result


async def test_search_locations_error(mock_client, service):
    mock_client.search_locations.side_effect = TransportAPIError("API down", status_code=500)
    result = await service.search_locations(query="Bern")
    assert "Error" in result


# --- search_connections ---


async def test_search_connections_happy_path(mock_client, service):
    mock_client.get_connections.return_value = [sample_connection()]
    result = await service.search_connections(from_station="Zürich HB", to_station="Bern")
    assert "connection" in result.lower()
    assert "Zürich HB" in result


async def test_search_connections_ambiguous_station(mock_client, service):
    candidates = [
        sample_location(id="8500010", name="Basel SBB"),
        sample_location(id="8500090", name="Basel Badischer Bahnhof"),
    ]
    mock_client.get_connections.side_effect = AmbiguousStationError(
        "Ambiguous", candidates=candidates
    )
    result = await service.search_connections(from_station="Basel", to_station="Bern")
    assert "Multiple stations match" in result
    assert "Basel SBB" in result
    assert "Basel Badischer Bahnhof" in result


async def test_search_connections_error(mock_client, service):
    mock_client.get_connections.side_effect = TransportAPIError("Timeout", status_code=500)
    result = await service.search_connections(from_station="Zürich", to_station="Bern")
    assert "Error" in result
    # No traceback leaked
    assert "Traceback" not in result


# --- get_stationboard ---


async def test_get_stationboard_happy_path(mock_client, service):
    board = sample_stationboard(station_name="Bern")
    mock_client.get_stationboard.return_value = board
    result = await service.get_stationboard(station="Bern")
    # Empty board returns the "no departures" message
    assert "Bern" in result


async def test_get_stationboard_error(mock_client, service):
    mock_client.get_stationboard.side_effect = TransportAPIError("Down", status_code=503)
    result = await service.get_stationboard(station="Bern")
    assert "Error" in result
    assert "Traceback" not in result
