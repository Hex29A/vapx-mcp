"""
VAPIX PTZ (Pan/Tilt/Zoom) Control API.

Controls mechanical PTZ movements using the classic CGI endpoint
/axis-cgi/com/ptz.cgi (GET-based, not JSON POST).

Reference: https://developer.axis.com/vapix/network-video/
    (Under "Pan/tilt/zoom API")

Coordinate system:
    - pan:  -180.0 to 180.0 degrees (negative=left, positive=right)
    - tilt: -180.0 to 180.0 degrees (negative=down, positive=up)
    - zoom: 1 to 9999 (1=wide, 9999=telephoto)

Note: Exact ranges vary by camera model. The camera will clamp
values to its supported range.

PTZ presets are managed via /axis-cgi/com/ptz.cgi with query parameters.
Preset list uses a separate endpoint in newer firmware.
"""

from typing import Any

from vapix.client import VapixClient


async def move_absolute(
    client: VapixClient,
    pan: float,
    tilt: float,
    zoom: int,
    speed: int | None = None,
) -> str:
    """
    Move camera to an absolute pan/tilt/zoom position.

    Args:
        pan: Horizontal angle (-180.0 to 180.0).
        tilt: Vertical angle (-180.0 to 180.0).
        zoom: Zoom level (1=wide to 9999=telephoto).
        speed: Movement speed 1-100 (optional, camera default if omitted).

    Returns:
        "OK" on success.
    """
    params: dict[str, Any] = {"pan": pan, "tilt": tilt, "zoom": zoom}
    if speed is not None:
        params["speed"] = speed
    await client.get("/axis-cgi/com/ptz.cgi", params)
    return "OK"


async def move_relative(
    client: VapixClient,
    rpan: float = 0,
    rtilt: float = 0,
    rzoom: int = 0,
    speed: int | None = None,
) -> str:
    """
    Move camera by a relative offset from current position.

    Args:
        rpan: Relative pan offset.
        rtilt: Relative tilt offset.
        rzoom: Relative zoom offset.
        speed: Movement speed 1-100 (optional).

    Returns:
        "OK" on success.
    """
    params: dict[str, Any] = {"rpan": rpan, "rtilt": rtilt, "rzoom": rzoom}
    if speed is not None:
        params["speed"] = speed
    await client.get("/axis-cgi/com/ptz.cgi", params)
    return "OK"


async def go_home(client: VapixClient) -> str:
    """
    Move camera to its home position.

    Returns:
        "OK" on success.
    """
    await client.get("/axis-cgi/com/ptz.cgi", {"move": "home"})
    return "OK"


async def go_to_preset(client: VapixClient, preset_name: str) -> str:
    """
    Move camera to a named server preset position.

    Args:
        preset_name: Name of the preset (case-sensitive).

    Returns:
        "OK" on success.
    """
    await client.get(
        "/axis-cgi/com/ptz.cgi", {"gotoserverpresetname": preset_name}
    )
    return "OK"


async def get_position(client: VapixClient) -> dict[str, float]:
    """
    Query the current PTZ position.

    Returns:
        Dict with 'pan', 'tilt', 'zoom' values.
    """
    response = await client.get("/axis-cgi/com/ptz.cgi", {"query": "position"})
    text = response.text.strip()

    # Response format: "pan=0.0000\r\ntilt=0.0000\r\nzoom=1\r\n..."
    position = {}
    for line in text.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip().lower()
            if key in ("pan", "tilt", "zoom"):
                position[key] = float(val.strip())

    return position


async def list_presets(client: VapixClient) -> list[str]:
    """
    List all server preset names configured on the camera.

    Returns:
        List of preset name strings.
    """
    response = await client.get(
        "/axis-cgi/com/ptz.cgi", {"query": "presetposall"}
    )
    text = response.text.strip()

    # Response format varies; common pattern is lines with preset info
    # Try to parse preset names from the response
    presets = []
    for line in text.splitlines():
        line = line.strip()
        if line and "=" in line:
            # Format: "presetposno1=PresetName" or similar
            _key, val = line.split("=", 1)
            val = val.strip()
            if val:
                presets.append(val)

    return presets
