"""
VAPIX Basic Device Information API.

Retrieves device properties like model name, serial number, firmware version,
hardware ID, etc. via /axis-cgi/basicdeviceinfo.cgi.

Reference: https://developer.axis.com/vapix/network-video/basic-device-information/

Methods:
    - getAllProperties: Returns all device properties (requires Operator access).
    - getProperties: Returns a subset of device properties.

Response includes: Architecture, Brand, BuildDate, HardwareID, ProdFullName,
ProdNbr, ProdShortName, ProdType, SerialNumber, Soc, Version, WebURL, etc.
"""

from typing import Any

from vapix.client import VapixClient

# API version 1.0 is the baseline supported by AXIS OS 8.40+
API_VERSION = "1.0"


async def get_all_properties(client: VapixClient) -> dict[str, Any]:
    """
    Retrieve all device properties from the Basic Device Information service.

    Returns a dict of property name → value, e.g.:
        {
            "Architecture": "armv7hf",
            "Brand": "AXIS",
            "ProdFullName": "AXIS M2036-LE Network Camera",
            "SerialNumber": "ACCC8E123456",
            "Version": "11.6.54",
            ...
        }
    """
    result = await client.post_json(
        "/axis-cgi/basicdeviceinfo.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vpx-mcp",
            "method": "getAllProperties",
        },
    )
    return result["data"]["propertyList"]


async def get_properties(
    client: VapixClient, properties: list[str]
) -> dict[str, Any]:
    """
    Retrieve a specific subset of device properties.

    Args:
        properties: List of property names, e.g. ["Brand", "ProdNbr", "Version"]

    Returns:
        Dict of requested property name → value.
    """
    result = await client.post_json(
        "/axis-cgi/basicdeviceinfo.cgi",
        {
            "apiVersion": API_VERSION,
            "context": "vpx-mcp",
            "method": "getProperties",
            "params": {"propertyList": properties},
        },
    )
    return result["data"]["propertyList"]
