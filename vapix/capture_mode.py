"""
VAPIX Capture Mode — Query and switch video capture modes (resolution/FPS).

Endpoint: POST /axis-cgi/capturemode.cgi
Docs: https://developer.axis.com/vapix/network-video/capture-mode/

Capture modes define the sensor resolution and max frame rate.
Switching capture modes requires a camera reboot to take effect.

Methods:
    getCaptureModes  — List available capture modes per channel
    setCaptureMode   — Switch to a different capture mode (reboot required)
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/capturemode.cgi"


async def get_capture_modes(client: VapixClient) -> list[dict[str, Any]]:
    """
    List available capture modes for all video channels.

    Returns list of channel dicts, each containing:
        channel       — Channel index (int)
        captureMode[] — Available modes with:
            captureModeId  — ID to pass to set_capture_mode
            enabled        — Whether this mode is currently active
            maxFPS         — Max frame rate (only guaranteed when enabled)
            description    — e.g. "1920x1080 (16:9) @ 30/60 fps"
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getCaptureModes",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def set_capture_mode(
    client: VapixClient,
    channel: int,
    capture_mode_id: int,
) -> None:
    """
    Switch to a different capture mode. Requires camera reboot to take effect.

    Args:
        channel: Video channel index (usually 0).
        capture_mode_id: Mode ID from get_capture_modes.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "setCaptureMode",
        "params": {
            "channel": channel,
            "captureModeId": capture_mode_id,
        },
    }
    await client.post_json(_PATH, payload)
