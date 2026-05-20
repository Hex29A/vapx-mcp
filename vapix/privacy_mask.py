"""
VAPIX Privacy Mask — Manage privacy masks that cover sensitive areas.

Endpoint: GET /axis-cgi/privacymask.cgi
Docs: https://developer.axis.com/vapix/network-video/overlay-api/#privacy-mask-api

Privacy masks cover areas in the video that should not be visible (faces,
windows, license plates). Masks automatically adapt their position and size
when the camera's pan/tilt/zoom position changes.

Key concepts:
    - Masks are identified by a unique name (string, max 128 chars).
    - Position can be set as center + width/height (percent) or pixel polygon.
    - Coordinates in percent are relative to image size.
    - Pixel polygon coordinates are in the camera's max resolution.
    - Masks can be enabled/disabled individually or all at once.
    - The camera has a maximum number of masks (Properties.PrivacyMask.MaxNbrOfPrivacyMasks).

Supported actions via privacymask.cgi:
    query=listpxjson        — List all masks with pixel coordinates (JSON)
    action=add              — Add a new mask
    action=update           — Update an existing mask's position/size
    action=remove           — Remove a mask by name
    action=enable_all       — Enable all masks
    action=disable_all      — Disable all masks

Note: Color and per-mask enable/disable use param.cgi — not exposed here
to keep the API surface focused on the most useful operations.
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/privacymask.cgi"


async def list_masks(client: VapixClient) -> list[dict[str, Any]]:
    """
    List all privacy masks with their pixel coordinates.

    Returns a list of masks, each with:
        id              — Numeric mask ID
        name            — Mask name
        enabled         — Whether the mask is currently visible
        zoomlowlimit    — Minimum zoom level for mask to be rendered
        zoom_visible    — Whether mask is visible at current zoom (optional)
        position        — List of {x, y} corner coordinates in max resolution
    """
    response = await client.get(_PATH, {"query": "listpxjson"})
    data = response.json()
    return data.get("listpx", [])


async def add_mask(
    client: VapixClient,
    name: str,
    *,
    width: float | None = None,
    height: float | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    polygon: str | None = None,
    image_source: int = 0,
) -> None:
    """
    Add a new privacy mask.

    Position can be set two ways:
    1. Width/height in percent (optionally with center coordinates):
       add_mask(client, "mask1", width=20.0, height=20.0, center_x=50.0, center_y=50.0)

    2. Pixel polygon (corners in max resolution, colon-separated):
       add_mask(client, "mask1", polygon="500,500:800,500:700,700:400,700")

    Args:
        name: Unique mask name (max 128 chars).
        width: Mask width as percent of image width (0.0–100.0).
        height: Mask height as percent of image height (0.0–100.0).
        center_x: Center X position as percent of image width (0.0–100.0).
        center_y: Center Y position as percent of image height (0.0–100.0).
        polygon: Pixel coordinates as "x1,y1:x2,y2:x3,y3[:...]" in max resolution.
        image_source: Video channel (default 0).

    Raises:
        ValueError: If neither width/height nor polygon is provided.
    """
    params: dict[str, Any] = {
        "action": "add",
        "name": name,
        "imagesource": image_source,
    }

    if polygon:
        params["pxpolygon"] = polygon
    elif width is not None and height is not None:
        params["width"] = width
        params["height"] = height
        if center_x is not None and center_y is not None:
            params["center"] = f"{center_x},{center_y}"
    else:
        raise ValueError("Must provide either width+height or polygon")

    response = await client.get(_PATH, params)

    # Successful add returns 204 No Content.
    # Error returns 200 with "Error: <message>" in body.
    if response.status_code == 200:
        text = response.text.strip()
        if text.startswith("Error"):
            raise Exception(f"Privacy mask error: {text}")


async def update_mask(
    client: VapixClient,
    name: str,
    *,
    width: float | None = None,
    height: float | None = None,
    center_x: float | None = None,
    center_y: float | None = None,
    polygon: str | None = None,
) -> None:
    """
    Update an existing privacy mask's position and/or size.

    Args:
        name: Name of the existing mask to update.
        width: New width as percent of image width.
        height: New height as percent of image height.
        center_x: New center X position as percent.
        center_y: New center Y position as percent.
        polygon: New pixel polygon coordinates.
    """
    params: dict[str, Any] = {"action": "update", "name": name}

    if polygon:
        params["pxpolygon"] = polygon
    elif width is not None and height is not None:
        params["width"] = width
        params["height"] = height
        if center_x is not None and center_y is not None:
            params["center"] = f"{center_x},{center_y}"

    response = await client.get(_PATH, params)

    if response.status_code == 200:
        text = response.text.strip()
        if text.startswith("Error"):
            raise Exception(f"Privacy mask error: {text}")


async def remove_mask(client: VapixClient, name: str) -> None:
    """
    Remove a privacy mask by name.

    Args:
        name: Name of the mask to remove.
    """
    response = await client.get(_PATH, {"action": "remove", "name": name})

    if response.status_code == 200:
        text = response.text.strip()
        if text.startswith("Error"):
            raise Exception(f"Privacy mask error: {text}")


async def enable_all(client: VapixClient) -> None:
    """Enable all privacy masks (make them visible)."""
    response = await client.get(_PATH, {"action": "enable_all"})

    if response.status_code == 200:
        text = response.text.strip()
        if text.startswith("Error"):
            raise Exception(f"Privacy mask error: {text}")


async def disable_all(client: VapixClient) -> None:
    """
    Disable all privacy masks (hide them).

    Useful in emergencies when you need full visibility.
    All masks remain configured but become invisible.
    """
    response = await client.get(_PATH, {"action": "disable_all"})

    if response.status_code == 200:
        text = response.text.strip()
        if text.startswith("Error"):
            raise Exception(f"Privacy mask error: {text}")
