"""
VAPIX I/O Port Management API.

Manages digital input/output ports on Axis cameras and I/O modules.

Primary:  POST /axis-cgi/io/portmanagement.cgi (modern JSON API)
Fallback: GET  /axis-cgi/io/port.cgi + param.cgi (legacy, Artpec-5 / old FW)

Note: portmanagement.cgi uses 0-based port IDs ("0", "1").
      Legacy io/port.cgi uses 1-based port numbers (action=1:/).
"""

from typing import Any

import httpx

from vapix.client import VapixClient, VapixError

API_VERSION = "1.0"

_MODERN_PATH = "/axis-cgi/io/portmanagement.cgi"
_LEGACY_PORT_PATH = "/axis-cgi/io/port.cgi"
_LEGACY_PARAM_PATH = "/axis-cgi/param.cgi"


# ---------------------------------------------------------------------------
# Legacy fallback helpers
# ---------------------------------------------------------------------------

def _parse_legacy_ports(param_text: str, state_text: str) -> list[dict[str, Any]]:
    """Parse legacy param.cgi + port.cgi responses into modern port format."""
    # Parse port config from param.cgi (IOPort group)
    # Port IDs are like I0, I1 (inputs), O0, O1 (outputs) — collect in order seen.
    seen_ids: list[str] = []
    port_data: dict[str, dict[str, Any]] = {}
    for line in param_text.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # e.g. root.IOPort.I0.Direction=input
        parts = key.split(".")
        if len(parts) < 4 or parts[1] != "IOPort":
            continue
        port_id = parts[2]  # "I0", "O0", etc.
        field = parts[3] if len(parts) > 3 else ""
        if port_id not in port_data:
            seen_ids.append(port_id)
            port_data[port_id] = {"port": str(len(seen_ids) - 1)}
        if field == "Direction":
            port_data[port_id]["direction"] = value.lower()
        elif field == "Usage":
            port_data[port_id]["name"] = value

    # Build ordered list
    ports = [port_data[pid] for pid in seen_ids]

    # Parse active states from port.cgi
    # Response: "port1=active\nport2=inactive\n" or similar
    for line in state_text.strip().splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # "port1" → index 0 (1-based to 0-based)
        if key.startswith("port"):
            idx = int(key[4:]) - 1
            if 0 <= idx < len(ports):
                ports[idx]["state"] = "closed" if value.strip() == "active" else "open"

    return ports


async def _legacy_get_ports(client: VapixClient) -> list[dict[str, Any]]:
    """Get ports via legacy param.cgi + port.cgi."""
    param_resp = await client.get(_LEGACY_PARAM_PATH, {"action": "list", "group": "IOPort"})
    # Determine number of ports from param response
    port_count = 0
    for line in param_resp.text.splitlines():
        if ".Direction=" in line:
            port_count += 1
    if port_count == 0:
        return []
    port_ids = ",".join(str(i + 1) for i in range(port_count))
    state_resp = await client.get(_LEGACY_PORT_PATH, {"checkactive": port_ids})
    return _parse_legacy_ports(param_resp.text, state_resp.text)


async def _legacy_set_port(client: VapixClient, port: str, state: str) -> str:
    """Set port state via legacy port.cgi. Port is 0-based, legacy is 1-based."""
    legacy_port = int(port) + 1
    # "/" = activate (closed), "\\" = deactivate (open)
    action_char = "/" if state == "closed" else "\\"
    await client.get(_LEGACY_PORT_PATH, {"action": f"{legacy_port}:{action_char}"})
    return "OK"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_ports(client: VapixClient) -> list[dict[str, Any]]:
    """
    Retrieve information about all I/O ports on the device.

    Tries modern portmanagement.cgi first, falls back to legacy port.cgi.

    Returns a list of port dicts, each containing:
        - port: Port ID string (e.g. "0", "1")
        - state: Current state ("open" or "closed")
        - direction: "input" or "output"
        - name: User-friendly port name
    """
    try:
        result = await client.post_json(
            _MODERN_PATH,
            {
                "apiVersion": API_VERSION,
                "context": "vapx-mcp",
                "method": "getPorts",
            },
        )
        return result["data"].get("items", [])
    except (httpx.HTTPStatusError, VapixError):
        return await _legacy_get_ports(client)


async def set_port_state(
    client: VapixClient, port: str, state: str
) -> str:
    """
    Set the state of an output port.

    Tries modern portmanagement.cgi first, falls back to legacy port.cgi.

    Args:
        port: Port ID string (e.g. "0"). Zero-based.
        state: Target state — "open" or "closed".

    Returns:
        "OK" on success.
    """
    if state not in ("open", "closed"):
        raise ValueError(f"state must be 'open' or 'closed', got '{state}'")

    try:
        await client.post_json(
            _MODERN_PATH,
            {
                "apiVersion": API_VERSION,
                "context": "vapx-mcp",
                "method": "setPorts",
                "params": {
                    "ports": [{"port": port, "state": state}]
                },
            },
        )
        return "OK"
    except (httpx.HTTPStatusError, VapixError):
        return await _legacy_set_port(client, port, state)


async def pulse_port(
    client: VapixClient,
    port: str,
    duration_ms: int = 1000,
) -> str:
    """
    Pulse an output port: close it, wait, then open it again.

    Uses setStateSequence on modern firmware. On legacy devices,
    falls back to a simple set closed → set open sequence (note:
    timing is approximate on legacy devices).

    Args:
        port: Port ID string (e.g. "1"). Zero-based.
        duration_ms: How long to keep the port closed, in milliseconds.

    Returns:
        "OK" on success.
    """
    try:
        await client.post_json(
            _MODERN_PATH,
            {
                "apiVersion": API_VERSION,
                "context": "vapx-mcp",
                "method": "setStateSequence",
                "params": {
                    "port": port,
                    "sequence": [
                        {"state": "closed", "time": duration_ms},
                        {"state": "open", "time": 0},
                    ],
                },
            },
        )
        return "OK"
    except (httpx.HTTPStatusError, VapixError):
        # Legacy: set closed, then open (no precise timing)
        await _legacy_set_port(client, port, "closed")
        await _legacy_set_port(client, port, "open")
        return "OK"
