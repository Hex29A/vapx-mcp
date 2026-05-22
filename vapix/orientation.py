"""
VAPIX Orientation — Read physical orientation sensor data.

Endpoints:
    GET /axis-cgi/orientation/getlongitudinalvalue.cgi  — rotation around lens axis
    GET /axis-cgi/orientation/getlateralvalue.cgi       — tilt angle (up/down)

Docs: https://developer.axis.com/vapix/network-video/orientation/

This reads the camera's built-in orientation sensor (accelerometer/gyroscope).
Not all cameras have this hardware. Values indicate physical mounting angle.

Note: This is NOT video rotation/mirror/corridor format — those are controlled
via param.cgi parameters, not this API.
"""

import xml.etree.ElementTree as ET
from typing import Any

from .client import VapixClient


async def get_orientation(client: VapixClient) -> dict[str, Any]:
    """
    Get the camera's physical orientation from its built-in sensor.

    Returns dict with:
        longitudinal — Rotation around lens axis (0-359 degrees)
        lateral      — Tilt angle (0=pointing down, 90=horizontal, 180=pointing up)
        available    — Whether orientation sensor is available
    """
    result: dict[str, Any] = {"available": True}

    try:
        resp = await client.get(
            "/axis-cgi/orientation/getlongitudinalvalue.cgi",
            {"schemaversion": 1},
        )
        root = ET.fromstring(resp.text)
        for elem in root.iter():
            tag = elem.tag.rpartition("}")[2] if "}" in elem.tag else elem.tag
            if tag == "Value" and elem.text:
                result["longitudinal"] = float(elem.text)
                break
    except Exception:
        result["available"] = False
        result["longitudinal"] = None

    try:
        resp = await client.get(
            "/axis-cgi/orientation/getlateralvalue.cgi",
            {"schemaversion": 1},
        )
        root = ET.fromstring(resp.text)
        for elem in root.iter():
            tag = elem.tag.rpartition("}")[2] if "}" in elem.tag else elem.tag
            if tag == "Value" and elem.text:
                result["lateral"] = float(elem.text)
                break
    except Exception:
        if not result.get("available", True):
            result["lateral"] = None

    return result
