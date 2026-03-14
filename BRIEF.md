**Project: Swiss Public Transport MCP Server**

**Goal:** Build a production-quality MCP server for Swiss public transport that's meaningfully better than existing attempts (grll/sbb-mcp and others), which are thin, outdated wrappers.

**Core API:** `transport.opendata.ch` — free, no auth required, well-documented. Covers trains, buses, trams across the entire Swiss network.

**Key differentiators to build toward:**
- Intermodal journey planning with real constraints ("with my bike", "arriving before 10am")
- Real-time disruption awareness baked into responses
- Natural language handling of Swiss transport specifics (half-fare, GA, bike reservations, panoramic trains)
- Stationboard lookups (next departures from any stop)
- Connection search with multiple legs and fallback options

**Tools to expose (suggested starting set):**
- `search_connections` — A to B with datetime, via, and transport type filters
- `get_stationboard` — live departures from a given station
- `search_locations` — fuzzy station/stop name resolution
- `get_disruptions` — current network disruptions (if the API supports it)

**Tech suggestions:**
- Python with `fastmcp` or the official `mcp` SDK
- Publishable via `uvx` / PyPI (like grll's pubmedmcp pattern — clean install experience)
- Start stdio, add SSE later for remote deployment

**References to look at:**
- `https://transport.opendata.ch/docs` — API docs
- `https://github.com/grll/sbb-mcp` — what exists, what to improve on
- `https://github.com/grll/pubmedmcp` — good pattern for a clean, publishable MCP server

