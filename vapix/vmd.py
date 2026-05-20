"""
VAPIX Video Motion Detection 4 — Configure motion detection zones and filters.

Endpoint: POST /local/vmd/control.cgi
Docs: https://developer.axis.com/vapix/network-video/video-motion-detection-4-api/

VMD4 is an ACAP application on the camera. This API controls its configuration
including detection zones, sensitivity filters, and alarm triggers.
"""

from typing import Any

from .client import VapixClient

_PATH = "/local/vmd/control.cgi"


async def get_configuration(client: VapixClient) -> dict[str, Any]:
    """
    Get the current motion detection configuration.

    Returns dict with:
        cameras: list of camera configs (active, id, rotation)
        profiles: list of detection profiles with zones, filters, triggers
        configurationStatus: 0 = OK
    """
    payload = {
        "apiVersion": "1.3",
        "method": "getConfiguration",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def set_configuration(
    client: VapixClient,
    cameras: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> None:
    """
    Set motion detection configuration.

    Args:
        cameras: Camera configs (active, id, rotation).
        profiles: Detection profiles with zones, filters, triggers.
                  Each profile has: name, uid, camera, filters[], triggers[]

    Filter types:
        sizePercentage: [width, height] — minimum object size
        timeShortLivedLimit: seconds — ignore objects shorter than this
        distanceSwayingObject: percentage — ignore swaying objects

    Trigger types:
        includeArea: [[x,y], ...] — polygon where motion is detected
        excludeArea: in filters[] — polygon where motion is ignored
    """
    payload = {
        "apiVersion": "1.3",
        "method": "setConfiguration",
        "params": {
            "cameras": cameras,
            "profiles": profiles,
        },
    }
    await client.post_json(_PATH, payload)


async def get_configuration_capabilities(client: VapixClient) -> dict[str, Any]:
    """Get VMD4 capabilities (supported filters, max profiles, etc.)."""
    payload = {
        "apiVersion": "1.3",
        "method": "getConfigurationCapabilities",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def send_alarm_event(client: VapixClient, profile: int = 1) -> None:
    """
    Send a test alarm event for VMS testing purposes.

    Args:
        profile: Profile UID to trigger the alarm for.
    """
    payload = {
        "apiVersion": "1.3",
        "method": "sendAlarmEvent",
        "params": {"profile": profile},
    }
    await client.post_json(_PATH, payload)
