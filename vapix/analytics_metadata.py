"""
VAPIX Analytics Metadata Config — Manage analytics metadata producers.

Endpoint: POST /axis-cgi/analyticsmetadataconfig.cgi
Docs: https://developer.axis.com/vapix/network-video/analytics-metadata-config/

Controls which analytics producers (object detection, motion, etc.) are
enabled per video channel. Producers generate ONVIF-compatible metadata
in the video stream.

Methods:
    listProducers        — List analytics producers and their enabled state
    setEnabledProducers  — Enable/disable specific producers per channel
    getSupportedMetadata — Get sample ONVIF XML metadata for producers
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/analyticsmetadataconfig.cgi"


async def list_producers(client: VapixClient) -> list[dict[str, Any]]:
    """
    List all analytics metadata producers and their status.

    Returns list of producer dicts with:
        name          — Producer identifier
        niceName      — Human-readable display name (optional)
        videochannels — List of {channel, enabled} per video channel
    """
    payload = {
        "apiVersion": "1.0",
        "method": "listProducers",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"].get("producers", [])


async def set_enabled_producers(
    client: VapixClient,
    producers: list[dict[str, Any]],
) -> None:
    """
    Enable or disable analytics metadata producers per channel.

    Args:
        producers: List of producer configs, each with:
            name (str) — Producer identifier
            videochannels (list) — [{channel: int, enabled: bool}]
    """
    payload = {
        "apiVersion": "1.0",
        "method": "setEnabledProducers",
        "params": {"producers": producers},
    }
    await client.post_json(_PATH, payload)


async def get_supported_metadata(
    client: VapixClient,
    producer_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Get sample ONVIF XML metadata frames for analytics producers.

    Args:
        producer_names: List of producer names to query (None = all).

    Returns list of producer dicts with:
        name           — Producer identifier
        sampleFrameXML — ONVIF XML metadata sample
    """
    params: dict[str, Any] = {}
    if producer_names:
        params["producers"] = producer_names

    payload = {
        "apiVersion": "1.0",
        "method": "getSupportedMetadata",
        "params": params,
    }
    data = await client.post_json(_PATH, payload)
    return data["data"].get("producers", [])
