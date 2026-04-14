#!/usr/bin/env python3
"""Probe the local MCP server with a single tool call.

Usage:
    uv run python scripts/probe.py <tool_name> [key=value ...]

Examples:
    uv run python scripts/probe.py list
    uv run python scripts/probe.py get_stationboard station="Zürich HB" limit=6
    uv run python scripts/probe.py plan_journey from_station="Zürich HB" to_station="Bern"
    uv run python scripts/probe.py search_locations query="Technopark"

Spawns the server via `uv run swiss-public-transport-mcp`, speaks MCP over
stdio, prints only the tool's text response (or the tools/list payload).
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys


def parse_arg(s: str):
    """Parse key=value. Value is JSON-decoded if possible, else a string."""
    if "=" not in s:
        raise SystemExit(f"Bad arg {s!r} — expected key=value")
    k, v = s.split("=", 1)
    try:
        return k, json.loads(v)
    except json.JSONDecodeError:
        return k, v


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    tool = sys.argv[1]
    args = dict(parse_arg(a) for a in sys.argv[2:])

    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    if tool == "list":
        messages.append({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    else:
        messages.append(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            }
        )

    proc = subprocess.Popen(
        ["uv", "run", "swiss-public-transport-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin and proc.stdout
    for m in messages:
        proc.stdin.write(json.dumps(m) + "\n")
    proc.stdin.flush()

    # Read line-by-line until we see the response for id=2, then close stdin
    # (telling the server we're done) and wait for clean shutdown.
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id") != 2:
                continue
            if "error" in d:
                print("ERROR:", json.dumps(d["error"], indent=2))
                return 1
            result = d.get("result", {})
            if tool == "list":
                for t in result.get("tools", []):
                    print(f"- {t['name']}: {t.get('description', '').splitlines()[0]}")
            else:
                for block in result.get("content", []):
                    if block.get("type") == "text":
                        print(block["text"])
            return 0
    finally:
        with contextlib.suppress(BrokenPipeError):
            proc.stdin.close()
        proc.wait(timeout=5)

    print("No response", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
