# swiss-public-transport-mcp

MCP server for Swiss public transport — connections, stationboards, and real-time delays.

Wraps [transport.opendata.ch](https://transport.opendata.ch) (free, no auth required).

## Install

```bash
git clone https://github.com/tpjnorton/swiss-public-transport-mcp.git
cd swiss-public-transport-mcp
uv sync
```

## Usage

```bash
uv run swiss-public-transport-mcp
```

Add to Claude Desktop config:

```json
{
  "mcpServers": {
    "swiss-transport": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/swiss-public-transport-mcp", "swiss-public-transport-mcp"]
    }
  }
}
```
