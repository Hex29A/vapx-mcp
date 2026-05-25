"""
VAPIX MQTT Client & Event Bridge — Configure MQTT event publishing.

Endpoints:
    POST /axis-cgi/mqtt/client.cgi  — MQTT client connection settings
    POST /axis-cgi/mqtt/event.cgi   — Event publication config

API Discovery IDs: mqtt-client, event-mqtt-bridge

Once configured, the camera publishes events directly to the MQTT broker.
MCP is only used for the one-time setup — no runtime overhead.
"""

from typing import Any

from .client import VapixClient

_CLIENT_PATH = "/axis-cgi/mqtt/client.cgi"
_EVENT_PATH = "/axis-cgi/mqtt/event.cgi"


async def get_client_status(client: VapixClient) -> dict[str, Any]:
    """
    Get MQTT client connection status and configuration.

    Returns dict with:
        status — {state, connectionStatus}
        config — {server: {protocol, host, port}, clientId, keepAliveInterval, ...}
    """
    payload = {"apiVersion": "1.0", "method": "getClientStatus"}
    data = await client.post_json(_CLIENT_PATH, payload)
    return data["data"]


async def configure_client(
    client: VapixClient,
    *,
    host: str,
    port: int = 1883,
    protocol: str = "tcp",
    client_id: str | None = None,
    username: str | None = None,
    password: str | None = None,
    keep_alive: int = 60,
    clean_session: bool = True,
    auto_reconnect: bool = True,
) -> dict[str, Any]:
    """
    Configure the MQTT client connection.

    Args:
        host: MQTT broker hostname or IP.
        port: Broker port (default 1883).
        protocol: "tcp", "ssl", "ws", or "wss".
        client_id: Optional client ID (camera generates one if omitted).
        username: Optional broker username.
        password: Optional broker password.
        keep_alive: Keep-alive interval in seconds.
        clean_session: Start with clean session.
        auto_reconnect: Auto-reconnect on disconnect.
    """
    server = {"protocol": protocol, "host": host, "port": port}
    params: dict[str, Any] = {
        "server": server,
        "keepAliveInterval": keep_alive,
        "cleanSession": clean_session,
        "autoReconnect": auto_reconnect,
    }
    if client_id:
        params["clientId"] = client_id
    if username:
        params["username"] = username
    if password:
        params["password"] = password

    payload = {"apiVersion": "1.0", "method": "configureClient", "params": params}
    data = await client.post_json(_CLIENT_PATH, payload)
    return data.get("data", {})


async def activate_client(client: VapixClient) -> None:
    """Enable the MQTT client (connect to broker)."""
    payload = {"apiVersion": "1.0", "method": "activateClient"}
    await client.post_json(_CLIENT_PATH, payload)


async def deactivate_client(client: VapixClient) -> None:
    """Disable the MQTT client (disconnect from broker)."""
    payload = {"apiVersion": "1.0", "method": "deactivateClient"}
    await client.post_json(_CLIENT_PATH, payload)


async def get_event_publication_config(client: VapixClient) -> dict[str, Any]:
    """
    Get event publication configuration (topic prefix, filters).

    Returns dict with:
        topicPrefix, customTopicPrefix, appendEventTopic,
        includeTopicNamespaces, eventFilterList
    """
    payload = {"apiVersion": "1.0", "method": "getEventPublicationConfig"}
    data = await client.post_json(_EVENT_PATH, payload)
    return data["data"]["eventPublicationConfig"]


async def configure_event_publication(
    client: VapixClient,
    *,
    event_filter_list: list[dict[str, Any]] | None = None,
    topic_prefix: str = "default",
    custom_topic_prefix: str = "",
    append_event_topic: bool = True,
) -> None:
    """
    Configure which events are published to the MQTT broker.

    Args:
        event_filter_list: List of event topic filters to publish.
        topic_prefix: "default" or "custom".
        custom_topic_prefix: Custom prefix when topic_prefix is "custom".
        append_event_topic: Append the event topic to the prefix.
    """
    params: dict[str, Any] = {
        "eventPublicationConfig": {
            "topicPrefix": topic_prefix,
            "customTopicPrefix": custom_topic_prefix,
            "appendEventTopic": append_event_topic,
            "eventFilterList": event_filter_list or [],
        }
    }
    payload = {"apiVersion": "1.0", "method": "configureEventPublication", "params": params}
    await client.post_json(_EVENT_PATH, payload)
