"""
VAPIX Event Polling — Collect events via WebSocket with a time-limited poll.

WebSocket: ws://<device>/vapix/ws-data-stream?sources=events
Session token: GET /axis-cgi/wssession.cgi

This module provides a practical polling approach for MCP:
  1. Get a session token (valid 15s)
  2. Open WebSocket connection
  3. Configure event filter
  4. Collect events for a few seconds
  5. Close and return batch

Requires the `websockets` package.

Docs: https://developer.axis.com/vapix/network-video/event-streaming-over-websocket/
"""

import asyncio
import json
from typing import Any

from .client import VapixClient

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment]


async def get_session_token(client: VapixClient) -> str:
    """
    Get a WebSocket session token (valid for ~15 seconds).
    """
    response = await client.get("/axis-cgi/wssession.cgi")
    return response.text.strip()


async def poll_events(
    client: VapixClient,
    *,
    duration_seconds: float = 5.0,
    topic_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Open a WebSocket, collect events for a duration, then close.

    Args:
        duration_seconds: How long to listen for events (default 5s, max 30s).
        topic_filter: Optional ONVIF topic filter string.
            Examples:
                "tns1:Device/tnsaxis:IO/VirtualPort"
                "tns1:RuleEngine/MotionRegionDetector/Motion"

    Returns list of event notifications, each containing:
        timestamp — ISO 8601 event time
        topic     — ONVIF topic string
        message   — Dict with source, key, data key-value pairs
    """
    if websockets is None:
        raise RuntimeError(
            "websockets package is required for event polling. "
            "Install it with: pip install websockets"
        )

    duration_seconds = min(max(duration_seconds, 1.0), 30.0)

    # Get session token
    token = await get_session_token(client)

    # Build WebSocket URL
    base_url = client.camera.base_url
    scheme = "wss" if base_url.startswith("https") else "ws"
    # Extract host:port from base URL
    host_part = base_url.split("://", 1)[1].rstrip("/")
    ws_url = f"{scheme}://{host_part}/vapix/ws-data-stream?sources=events&wssession={token}"

    events: list[dict[str, Any]] = []

    async with websockets.connect(ws_url) as ws:
        # Configure event filter
        filter_config: dict[str, Any] = {
            "apiVersion": "1.0",
            "method": "events:configure",
            "params": {"eventFilterList": []},
        }
        if topic_filter:
            filter_config["params"]["eventFilterList"] = [
                {"topicFilter": topic_filter}
            ]

        await ws.send(json.dumps(filter_config))

        # Collect events for the specified duration
        try:
            async with asyncio.timeout(duration_seconds):
                async for message in ws:
                    try:
                        msg = json.loads(message)
                        if msg.get("method") == "events:notify":
                            notification = msg.get("params", {}).get("notification", {})
                            events.append(notification)
                    except json.JSONDecodeError:
                        continue
        except (TimeoutError, asyncio.TimeoutError):
            pass

    return events
