"""
VAPIX Dynamic Overlay — Add/remove text and image overlays on live video.

Endpoint: POST /axis-cgi/dynamicoverlay/dynamicoverlay.cgi
Docs: https://developer.axis.com/vapix/network-video/overlay-api/

Overlays can annotate the live video stream with text (timestamps,
alert messages, labels) or images (logos, icons).

Note: Overlay identity values may change after device reboot.
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/dynamicoverlay/dynamicoverlay.cgi"


async def list_overlays(client: VapixClient) -> dict[str, Any]:
    """
    List all current overlays and available image files.

    Returns dict with keys:
        textOverlays: list of text overlay objects
        imageOverlays: list of image overlay objects
        imageFiles: list of available overlay image paths
    """
    payload = {
        "apiVersion": "1.0",
        "method": "list",
        "params": {},
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def add_text(
    client: VapixClient,
    text: str,
    *,
    camera: int = 1,
    position: str = "topLeft",
    text_color: str = "white",
    text_bg_color: str = "transparent",
    font_size: int | None = None,
) -> int:
    """
    Add a text overlay to the video stream.

    Args:
        text: Overlay text (max 512 chars). Supports format strings:
              %c = date+time, %H = hour, %M = minute, etc.
        camera: Camera/view number (default 1).
        position: One of: topLeft, topRight, bottomLeft, bottomRight,
                  or custom coordinates.
        text_color: Text color name (white, black, red, etc.)
        text_bg_color: Background color (transparent, black, white, etc.)
        font_size: Font size in pixels (device-dependent range).

    Returns:
        The overlay identity (integer) for later modification/removal.
    """
    params: dict[str, Any] = {
        "camera": camera,
        "text": text,
        "position": position,
        "textColor": text_color,
        "textBGColor": text_bg_color,
    }
    if font_size is not None:
        params["fontSize"] = font_size

    payload = {
        "apiVersion": "1.0",
        "method": "addText",
        "params": params,
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]["identity"]


async def set_text(
    client: VapixClient,
    identity: int,
    **kwargs: Any,
) -> None:
    """
    Update properties of an existing text overlay.

    Args:
        identity: Overlay identity from add_text().
        **kwargs: Properties to update (text, textColor, textBGColor,
                  fontSize, position, etc.)
    """
    params = {"identity": identity, **kwargs}
    payload = {
        "apiVersion": "1.0",
        "method": "setText",
        "params": params,
    }
    await client.post_json(_PATH, payload)


async def remove_overlay(client: VapixClient, identity: int) -> None:
    """
    Remove an overlay by its identity.

    Args:
        identity: Overlay identity from add_text() or add_image().
    """
    payload = {
        "apiVersion": "1.0",
        "method": "remove",
        "params": {"identity": identity},
    }
    await client.post_json(_PATH, payload)


async def get_overlay_capabilities(client: VapixClient) -> dict[str, Any]:
    """Get overlay capabilities (max overlays, supported colors, etc.)."""
    payload = {
        "apiVersion": "1.0",
        "method": "getOverlayCapabilities",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]
