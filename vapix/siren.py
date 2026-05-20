"""
VAPIX Siren and Light — Control combo siren+strobe devices.

Endpoint: POST /axis-cgi/siren_and_light.cgi
Docs: https://developer.axis.com/vapix/network-video/siren-and-light/

This API is for dedicated siren/strobe devices (e.g. AXIS D2050-VE),
NOT the standard light control API (lightcontrol.cgi) which controls
built-in camera LEDs.

Supports siren patterns, strobe light colors, intensity, and profiles.
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/siren_and_light.cgi"


async def get_capabilities(client: VapixClient) -> dict[str, Any]:
    """
    Get siren and light capabilities.

    Returns supported patterns, colors, intensity ranges, etc.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getCapabilities",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def get_status(client: VapixClient) -> dict[str, Any]:
    """
    Get current siren and light status.

    Returns empty dict if idle, or active siren/light details
    including pattern, intensity, duration remaining, priority.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getStatus",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def start(
    client: VapixClient,
    *,
    siren: dict[str, Any] | None = None,
    light: dict[str, Any] | None = None,
    profile: str | None = None,
    duration: int | None = None,
    duration_unit: str = "seconds",
) -> dict[str, Any]:
    """
    Activate siren and/or light.

    Either specify siren/light directly, or use a saved profile.

    Args:
        siren: Siren config dict with keys:
               pattern (str), intensity (int), optionally duration
        light: Light config dict with keys:
               pattern (str), speed (int), colors (list[str]), intensity (int)
        profile: Name of a saved profile to use instead of direct config.
        duration: Duration value (applied to both siren and light if set).
        duration_unit: "seconds" or "repetitions" (default: "seconds").

    Returns:
        Dict with sirenId and/or lightId of the activated devices.
    """
    if profile:
        params: dict[str, Any] = {"profile": profile}
    else:
        params = {}
        if siren:
            if duration and "duration" not in siren:
                siren["duration"] = {"unit": duration_unit, "value": duration}
            params["siren"] = siren
        if light:
            if duration and "duration" not in light:
                light["duration"] = {"unit": duration_unit, "value": duration}
            params["light"] = light

    payload = {
        "apiVersion": "1.0",
        "method": "start",
        "params": params,
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def stop(client: VapixClient, what: list[str] | None = None) -> None:
    """
    Stop active siren and/or light.

    Args:
        what: List of things to stop, e.g. ["siren", "light"].
              Defaults to stopping both.
    """
    if what is None:
        what = ["siren", "light"]
    payload = {
        "apiVersion": "1.0",
        "method": "stop",
        "params": {"all": what},
    }
    await client.post_json(_PATH, payload)


async def get_profiles(client: VapixClient) -> list[dict[str, Any]]:
    """List all saved siren/light profiles."""
    payload = {
        "apiVersion": "1.0",
        "method": "getProfiles",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"].get("profiles", [])
