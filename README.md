# swiss-transport-mcp

MCP server for Swiss public transport — connections, stationboards, and real-time delays.

Wraps [transport.opendata.ch](https://transport.opendata.ch) (free, no auth required).

## Install

```bash
pip install swiss-transport-mcp
```

## Usage

```bash
swiss-transport-mcp
```

Add to Claude Desktop config:

```json
{
  "mcpServers": {
    "swiss-transport": {
      "command": "swiss-transport-mcp"
    }
  }
}
```
