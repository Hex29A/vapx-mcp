"""
VAPIX Geolocation — Get and set camera GPS coordinates and heading.

Endpoints:
    GET /axis-cgi/geolocation/get.cgi  — read position
    GET /axis-cgi/geolocation/set.cgi  — update position

Docs: https://developer.axis.com/vapix/network-video/

Note: This is a legacy XML API (not JSON POST). Coordinates are WGS-84.
Most Axis cameras don't have GPS hardware — coordinates are manually set.
"""

import xml.etree.ElementTree as ET
from typing import Any

from .client import VapixClient


async def get_location(client: VapixClient) -> dict[str, Any]:
    """
    Get the camera's configured geolocation.

    Returns dict with:
        lat             — Latitude (float or empty)
        lng             — Longitude (float or empty)
        heading         — Compass heading in degrees (float or empty)
        text            — Location description text
        validPosition   — Whether lat/lng are set
        validHeading    — Whether heading is set
    """
    response = await client.get("/axis-cgi/geolocation/get.cgi")
    text = response.text

    root = ET.fromstring(text)
    result: dict[str, Any] = {}
    for child in root:
        # Strip namespace if present
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        value = child.text or ""
        # Convert booleans and numbers
        if value.lower() in ("true", "false"):
            result[tag] = value.lower() == "true"
        else:
            try:
                result[tag] = float(value)
            except ValueError:
                result[tag] = value
    return result


async def set_location(
    client: VapixClient,
    *,
    lat: float | None = None,
    lng: float | None = None,
    heading: float | None = None,
    text: str | None = None,
) -> None:
    """
    Set the camera's geolocation.

    Args:
        lat: Latitude in decimal degrees (WGS-84).
        lng: Longitude in decimal degrees (WGS-84).
        heading: Compass heading in degrees (0-360).
        text: Location description text.
    """
    params: dict[str, Any] = {}
    if lat is not None:
        params["lat"] = lat
    if lng is not None:
        params["lng"] = lng
    if heading is not None:
        params["heading"] = heading
    if text is not None:
        params["text"] = text

    response = await client.get("/axis-cgi/geolocation/set.cgi", params)

    # Check for error in response
    if response.status_code != 200 and response.status_code != 204:
        raise Exception(f"Geolocation set error: HTTP {response.status_code}")
    resp_text = response.text.strip()
    if resp_text and "error" in resp_text.lower():
        raise Exception(f"Geolocation error: {resp_text}")
