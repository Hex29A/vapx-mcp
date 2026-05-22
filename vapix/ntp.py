"""
VAPIX NTP — Query and configure NTP time synchronization.

Endpoint: POST /axis-cgi/ntp.cgi
Docs: https://developer.axis.com/vapix/network-video/ntp-api/

Manages the camera's NTP client: check sync status, configure NTP servers,
switch between static and DHCP-provided servers.

Methods:
    getNTPInfo                   — Current NTP status and configuration
    setNTPClientConfiguration    — Update NTP settings
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/ntp.cgi"


async def get_ntp_info(client: VapixClient) -> dict[str, Any]:
    """
    Get NTP client status and configuration.

    Returns dict with:
        enabled           — Whether NTP client is running
        serversSource     — "DHCP" or "static"
        staticServers     — List of configured NTP servers
        advertisedServers — DHCP-provided NTP servers
        synced            — Whether time is synced
        timeToNextSync    — Seconds until next sync
        timeOffset        — Offset in ms (only valid when synced)
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getNTPInfo",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def set_ntp_config(
    client: VapixClient,
    *,
    enabled: bool | None = None,
    servers_source: str | None = None,
    static_servers: list[str] | None = None,
) -> None:
    """
    Update NTP client configuration.

    Args:
        enabled: Enable/disable NTP client.
        servers_source: "static" or "DHCP".
        static_servers: List of NTP server addresses (overwrites existing).
    """
    params: dict[str, Any] = {}
    if enabled is not None:
        params["enabled"] = enabled
    if servers_source is not None:
        params["serversSource"] = servers_source
    if static_servers is not None:
        params["staticServers"] = static_servers

    payload = {
        "apiVersion": "1.0",
        "method": "setNTPClientConfiguration",
        "params": params,
    }
    await client.post_json(_PATH, payload)
