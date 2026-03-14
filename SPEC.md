# Swiss Transport MCP Server — Full Implementation Spec

## Context

Build a production-quality MCP server for Swiss public transport wrapping `transport.opendata.ch` (free, no auth). Architecture leaves a clear seam for SBB GraphQL enrichment later. The existing `grll/sbb-mcp` is thin (3 tools, v0.1.0, no stationboard, debug breakpoints left in) — we aim to be meaningfully better.

**Package:** `swiss-transport-mcp` | **Import:** `swiss_transport_mcp` | **Python:** >=3.12 | **License:** MIT

---

## Directory Structure

```
swiss-transport-mcp/
├── src/swiss_transport_mcp/
│   ├── __init__.py              # __version__ = "0.1.0"
│   ├── __main__.py              # FastMCP app, lifespan, tool registration, entry point
│   ├── tools.py                 # MCP tool functions (validate → delegate → format)
│   ├── service.py               # Orchestration, station resolution, fallback logic
│   ├── clients/
│   │   ├── __init__.py          # empty
│   │   ├── base.py              # TransportClient Protocol
│   │   └── opendata.py          # transport.opendata.ch implementation
│   ├── models.py                # Dataclass domain models (API-agnostic)
│   ├── formatters.py            # Domain models → LLM-readable text
│   └── errors.py                # Exceptions + retry decorator
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures (mock client, sample data factories)
│   ├── test_opendata_client.py  # Client layer tests with respx
│   ├── test_formatters.py       # Pure formatter tests
│   ├── test_service.py          # Service layer tests with mock client
│   └── test_tools.py            # End-to-end tool tests via FastMCP test client
├── pyproject.toml
├── LICENSE
└── .github/workflows/ci.yml
```

**Layer flow:** Tool (Pydantic request validation) → Service (orchestration) → Client (HTTP) → Models → Formatter → string response

---

## WORKSTREAM A: Foundation (models, errors, protocol)

**Files:** `models.py`, `errors.py`, `clients/base.py`, `clients/__init__.py`

No external dependencies. This is the contract that all other workstreams build against.

### A1: Domain Models (`src/swiss_transport_mcp/models.py`)

All types are `@dataclass`. Not Pydantic — these are internal, no validation needed. Pydantic is only used at the tool boundary for request models.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Location:
    id: str                           # e.g. "8507000"
    name: str                         # e.g. "Bern"
    type: str                         # "station" | "poi" | "address" | "refine"
    latitude: float | None = None     # WGS84
    longitude: float | None = None    # WGS84
    score: float | None = None        # API relevance score (nullable)
    distance: float | None = None     # meters, populated on coordinate search


@dataclass
class Prognosis:
    """Real-time prediction data for a stop."""
    departure: datetime | None = None   # predicted actual departure
    arrival: datetime | None = None     # predicted actual arrival
    platform: str | None = None         # predicted platform (may differ from scheduled)
    capacity_first: int | None = None   # occupancy 0-3 scale (None = unknown)
    capacity_second: int | None = None  # occupancy 0-3 scale (None = unknown)


@dataclass
class Stop:
    """A station at a point in time within a journey."""
    station: Location
    arrival: datetime | None = None
    departure: datetime | None = None
    platform: str | None = None
    delay_minutes: int | None = None    # computed from prognosis - scheduled
    prognosis: Prognosis | None = None


@dataclass
class Leg:
    """One segment of a connection (a single vehicle or walk)."""
    departure: Stop
    arrival: Stop
    line_name: str | None = None        # "IC 1", "S3", "Bus 31", "Tram 4"
    category: str | None = None         # "IC", "IR", "S", "BUS", "TRAM", etc.
    direction: str | None = None        # final destination of the service
    operator: str | None = None         # "SBB", "BLS", "PostAuto", etc.
    is_walking: bool = False
    intermediate_stops: list[Stop] = field(default_factory=list)
    capacity_first: int | None = None   # 0-3
    capacity_second: int | None = None  # 0-3


@dataclass
class Connection:
    """A complete journey from A to B, possibly with multiple legs."""
    departure: Stop                     # first departure
    arrival: Stop                       # final arrival
    duration: timedelta
    transfers: int
    legs: list[Leg]
    products: list[str]                 # unique transport categories used


@dataclass
class StationboardEntry:
    """One row on a departure/arrival board."""
    stop: Stop                          # the departure/arrival at this station
    line_name: str | None = None
    category: str | None = None
    direction: str | None = None        # where this service is heading
    operator: str | None = None
    capacity_first: int | None = None
    capacity_second: int | None = None


