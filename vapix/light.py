"""
VAPIX Light Control API.

Controls IR and white light LEDs on Axis cameras via
/axis-cgi/lightcontrol.cgi (JSON POST).

Reference: https://developer.axis.com/vapix/network-video/light-control/

Important: The API uses activateLight/deactivateLight to turn lights on/off,
NOT a generic "setLightState" method. A light must be enabled before it can
be activated.

Light IDs are strings like "led0", "led1". Use getLightInformation to
discover available lights and their types (IR, WHITE, INDICATOR).
"""

from typing import Any

from vapix.client import VapixClient

API_VERSION = "1.0"


async def get_light_information(client: VapixClient) -> list[dict[str, Any]]:
    """
    List all lights on the device and their current state/configuration.

    Returns a list of light info dicts, each containing:
        - lightID: Unique light identifier (e.g. "led0")
        - lightType: Type of light ("IR", "WHITE", etc.)
        - enabled: Whether the light is enabled (can be activated)
        - lightState: Whether the light is currently on
        - synchronizeDayNightMode: Auto day/night sync status
        - automaticIntensityMode: Auto intensity status
        - nrOfLEDs: Number of LEDs in this light group
        - error: Whether a hardware error has occurred
        - errorInfo: Error description if error is true

    Example return:
        [
            {"lightID": "led0", "lightType": "IR", "enabled": true,
             "lightState": false, "nrOfLEDs": 1, ...}
        ]
    """
    result = await client.post_json(
        "/axis-cgi/lightcontrol.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vapx-mcp",
            "method": "getLightInformation",
            "params": {},
        },
    )
    return result["data"]["items"]


async def activate_light(client: VapixClient, light_id: str) -> str:
    """
    Turn on (activate) a light by its ID.

    The light must be enabled first. If it's an IR light, the IR cut filter
    must not be in "On" mode.

    Args:
        light_id: Light identifier (e.g. "led0"). Get from getLightInformation.

    Returns:
        "OK" on success.

    Raises:
        VapixError: If light ID is invalid or light is disabled.
    """
    await client.post_json(
        "/axis-cgi/lightcontrol.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vapx-mcp",
            "method": "activateLight",
            "params": {"lightID": light_id},
        },
    )
    return "OK"


async def deactivate_light(client: VapixClient, light_id: str) -> str:
    """
    Turn off (deactivate) a light by its ID.

    Args:
        light_id: Light identifier (e.g. "led0").

    Returns:
        "OK" on success.
    """
    await client.post_json(
        "/axis-cgi/lightcontrol.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vapx-mcp",
            "method": "deactivateLight",
            "params": {"lightID": light_id},
        },
    )
    return "OK"


async def enable_light(client: VapixClient, light_id: str) -> str:
    """
    Enable a light, allowing it to be activated.

    A disabled light cannot be turned on by any method.

    Args:
        light_id: Light identifier (e.g. "led0").

    Returns:
        "OK" on success.
    """
    await client.post_json(
        "/axis-cgi/lightcontrol.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vapx-mcp",
            "method": "enableLight",
            "params": {"lightID": light_id},
        },
    )
    return "OK"


async def get_light_status(client: VapixClient, light_id: str) -> bool:
    """
    Check if a specific light is currently on or off.

    Args:
        light_id: Light identifier (e.g. "led0").

    Returns:
        True if the light is on, False if off.
    """
    result = await client.post_json(
        "/axis-cgi/lightcontrol.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vapx-mcp",
            "method": "getLightStatus",
            "params": {"lightID": light_id},
        },
    )
    return result["data"]["status"]


async def set_manual_intensity(
    client: VapixClient, light_id: str, intensity: int
) -> str:
    """
    Set the manual intensity level for a light.

    Use getValidIntensity first to determine the supported range.

    Args:
        light_id: Light identifier.
        intensity: Intensity level (range depends on device, typically 0-100).

    Returns:
        "OK" on success.
    """
    await client.post_json(
        "/axis-cgi/lightcontrol.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vapx-mcp",
            "method": "setManualIntensity",
            "params": {"lightID": light_id, "intensity": intensity},
        },
    )
    return "OK"
