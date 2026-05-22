"""
VAPIX Audio Device Control — Query and configure audio input/output devices.

Endpoint: POST /axis-cgi/audiodevicecontrol.cgi
Docs: https://developer.axis.com/vapix/network-video/audio/

Manages audio input/output hardware settings: gain levels, mute,
connection types (internal mic, line-in, external), and signaling.

Note: This controls audio device *configuration*, not streaming.
Actual audio streaming uses RTSP or separate binary endpoints
which are not practical for MCP.

Methods:
    getDevicesCapabilities  — Hardware capabilities (gain ranges, power types)
    getDevicesSettings      — Current audio device settings
    setDevicesSettings      — Update audio device settings
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/audiodevicecontrol.cgi"


async def get_capabilities(client: VapixClient) -> dict[str, Any]:
    """
    Get audio device capabilities (inputs, outputs, gain ranges).

    Returns dict with devices[] containing inputs/outputs with
    supported connection types, signaling types, gain ranges, etc.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getDevicesCapabilities",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def get_settings(client: VapixClient) -> dict[str, Any]:
    """
    Get current audio device settings.

    Returns dict with devices[] containing current input/output
    settings: selected connection type, gain, mute status, etc.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getDevicesSettings",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def set_settings(client: VapixClient, devices: list[dict[str, Any]]) -> None:
    """
    Update audio device settings.

    Args:
        devices: List of device settings dicts (same structure as
                 returned by get_settings). Pass only changed fields.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "setDevicesSettings",
        "params": {"devices": devices},
    }
    await client.post_json(_PATH, payload)
