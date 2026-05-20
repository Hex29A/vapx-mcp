"""
VAPIX I/O Port Management API.

Manages digital input/output ports on Axis cameras and I/O modules.
Uses /axis-cgi/io/portmanagement.cgi with JSON POST requests.

Reference: https://developer.axis.com/vapix/network-video/io-port-management/

Port states use "open"/"closed" strings (not boolean).
- "open"  = circuit open (inactive / high impedance)
- "closed" = circuit closed (active / grounded)

Methods:
    - getPorts: Retrieve all ports and their current states.
    - setPorts: Configure port properties including state.
    - setStateSequence: Apply a timed sequence of state changes.
"""

from typing import Any

from vapix.client import VapixClient

API_VERSION = "1.0"


async def get_ports(client: VapixClient) -> list[dict[str, Any]]:
    """
    Retrieve information about all I/O ports on the device.

    Returns a list of port dicts, each containing:
        - port: Port ID string (e.g. "0", "1")
        - state: Current state ("open" or "closed")
        - configurable: Whether port direction can be changed
        - direction: "input" or "output"
        - name: User-friendly port name
        - normalState: What constitutes the "normal" state

    Example return:
        [
            {"port": "0", "state": "closed", "direction": "input",
             "name": "Call button", "normalState": "open", ...},
            {"port": "1", "state": "open", "direction": "output",
             "name": "Door relay", "normalState": "open", ...}
        ]
    """
    result = await client.post_json(
        "/axis-cgi/io/portmanagement.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vpx-mcp",
            "method": "getPorts",
        },
    )
    return result["data"]["items"]


async def set_port_state(
    client: VapixClient, port: str, state: str
) -> str:
    """
    Set the state of an output port.

    Args:
        port: Port ID string (e.g. "1").
        state: Target state — "open" or "closed".
               "open" = circuit open (inactive)
               "closed" = circuit closed (active)

    Returns:
        "OK" on success.

    Raises:
        VapixError: If the port is read-only or an input port.
    """
    if state not in ("open", "closed"):
        raise ValueError(f"state must be 'open' or 'closed', got '{state}'")

    await client.post_json(
        "/axis-cgi/io/portmanagement.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vpx-mcp",
            "method": "setPorts",
            "params": {
                "ports": [{"port": port, "state": state}]
            },
        },
    )
    return "OK"


async def pulse_port(
    client: VapixClient,
    port: str,
    duration_ms: int = 1000,
) -> str:
    """
    Pulse an output port: close it, wait, then open it again.

    Uses the setStateSequence method for atomic timed execution
    on the device itself (no client-side sleep needed).

    Args:
        port: Port ID string (e.g. "1").
        duration_ms: How long to keep the port closed, in milliseconds.
                     Maximum 65535 ms.

    Returns:
        "OK" on success.
    """
    await client.post_json(
        "/axis-cgi/io/portmanagement.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vpx-mcp",
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
