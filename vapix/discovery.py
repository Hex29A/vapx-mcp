"""
VAPIX API Discovery — List all APIs supported by an Axis device.

Endpoint: POST /axis-cgi/apidiscovery.cgi
Docs: https://developer.axis.com/vapix/network-video/api-discovery-service/

Available on all Axis devices with AXIS OS 9.80+.
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/apidiscovery.cgi"


async def get_api_list(client: VapixClient) -> list[dict[str, Any]]:
    """
    Get the list of all VAPIX APIs supported by the device.

    Returns a list of dicts, each with:
        id, version, name, status, docLink (optional)
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getApiList",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]["apiList"]


async def check_api_support(
    client: VapixClient, api_id: str
) -> dict[str, Any] | None:
    """
    Check if a specific API is supported by the device.

    Args:
        api_id: API identifier, e.g. "light-control", "io-port-management"

    Returns:
        API info dict if supported, None otherwise.
    """
    apis = await get_api_list(client)
    for api in apis:
        if api.get("id") == api_id:
            return api
    return None
