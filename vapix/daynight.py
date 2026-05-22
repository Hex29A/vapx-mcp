"""
VAPIX Day/Night — Configure IR-cut filter switching for day/night transitions.

Endpoint: POST /axis-cgi/daynight.cgi
Docs: https://developer.axis.com/vapix/network-video/day-night/

Controls how the camera transitions between day mode (color) and night mode
(IR/B&W). Configurable thresholds, dwell times, and IR-pass filter settings.

Methods:
    getCapabilities    — Check supported features per channel
    getConfiguration   — Get current day/night settings
    setConfiguration   — Update day/night settings
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/daynight.cgi"


async def get_capabilities(client: VapixClient, channel: int = 0) -> dict[str, Any]:
    """
    Get day/night capabilities for a video channel.

    Returns dict with:
        AutotuneSupport       — Whether auto-tuning is supported
        IrPassSupport         — Whether IR-pass filter is supported
        NightDayShiftLevelSupport — Whether shift level is configurable
    """
    payload = {
        "apiVersion": "1.2",
        "method": "getCapabilities",
        "params": {"channel": channel},
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def get_configuration(client: VapixClient, channel: int = 0) -> dict[str, Any]:
    """
    Get current day/night configuration for a video channel.

    Returns dict with:
        DayNightShiftLevel  — Day→Night threshold (0-100)
        DayNightDwellTime   — Seconds before switching day→night (1-600)
        NightDayShiftLevel  — Night→Day threshold (0-100)
        NightDayDwellTime   — Seconds before switching night→day (1-600)
        Autotune            — Whether auto-tuning is enabled
        NightFilter         — "irpass" or "clear"
    """
    payload = {
        "apiVersion": "1.2",
        "method": "getConfiguration",
        "params": {"channel": channel},
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def set_configuration(
    client: VapixClient,
    channel: int = 0,
    **settings: Any,
) -> None:
    """
    Update day/night configuration.

    Args:
        channel: Video channel (default 0).
        **settings: Any combination of:
            DayNightShiftLevel (int 0-100)
            DayNightDwellTime (int 1-600)
            NightDayShiftLevel (int 0-100)
            NightDayDwellTime (int 1-600)
            Autotune (bool)
            NightFilter ("irpass" or "clear")
    """
    params: dict[str, Any] = {"channel": channel}
    params.update(settings)
    payload = {
        "apiVersion": "1.2",
        "method": "setConfiguration",
        "params": params,
    }
    await client.post_json(_PATH, payload)
