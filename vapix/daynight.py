"""
VAPIX Day/Night — Configure IR-cut filter switching for day/night transitions.

Primary endpoint: POST /axis-cgi/daynight.cgi (newer firmware)
Fallback: GET /axis-cgi/param.cgi?group=ImageSource.I0.DayNight (legacy)

Controls how the camera transitions between day mode (color) and night mode
(IR/B&W). Configurable thresholds, dwell times, and IR-pass filter settings.
"""

from typing import Any

import httpx

from .client import VapixClient, VapixError

_PATH = "/axis-cgi/daynight.cgi"
_PARAM_PATH = "/axis-cgi/param.cgi"
_PARAM_GROUP = "ImageSource.I0.DayNight"


def _parse_param_response(text: str) -> dict[str, Any]:
    """Parse param.cgi key=value response into a config dict."""
    result: dict[str, Any] = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # e.g. root.ImageSource.I0.DayNight.IrCutFilter=auto
        short_key = key.rsplit(".", 1)[-1]
        result[short_key] = value
    return result


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
    try:
        data = await client.post_json(_PATH, payload)
        return data["data"]
    except (httpx.HTTPStatusError, VapixError):
        # Fallback: if param.cgi works, report basic capabilities
        resp = await client.get(_PARAM_PATH, {"action": "list", "group": _PARAM_GROUP})
        params = _parse_param_response(resp.text)
        return {
            "source": "param-cgi",
            "IrCutFilter": params.get("IrCutFilter", "unknown"),
            "ShiftLevel": params.get("ShiftLevel", "unknown"),
        }


async def get_configuration(client: VapixClient, channel: int = 0) -> dict[str, Any]:
    """
    Get current day/night configuration for a video channel.

    Tries the modern daynight.cgi first, falls back to param.cgi.
    """
    payload = {
        "apiVersion": "1.2",
        "method": "getConfiguration",
        "params": {"channel": channel},
    }
    try:
        data = await client.post_json(_PATH, payload)
        return data["data"]
    except (httpx.HTTPStatusError, VapixError):
        resp = await client.get(_PARAM_PATH, {"action": "list", "group": _PARAM_GROUP})
        return _parse_param_response(resp.text)


async def set_configuration(
    client: VapixClient,
    channel: int = 0,
    **settings: Any,
) -> None:
    """
    Update day/night configuration.

    Tries the modern daynight.cgi first, falls back to param.cgi.

    Args:
        channel: Video channel (default 0).
        **settings: Any combination of:
            DayNightShiftLevel (int 0-100)
            DayNightDwellTime (int 1-600)
            NightDayShiftLevel (int 0-100)
            NightDayDwellTime (int 1-600)
            Autotune (bool)
            NightFilter ("irpass" or "clear")
            IrCutFilter (str, param.cgi: "auto", "yes", "no")
            ShiftLevel (int, param.cgi: 0-100)
    """
    params: dict[str, Any] = {"channel": channel}
    params.update(settings)
    payload = {
        "apiVersion": "1.2",
        "method": "setConfiguration",
        "params": params,
    }
    try:
        await client.post_json(_PATH, payload)
    except (httpx.HTTPStatusError, VapixError):
        # Fallback: set via param.cgi
        param_settings = {k: v for k, v in settings.items() if k != "channel"}
        for key, val in param_settings.items():
            param = f"{_PARAM_GROUP}.{key}"
            await client.get(_PARAM_PATH, {"action": "update", param: str(val)})
