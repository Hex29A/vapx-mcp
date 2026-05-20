"""
VAPIX Clear View — Activate wiper and speed-dry to keep the lens clean.

Endpoint: POST /axis-cgi/clearviewcontrol.cgi
Docs: https://developer.axis.com/vapix/network-video/clear-view/

The Clear View API controls wiper and speed-dry functions on cameras
that have this hardware (e.g. outdoor dome cameras with built-in wipers).

Supported methods:
    getServiceInfo  — List available cleaning services (wiper, speeddry)
    getStatus       — Check if a service is idle, running, or cooling down
    start           — Activate wiper or speed-dry (with optional duration)
    stop            — Stop a running cleaning operation (if stoppable)

Each service is identified by a numeric ID (typically 0=wiper, 1=speeddry).
The getServiceInfo response provides IDs, duration limits, and cooldown times.
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/clearviewcontrol.cgi"


async def get_service_info(client: VapixClient) -> list[dict[str, Any]]:
    """
    Get information about available Clear View services.

    Returns a list of services, each with:
        id              — Numeric service ID (0=wiper, 1=speeddry, etc.)
        type            — "wiper" or "speeddry"
        durationVariable — Whether custom duration is supported
        durationMin     — Minimum duration in seconds (if variable)
        durationMax     — Maximum duration in seconds (if variable)
        durationDefault — Default duration in seconds
        idleTimeMin     — Minimum cooldown between activations (seconds)
        stoppable       — Whether the service can be stopped mid-operation
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getServiceInfo",
        "params": {},
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]["serviceInfo"]


async def get_status(client: VapixClient, service_id: int = 0) -> dict[str, Any]:
    """
    Get current status of a Clear View service.

    Args:
        service_id: Service ID from getServiceInfo (default 0 = wiper).

    Returns dict with:
        state       — "idle", "running", or "coolingDown"
        stopsIn     — Seconds until service stops (if running)
        availableIn — Seconds until service available (if cooling down)
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getStatus",
        "params": {"id": service_id},
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def start(
    client: VapixClient,
    service_id: int = 0,
    duration: int | None = None,
) -> None:
    """
    Start a Clear View cleaning operation (wiper or speed-dry).

    Args:
        service_id: Service ID from getServiceInfo (default 0 = wiper).
        duration: Duration in seconds. Must be within durationMin–durationMax
                  from getServiceInfo. Omit for default duration.
    """
    params: dict[str, Any] = {"id": service_id}
    if duration is not None:
        params["duration"] = duration

    payload = {
        "apiVersion": "1.0",
        "method": "start",
        "params": params,
    }
    await client.post_json(_PATH, payload)


async def stop(client: VapixClient, service_id: int = 0) -> None:
    """
    Stop a running Clear View operation.

    Only works if the service's 'stoppable' flag is True.

    Args:
        service_id: Service ID to stop (default 0 = wiper).
    """
    payload = {
        "apiVersion": "1.0",
        "method": "stop",
        "params": {"id": service_id},
    }
    await client.post_json(_PATH, payload)