@dataclass
class Stationboard:
    """Complete departure or arrival board for a station."""
    station: Location
    entries: list[StationboardEntry]
    mode: str = "departure"             # "departure" | "arrival"
```

### A2: Errors (`src/swiss_transport_mcp/errors.py`)

```python
from __future__ import annotations
import asyncio
import random
from functools import wraps
from typing import Any, Callable


class TransportAPIError(Exception):
    """Base exception for transport API errors."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(TransportAPIError):
    """HTTP 429 from the transport API."""
    pass


class StationNotFoundError(TransportAPIError):
    """No station matched the query."""
    pass


class AmbiguousStationError(TransportAPIError):
    """Multiple stations match — caller should disambiguate."""
    def __init__(self, message: str, candidates: list):
        super().__init__(message)
        self.candidates = candidates  # list[Location]
```

**Retry decorator** (also in `errors.py`):

```python
def retry_on_transient(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator: retries on 429 and 5xx with exponential backoff + jitter."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except TransportAPIError as e:
                    last_exception = e
                    if e.status_code and e.status_code < 500 and not isinstance(e, RateLimitError):
                        raise  # don't retry 4xx (except 429)
                    if attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)
            raise last_exception  # unreachable, but satisfies type checker
        return wrapper
    return decorator
```

### A3: Provider Protocol (`src/swiss_transport_mcp/clients/base.py`)

```python
from __future__ import annotations
from typing import Protocol
from swiss_transport_mcp.models import Location, Connection, Stationboard


class TransportClient(Protocol):
    """Interface for transport data providers.

    OpenData implements this now. SBB GraphQL implements it later.
    The service layer depends on this protocol, not concrete classes.
    """

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
```

---

## WORKSTREAM B: OpenData API Client

**File:** `src/swiss_transport_mcp/clients/opendata.py`
**Depends on:** Workstream A (models, errors, protocol)
**Test file:** `tests/test_opendata_client.py`

### B1: Client Class

```python
import httpx
from swiss_transport_mcp.models import *
from swiss_transport_mcp.errors import TransportAPIError, RateLimitError, retry_on_transient


# Transport type mapping: our public names → API values
TRANSPORT_TYPE_MAP = {
    "train": "train",
    "tram": "tram",
    "ship": "ship",
    "bus": "bus",
    "cableway": "cableway",
}


class OpenDataClient:
    BASE_URL = "https://transport.opendata.ch/v1"

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"User-Agent": "swiss-transport-mcp/0.1.0"},
        )
```

### B2: API Quirks Reference

These are critical for correct implementation:

| Quirk | Detail |
|-------|--------|
| **Coordinate params** | `x` = latitude, `y` = longitude (reversed from typical x=lon, y=lat) |
| **Duration format** | `"00d01:18:00"` — parse with `r'(\d+)d(\d+):(\d+):(\d+)'` → timedelta |
| **isArrivalTime** | Send as `"1"` or `"0"`, not `true`/`false` |
| **via** | Repeated query params: `via[]=Bern&via[]=Olten` |
| **transportations** | Repeated: `transportations[]=train&transportations[]=bus` |
| **Delay computation** | `delay = (prognosis.departure - scheduled_departure).seconds // 60` when prognosis exists |
| **Occupancy** | `capacity1st`/`capacity2nd` are ints 0–3. `null` = unknown |
| **Sections** | Each connection has `sections[]`. A section may have `journey` (transport) or `walk` (walking). Check which is present |
| **Cancelled detection** | A stationboard entry with no prognosis departure but a scheduled departure likely indicates cancellation — verify heuristic |

### B3: Method Signatures and Mapping

**`search_locations`**
- API: `GET /v1/locations?query={q}&x={lat}&y={lon}&type={type}`
- Map `latitude` → param `x`, `longitude` → param `y`
- Parse response `stations[]` → `list[Location]`

**`get_connections`**
- API: `GET /v1/connections?from={from}&to={to}&date={date}&time={time}&isArrivalTime={0|1}&via[]={v}&transportations[]={t}&limit={n}`
- Parse response `connections[]` → `list[Connection]`
- For each connection: iterate `sections[]`, build `Leg` from each section
- For sections with `journey`: extract `journey.name`, `journey.category`, `journey.operator`, `journey.to`
- For sections with `walk`: create `Leg(is_walking=True)`, compute walk duration from timestamps
- Parse `passList[]` into `intermediate_stops`
- Extract `capacity1st`/`capacity2nd` from section level

**`get_stationboard`**
- API: `GET /v1/stationboard?station={s}&limit={n}&datetime={dt}&type={departure|arrival}&transportations[]={t}`
- Note: the API param is `type` for mode, not `mode`
- Parse response `stationboard[]` → `Stationboard`

### B4: Response Parsing Helpers (private methods)

Implement these as private methods on `OpenDataClient`:

- `_parse_location(data: dict) -> Location` — maps API station object to Location
- `_parse_stop(data: dict) -> Stop` — maps API checkpoint with prognosis, computes delay_minutes
- `_parse_connection(data: dict) -> Connection` — maps full connection including sections/legs
- `_parse_section(data: dict) -> Leg` — handles both journey and walk sections
- `_parse_stationboard_entry(data: dict) -> StationboardEntry`
- `_parse_duration(duration_str: str) -> timedelta` — parses `"00d01:18:00"` format

All parsing should be defensive — use `.get()` with defaults, handle `None` gracefully.

### B5: Error Handling in Client

Implement a private `_request` method that wraps `self._client.get()`:
- Check status code
- 429 → raise `RateLimitError`
- 5xx → raise `TransportAPIError` with status code (triggers retry)
- 4xx → raise `TransportAPIError` (no retry)
- Apply `@retry_on_transient()` to each public method

### B6: Tests (`tests/test_opendata_client.py`)

Use `respx` to mock httpx. Test cases:

1. **search_locations with text query** — mock `/v1/locations?query=Bern` → verify Location list
2. **search_locations with coordinates** — verify `x`/`y` param mapping is correct (x=lat, y=lon)
3. **get_connections basic** — mock response with 2 connections, verify Leg parsing, duration, platforms
4. **get_connections with via** — verify `via[]` params are sent correctly
5. **get_connections with walking section** — verify `is_walking=True` leg is created
6. **get_connections with delays** — verify `delay_minutes` computed from prognosis
7. **get_stationboard** — mock response, verify entries parsed correctly
8. **HTTP 429 triggers retry** — mock 429 then 200, verify retry happens
9. **HTTP 500 triggers retry** — similar
10. **HTTP 404 raises without retry** — verify no retry on 4xx

Provide realistic fixture data based on the API response shapes documented above. Put fixture factories in `conftest.py`.

---

## WORKSTREAM C: Formatters

**File:** `src/swiss_transport_mcp/formatters.py`
**Depends on:** Workstream A (models only — no client dependency)
**Test file:** `tests/test_formatters.py`

### C1: Formatting Principles

1. **Text, not JSON** — LLMs process structured text better than raw API dumps
2. **Scannable** — visual separators, aligned columns, bullet indentation
3. **Inline status** — delays and platform changes next to the affected departure
4. **Occupancy visual** — `●○○` (low) / `●●○` (medium) / `●●●` (high) / omitted (unknown)
5. **Computed fields** — transfer times between legs, total delay impact
6. **Truncation** — >10 intermediate stops → first 3, last 2, "... and N more stops"

### C2: `format_locations(locations: list[Location]) -> str`

**Template:**
```
Found {n} station(s) matching "{query}":

1. Bern (ID: 8507000)
   Coordinates: 46.948, 7.439

2. Bern Wankdorf (ID: 8507100)
   Coordinates: 46.969, 7.466
```

- If `locations` is empty: return `"No stations found matching your query."`
- If location has `distance`: append `" | {distance}m away"`
- Only show coordinates if both lat/lon are non-null
- Number each result for easy LLM reference

### C3: `format_connections(connections: list[Connection], from_name: str, to_name: str) -> str`

**Template:**
```
{n} connections from {from_name} to {to_name}:

--- Connection 1 ---
Depart: 14:02  →  Arrive: 14:58  |  Duration: 56 min  |  Transfers: 0

  Leg 1: IC 1 → Genève-Aéroport
    Zürich HB (plat. 8) 14:02  →  Bern 14:58
    ⚠ +3 min delay (expected 15:01)
    Occupancy: 1st ●●○ | 2nd ●●●

--- Connection 2 (2 legs) ---
Depart: 14:15  →  Arrive: 15:42  |  Duration: 1h 27min  |  Transfers: 1

  Leg 1: S3 → Wetzikon
    Zürich HB (plat. 3) 14:15  →  Thalwil 14:28
    On time

  ↔ Transfer at Thalwil (8 min)

  Leg 2: RE → Chur
    Thalwil (plat. 1) 14:36  →  Chur 15:42
    On time
    Occupancy: 1st ●○○ | 2nd ●●○
```

**Logic details:**
- Duration: if <60min show as "Xmin", if >=60min show as "Xh Ymin"
- Transfers count from `connection.transfers`
- For each leg:
  - If `leg.is_walking`: render as `"  🚶 Walk ({duration} min)"` — compute from departure/arrival timestamps
  - Else: render line_name + direction, departure station/platform/time → arrival station/time
  - If `leg.departure.delay_minutes` and > 0: show `"⚠ +N min delay (expected HH:MM)"`
  - If delay_minutes == 0 or None: show `"On time"`
  - Show occupancy only if capacity values are non-null
- Between legs: show `"↔ Transfer at {station} ({N} min)"` — compute gap between prev arrival and next departure
- Show connection header with leg count only if >1 leg

### C4: `format_stationboard(board: Stationboard) -> str`

**Template:**
```
Departures from Zürich HB:

Time   Plat  Line        Destination              Status
─────  ────  ──────────  ───────────────────────  ──────────
14:02  8     IC 1        Genève-Aéroport          +3 min
14:04  3     S3          Wetzikon                 On time
14:07  33    Tram 4      Tiefenbrunnen            On time
14:09  14    IR 36       Basel SBB                ⚠ Cancelled
14:10  52    Bus 31      Hegibachplatz            On time
```

**Logic details:**
- Header: `"Departures from"` or `"Arrivals at"` based on `board.mode`
- Time column: show scheduled time in HH:MM
- Platform: show as-is, or `"—"` if None
- Line: `category + " " + number` from line_name, or just line_name
- Destination: from `entry.direction`
- Status:
  - delay_minutes > 0: `"+N min"`
  - delay_minutes == 0 or None with valid prognosis: `"On time"`
  - No departure prognosis at all but scheduled exists: `"⚠ Cancelled"` (heuristic)
- Use fixed-width formatting. Pad columns with spaces. Line separator is `─` chars.
- If board is empty: `"No departures found for {station_name}."`

### C5: Helper Functions

```python
def _format_time(dt: datetime | None) -> str:
    """Format datetime as HH:MM, or '—' if None."""

def _format_duration(td: timedelta) -> str:
    """Format timedelta as 'Xmin' or 'Xh Ymin'."""

def _format_occupancy(first: int | None, second: int | None) -> str | None:
    """Format occupancy as 'Occupancy: 1st ●●○ | 2nd ●●●' or None if unknown."""
    # Mapping: 0 or None → omit, 1 → ●○○, 2 → ●●○, 3 → ●●●

def _format_delay(delay_minutes: int | None, expected_time: datetime | None) -> str:
    """Format delay status string."""
```

### C6: Tests (`tests/test_formatters.py`)

Test with synthetic dataclass instances (no HTTP mocking needed):

1. **format_locations — normal** — 3 locations → verify numbered output, IDs shown
2. **format_locations — empty** — verify "No stations found" message
3. **format_locations — with distance** — coordinate search results show distance
4. **format_connections — single leg, on time** — verify clean output
5. **format_connections — single leg, delayed** — verify delay warning with expected time
6. **format_connections — multi-leg with transfer** — verify transfer line with computed wait time
7. **format_connections — walking section** — verify walk rendering
8. **format_connections — occupancy display** — verify ●○○/●●○/●●● rendering
9. **format_connections — many intermediate stops** — verify truncation (>10 stops)
10. **format_stationboard — normal** — verify tabular layout, column alignment
11. **format_stationboard — cancelled entry** — verify ⚠ Cancelled
12. **format_stationboard — empty** — verify empty message
13. **_format_duration** — test edge cases: 0min, 59min, 60min, 2h 5min

---

## WORKSTREAM D: Service Layer + Tools + App Wiring

**Files:** `service.py`, `tools.py`, `__main__.py`
**Depends on:** Workstreams A, B, C
**Test files:** `tests/test_service.py`, `tests/test_tools.py`

### D1: Service Layer (`src/swiss_transport_mcp/service.py`)

```python
class TransportService:
    def __init__(self, client: TransportClient):
        self._client = client
```

**Methods mirror the tools but add orchestration logic:**

**`search_locations(...) -> str`**
- Delegates to `client.search_locations()`
- Passes result to `format_locations()`
- Catches `TransportAPIError` → returns readable error string

**`search_connections(...) -> str`**
- Delegates to `client.get_connections()`
- Passes result to `format_connections()`
- **Station resolution logic:** If `get_connections` raises `StationNotFoundError`, automatically try `client.search_locations(query=station_name)`:
  - If exactly 1 result: retry with the resolved station ID
  - If multiple results: raise `AmbiguousStationError` with candidates
  - If 0 results: return error message
- Catches `AmbiguousStationError` → format candidates into a clarification message:
  ```
  Multiple stations match "{name}". Did you mean:
  1. Basel SBB (ID: 8500010)
  2. Basel Badischer Bahnhof (ID: 8500090)
  Please retry with a more specific name or station ID.
  ```
- Catches other `TransportAPIError` → returns readable error string

**`get_stationboard(...) -> str`**
- Delegates to `client.get_stationboard()`
- Passes result to `format_stationboard()`
- Same station resolution fallback as connections
- Catches errors → readable messages

### D2: Tools (`src/swiss_transport_mcp/tools.py`)

Each tool is a thin async function with a Pydantic model for input validation. Tools live here but are registered in `__main__.py`.

```python
from pydantic import BaseModel, Field
from typing import Literal


class SearchLocationsInput(BaseModel):
    query: str | None = Field(None, description="Station name or partial name (e.g., 'Bern', 'Zurich HB')")
    latitude: float | None = Field(None, description="WGS84 latitude for nearby station search")
    longitude: float | None = Field(None, description="WGS84 longitude for nearby station search")
    type: Literal["all", "station", "poi", "address"] = Field("station", description="Location type filter")


class SearchConnectionsInput(BaseModel):
    from_station: str = Field(..., description="Departure station name or ID")
    to_station: str = Field(..., description="Arrival station name or ID")
    via: list[str] | None = Field(None, description="Intermediate stations (up to 5)", max_length=5)
    date: str | None = Field(None, description="Travel date (YYYY-MM-DD). Defaults to today")
    time: str | None = Field(None, description="Travel time (HH:MM). Defaults to now")
    is_arrival_time: bool = Field(False, description="If true, the specified time is the desired arrival time, not departure")
    transport_types: list[Literal["train", "tram", "ship", "bus", "cableway"]] | None = Field(
        None, description="Filter by transport type. Omit for all types"
    )
    limit: int = Field(4, description="Number of connections to return (1-6)", ge=1, le=6)


class StationboardInput(BaseModel):
    station: str = Field(..., description="Station name or ID")
    mode: Literal["departure", "arrival"] = Field("departure", description="Show departures or arrivals")
    limit: int = Field(15, description="Number of entries (1-40)", ge=1, le=40)
    datetime: str | None = Field(None, description="Date and time (YYYY-MM-DD HH:MM). Defaults to now")
    transport_types: list[Literal["train", "tram", "ship", "bus", "cableway"]] | None = Field(
        None, description="Filter by transport type. Omit for all types"
    )
```

**Tool functions:**

```python
async def search_locations(input: SearchLocationsInput, service: TransportService) -> str:
    """Search for Swiss public transport stations, addresses, or points of interest.
    Use this to resolve station names or find stations near coordinates."""
    return await service.search_locations(
        query=input.query, latitude=input.latitude, longitude=input.longitude, loc_type=input.type
    )


async def search_connections(input: SearchConnectionsInput, service: TransportService) -> str:
    """Find train/bus/tram connections between two stations in Switzerland.
    Returns schedules with real-time delays, platforms, and occupancy."""
    return await service.search_connections(
        from_station=input.from_station, to_station=input.to_station,
        via=input.via, date=input.date, time=input.time,
        is_arrival_time=input.is_arrival_time,
        transport_types=input.transport_types, limit=input.limit,
    )


async def get_stationboard(input: StationboardInput, service: TransportService) -> str:
    """Get live departures or arrivals at a Swiss public transport station.
    Shows upcoming services with real-time delay and platform info."""
    return await service.get_stationboard(
        station=input.station, limit=input.limit,
        datetime_str=input.datetime, mode=input.mode,
        transport_types=input.transport_types,
    )
```

### D3: App Wiring (`src/swiss_transport_mcp/__main__.py`)

```python
from contextlib import asynccontextmanager
import httpx
from mcp.server.fastmcp import FastMCP
from swiss_transport_mcp.clients.opendata import OpenDataClient
from swiss_transport_mcp.service import TransportService


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Create shared HTTP client and service on startup, close on shutdown."""
    async with httpx.AsyncClient(
        base_url=OpenDataClient.BASE_URL,
        timeout=httpx.Timeout(15.0, connect=5.0),
        headers={"User-Agent": "swiss-transport-mcp/0.1.0"},
    ) as http_client:
        client = OpenDataClient(http_client)
        service = TransportService(client)
        # Store in server context for tools to access
        yield {"service": service}


