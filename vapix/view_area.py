"""
VAPIX View Area API — List and configure virtual view areas.

Endpoints:
  POST /axis-cgi/viewarea/info.cgi      — list view areas (read-only)
  POST /axis-cgi/viewarea/configure.cgi — set/reset geometry (write)

A view area defines a crop of the camera's full sensor as a virtual channel.
Wide-angle or high-res cameras can expose multiple view areas, each streaming
a different region of interest at lower resolution.

Geometry is defined in pixel coordinates on the canvas (= full sensor size).
Coordinates must be aligned to the grid (typically 8x8 pixels).

Ref: https://developer.axis.com/vapix/network-video/view-area-api/
"""

from typing import Any

from .client import VapixClient

_INFO_PATH = "/axis-cgi/viewarea/info.cgi"
_CONFIGURE_PATH = "/axis-cgi/viewarea/configure.cgi"


async def list_view_areas(client: VapixClient) -> list[dict[str, Any]]:
    """
    List all view areas with their geometry and constraints.

    Returns a list of view areas. Each entry includes:
      - id: view area identifier
      - camera: virtual channel number
      - configurable: whether geometry can be changed
      - canvas_size: full sensor size (horizontal x vertical pixels)
      - geometry: current crop (offset + size in pixels)
      - min_size / max_size: allowed size range
      - grid: alignment requirements (geometry must be aligned to this grid)
    """
    result = await client.post_json(
        _INFO_PATH,
        {"apiVersion": "1.0", "context": "vapx-mcp", "method": "list"},
    )
    raw_areas = result["data"]["viewAreas"]
    areas = []
    for a in raw_areas:
        entry: dict[str, Any] = {
            "id": a["id"],
            "camera": a.get("camera"),
            "source": a.get("source"),
            "configurable": a.get("configurable", False),
        }
        if "canvasSize" in a:
            entry["canvas_size"] = a["canvasSize"]
        if "rectangularGeometry" in a:
            g = a["rectangularGeometry"]
            entry["geometry"] = {
                "horizontal_offset": g.get("horizontalOffset"),
                "vertical_offset": g.get("verticalOffset"),
                "horizontal_size": g.get("horizontalSize"),
                "vertical_size": g.get("verticalSize"),
            }
        if "minSize" in a:
            entry["min_size"] = a["minSize"]
        if "maxSize" in a:
            entry["max_size"] = a["maxSize"]
        if "grid" in a:
            entry["grid"] = a["grid"]
        areas.append(entry)
    return areas


async def set_view_area_geometry(
    client: VapixClient,
    view_area_id: int,
    horizontal_offset: int,
    vertical_offset: int,
    horizontal_size: int,
    vertical_size: int,
) -> dict[str, Any]:
    """
    Set the crop geometry for a view area.

    Args:
        view_area_id: ID from list_view_areas
        horizontal_offset: Left edge in pixels (must align to grid)
        vertical_offset: Top edge in pixels (must align to grid)
        horizontal_size: Width in pixels (must align to grid, >= min_size)
        vertical_size: Height in pixels (must align to grid, >= min_size)

    Returns:
        The updated geometry as confirmed by the camera.
    """
    result = await client.post_json(
        _CONFIGURE_PATH,
        {
            "apiVersion": "1.0",
            "context": "vapx-mcp",
            "method": "setGeometry",
            "params": {
                "viewAreaId": view_area_id,
                "rectangularGeometry": {
                    "horizontalOffset": horizontal_offset,
                    "verticalOffset": vertical_offset,
                    "horizontalSize": horizontal_size,
                    "verticalSize": vertical_size,
                },
            },
        },
    )
    return result.get("data", result)


async def reset_view_area_geometry(
    client: VapixClient, view_area_id: int
) -> dict[str, Any]:
    """Reset a view area's geometry to its factory default (full canvas)."""
    result = await client.post_json(
        _CONFIGURE_PATH,
        {
            "apiVersion": "1.0",
            "context": "vapx-mcp",
            "method": "resetGeometry",
            "params": {"viewAreaId": view_area_id},
        },
    )
    return result.get("data", result)
