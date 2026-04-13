# swiss-public-transport-mcp

MCP server for Swiss public transport — connections, stationboards, real-time delays, and direct booking links for SBB.

Wraps [transport.opendata.ch](https://transport.opendata.ch) — **free, no API key, no signup**. Covers the full Swiss network (SBB, Postauto, regional, trams, buses, ships, cableways).

## Why this server

- **Zero config.** Install and go — no account, no token, no env vars.
- **Booking links.** Returns deep links into SBB.ch so the user can buy a ticket in one click.
- **Disambiguation built in.** Ambiguous station names return candidates instead of failing silently.
- **Compact, model-friendly output.** Formatted text designed for LLM context windows, not raw JSON dumps.

## Tools

| Tool | Purpose |
|---|---|
| `search_locations` | Resolve a station/stop/POI by name or coordinates |
| `search_connections` | Plan A → B with via, transport-type filters, arrival-time mode |
| `get_stationboard` | Live departures or arrivals from any stop |
| `get_booking_link` | Build an SBB.ch URL for a journey so the user can buy a ticket |

## Install

No install needed — run directly with [`uvx`](https://docs.astral.sh/uv/):

```bash
uvx swiss-public-transport-mcp
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "swiss-transport": {
      "command": "uvx",
      "args": ["swiss-public-transport-mcp"]
    }
  }
}
```

Config file location:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Development

```bash
git clone https://github.com/tpjnorton/swiss-public-transport-mcp.git
cd swiss-public-transport-mcp
uv sync
uv run swiss-public-transport-mcp
```

## Related project

If you need official `opentransportdata.swiss` data — SIRI-SX disruption alerts, occupancy forecasts, OJP Fare ticket prices, train formation — see [malkreide/swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp). It exposes ~11 tools across the official OJP 2.0 / SIRI / CKAN APIs and requires a (free) API key from the opentransportdata.swiss API Manager.

| | this server | malkreide/swiss-transport-mcp |
|---|---|---|
| Data source | transport.opendata.ch | opentransportdata.swiss (official) |
| API key | none | required (free signup) |
| Tools | 4 (journey planning + booking links) | 11 (planning + disruptions + occupancy + fares + formation) |
| Setup | one command | per-API key configuration |
| Best for | quick journey planning, fast LLM responses, ticket purchase flow | rich operational data, official feeds |

The two servers cover overlapping but distinct use cases — you can install both side by side.