mcp = FastMCP(
    "Swiss Public Transport",
    description="Real-time Swiss public transport: connections, stationboards, and station search",
    lifespan=app_lifespan,
)
```

**Tool registration:** Register tools with `@mcp.tool()` decorator. The tool functions access the service via `mcp.get_context()` → `ctx.request_context.lifespan_context["service"]`.

Refer to FastMCP docs for the exact pattern — the key point is:
- Tools are decorated with `@mcp.tool()`
- Inside the tool, get context via `ctx = mcp.get_context()` and then `service = ctx.request_context.lifespan_context["service"]`

**Entry point:**

```python
def main():
    mcp.run()

if __name__ == "__main__":
    main()
```

### D4: `__init__.py`

```python
__version__ = "0.1.0"
```

### D5: Tests

**`tests/conftest.py`** — shared fixtures:
- `mock_client` — a mock implementing `TransportClient` protocol
- `sample_location()`, `sample_connection()`, `sample_stationboard()` — factory functions returning domain model instances with realistic data
- `service` fixture — `TransportService(mock_client)`

**`tests/test_service.py`**:
1. **search_locations delegates to client** — verify client called with correct args
2. **search_connections — happy path** — verify formatted output returned
3. **search_connections — station not found triggers resolution** — mock `StationNotFoundError` then `search_locations` returning 1 match → verify retry with ID
4. **search_connections — ambiguous station** — mock resolution returning 3 matches → verify clarification message
5. **get_stationboard — happy path**
6. **error handling** — `TransportAPIError` → verify readable message, no traceback

**`tests/test_tools.py`** — end-to-end via FastMCP test client:
1. Call each tool with valid input → verify string response
2. Call with invalid input (missing required field) → verify Pydantic error

---

## WORKSTREAM E: Scaffolding & CI

**Files:** `pyproject.toml`, `LICENSE`, `.github/workflows/ci.yml`, `src/swiss_transport_mcp/__init__.py`, `src/swiss_transport_mcp/clients/__init__.py`, `tests/__init__.py`

### E1: `pyproject.toml`

```toml
[project]
name = "swiss-transport-mcp"
dynamic = ["version"]
description = "MCP server for Swiss public transport — connections, stationboards, and real-time delays"
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
    "mcp>=1.13.0",
    "httpx>=0.28.0",
    "pydantic>=2.0.0",
]

