from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

from swiss_public_transport_mcp.models import Connection, Location, Stationboard

OCCUPANCY = {1: "\u25cf\u25cb\u25cb", 2: "\u25cf\u25cf\u25cb", 3: "\u25cf\u25cf\u25cf"}

SBB_BASE_URL = "https://www.sbb.ch/en"


def build_sbb_url(
    from_station: str,
    to_station: str,
    date: str | None = None,
    time: str | None = None,
    is_arrival_time: bool = False,
) -> str:
    """Build a deep link to the SBB timetable/booking page.

    Args:
        from_station: Origin station name.
        to_station: Destination station name.
        date: Travel date as YYYY-MM-DD.
        time: Travel time as HH:MM.
        is_arrival_time: If True, time is desired arrival; otherwise departure.
    """
    params = [
        ("von", from_station),
        ("nach", to_station),
    ]
    if date:
        params.append(("day", date))
    if time:
        # SBB frontend uses underscore as separator (HH_MM), not colon
        params.append(("time", time.replace(":", "_")))
    moment = "arr" if is_arrival_time else "dep"
    params.append(("moment", moment))
    query = "&".join(f"{k}={quote(v, safe='":-_')}" for k, v in params)
    return f"{SBB_BASE_URL}?{query}"


def _format_time(dt: datetime | None) -> str:
    if dt is None:
        return "\u2014"
    return dt.strftime("%H:%M")


def _format_duration(td: timedelta) -> str:
    total_minutes = int(td.total_seconds()) // 60
    if total_minutes < 60:
        return f"{total_minutes}min"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}min"


def _format_occupancy(first: int | None, second: int | None) -> str | None:
    parts = []
    if first and first in OCCUPANCY:
        parts.append(f"1st {OCCUPANCY[first]}")
    if second and second in OCCUPANCY:
        parts.append(f"2nd {OCCUPANCY[second]}")
    if not parts:
        return None
    return "Occupancy: " + " | ".join(parts)


def _format_delay(delay_minutes: int | None, expected_time: datetime | None) -> str:
    if delay_minutes is not None and delay_minutes > 0:
        msg = f"\u26a0 +{delay_minutes} min delay"
        if expected_time:
            msg += f" (expected {_format_time(expected_time)})"
        return msg
    return "On time"


def format_locations(locations: list[Location]) -> str:
    if not locations:
        return "No stations found matching your query."

    lines = [f"Found {len(locations)} station(s):\n"]
    for i, loc in enumerate(locations, 1):
        line = f"{i}. {loc.name} (ID: {loc.id})"
        if loc.distance is not None:
            line += f" | {loc.distance:.0f}m away"
        lines.append(line)
        if loc.latitude is not None and loc.longitude is not None:
            lines.append(f"   Coordinates: {loc.latitude:.4f}, {loc.longitude:.4f}")
    return "\n".join(lines)


def format_connections(
    connections: list[Connection],
    from_name: str,
    to_name: str,
    date: str | None = None,
    time: str | None = None,
    is_arrival_time: bool = False,
) -> str:
    if not connections:
        return f"No connections found from {from_name} to {to_name}."

    lines = [f"{len(connections)} connection(s) from {from_name} to {to_name}:\n"]

    for idx, conn in enumerate(connections, 1):
        dep_time = _format_time(conn.departure.departure)
        arr_time = _format_time(conn.arrival.arrival)
        dur = _format_duration(conn.duration)

        header = f"--- Connection {idx}"
        if len(conn.legs) > 1:
            header += f" ({len(conn.legs)} legs)"
        header += " ---"
        lines.append(header)
        lines.append(
            f"Depart: {dep_time}  \u2192  Arrive: {arr_time}  |  "
            f"Duration: {dur}  |  Transfers: {conn.transfers}"
        )
        lines.append("")

        for leg_idx, leg in enumerate(conn.legs):
            # Transfer line between legs
            if leg_idx > 0:
                prev_leg = conn.legs[leg_idx - 1]
                if prev_leg.arrival.arrival and leg.departure.departure:
                    gap = (
                        int((leg.departure.departure - prev_leg.arrival.arrival).total_seconds())
                        // 60
                    )
                    transfer_station = leg.departure.station.name
                    lines.append(f"  \u21d4 Transfer at {transfer_station} ({gap} min)")
                    lines.append("")

            if leg.is_walking:
                walk_min = ""
                if leg.departure.departure and leg.arrival.arrival:
                    mins = (
                        int((leg.arrival.arrival - leg.departure.departure).total_seconds()) // 60
                    )
                    walk_min = f" ({mins} min)"
                lines.append(f"  \U0001f6b6 Walk{walk_min}")
            else:
                leg_label = f"  Leg {leg_idx + 1}: {leg.line_name or '?'}"
                if leg.direction:
                    leg_label += f" \u2192 {leg.direction}"
                lines.append(leg_label)

                dep_station = leg.departure.station.name
                arr_station = leg.arrival.station.name
                dep_plat = f" (plat. {leg.departure.platform})" if leg.departure.platform else ""
                dep_t = _format_time(leg.departure.departure)
                arr_t = _format_time(leg.arrival.arrival)
                lines.append(f"    {dep_station}{dep_plat} {dep_t}  \u2192  {arr_station} {arr_t}")

                expected = leg.departure.prognosis.departure if leg.departure.prognosis else None
                lines.append(f"    {_format_delay(leg.departure.delay_minutes, expected)}")

                occ = _format_occupancy(leg.capacity_first, leg.capacity_second)
                if occ:
                    lines.append(f"    {occ}")

            lines.append("")

    url = build_sbb_url(from_name, to_name, date=date, time=time, is_arrival_time=is_arrival_time)
    lines.append(f"Book tickets: {url}")

    return "\n".join(lines).rstrip()


def format_stationboard(board: Stationboard) -> str:
    if not board.entries:
        label = "departures" if board.mode == "departure" else "arrivals"
        return f"No {label} found for {board.station.name}."

    header_verb = "Departures from" if board.mode == "departure" else "Arrivals at"
    lines = [f"{header_verb} {board.station.name}:\n"]

    # Column widths
    w_time = 5
    w_plat = 4
    w_line = 10
    w_dest = 24
    w_status = 12

    lines.append(
        f"{'Time':<{w_time}}  {'Plat':<{w_plat}}  {'Line':<{w_line}}  "
        f"{'Destination':<{w_dest}}  {'Status':<{w_status}}"
    )
    lines.append(
        f"{'\u2500' * w_time}  {'\u2500' * w_plat}  {'\u2500' * w_line}  "
        f"{'\u2500' * w_dest}  {'\u2500' * w_status}"
    )

    for entry in board.entries:
        time_str = _format_time(entry.stop.departure or entry.stop.arrival)
        plat = entry.stop.platform or "\u2014"
        line = entry.line_name or ""
        dest = entry.direction or ""

        # Status logic. The opendata.ch API has no reliable cancellation
        # signal, so we only report delays and confirmed on-time status.
        # Absence of real-time data (common 1+ days ahead) => blank status.
        delay = entry.stop.delay_minutes
        has_prognosis = entry.stop.prognosis is not None

        if delay is not None and delay > 0:
            status = f"+{delay} min"
        elif has_prognosis:
            status = "On time"
        else:
            status = ""

        lines.append(
            f"{time_str:<{w_time}}  {plat:<{w_plat}}  {line:<{w_line}}  {dest:<{w_dest}}  {status}"
        )

    return "\n".join(lines)