[project.scripts]
swiss-transport-mcp = "swiss_transport_mcp.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.version]
path = "src/swiss_transport_mcp/__init__.py"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "respx>=0.22.0",
]
```

### E2: CI (`/.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest
```

### E3: LICENSE — MIT

---

## Agent Assignment

These workstreams can be executed in parallel with the following dependency order:

```
E (scaffold) ──┐
A (models)   ──┼── B (client)  ──┐
               │                  ├── D (service + tools + wiring)
               └── C (formatters)─┘
```

- **Agent 1:** Workstream E (scaffold) + Workstream A (models/errors/protocol) — no deps, do first
- **Agent 2:** Workstream C (formatters + formatter tests) — depends only on models from A
- **Agent 3:** Workstream B (OpenData client + client tests) — depends only on models/errors from A
- **Agent 4:** Workstream D (service + tools + wiring + integration tests) — depends on A, B, C

In practice: Agent 1 goes first (it's fast), then Agents 2 and 3 run in parallel, then Agent 4 wires everything together.

---

## Verification

1. `uv sync --dev` installs cleanly
2. `uv run ruff check . && uv run ruff format --check .` — no issues
3. `uv run pytest` — all tests pass
4. `uv run swiss-transport-mcp` — starts on stdio, no errors
5. Manual test via MCP inspector or Claude Desktop:
   - `search_locations(query="Zürich")` → numbered station list with IDs
   - `search_connections(from_station="Zürich HB", to_station="Bern")` → formatted connections with legs, delays, occupancy
   - `get_stationboard(station="Bern")` → tabular departures with status column
