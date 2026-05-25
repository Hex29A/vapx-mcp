"""
Tests for stream_status and mqtt VAPIX modules.

Uses respx to mock HTTP responses — no real cameras needed.
"""

import json

import httpx
import pytest
import respx

from config import CameraConfig
from vapix import mqtt, stream_status
from vapix.client import VapixClient, VapixError


def _make_camera(**overrides):
    defaults = dict(
        id="test-cam",
        name="Test Camera",
        host="192.168.1.100",
        port=443,
        https=True,
        verify_ssl=False,
        username="root",
        password="testpass",
        capabilities=["snapshot", "stream_status", "mqtt"],
    )
    defaults.update(overrides)
    return CameraConfig(**defaults)


BASE_URL = "https://192.168.1.100:443"


# ---------------------------------------------------------------------------
# Stream Status
# ---------------------------------------------------------------------------

class TestStreamStatus:
    @pytest.mark.asyncio
    async def test_active_streams(self):
        """Should parse active stream data."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getStreamStatus",
            "data": {
                "streams": [
                    {
                        "clients": 2,
                        "bitrate": 4500,
                        "fps": 30,
                        "resolution": "1920x1080",
                        "codec": "h264",
                    },
                    {
                        "clients": 1,
                        "bitrate": 1200,
                        "fps": 15,
                        "resolution": "640x480",
                        "codec": "mjpeg",
                    },
                ]
            },
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/streamstatus.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                result = await stream_status.get_stream_status(client)

        assert len(result) == 2
        assert result[0]["clients"] == 2
        assert result[0]["codec"] == "h264"
        assert result[1]["resolution"] == "640x480"

    @pytest.mark.asyncio
    async def test_no_active_streams_returns_empty(self):
        """Transport Level Error (2107) should return empty list."""
        mock_resp = {
            "apiVersion": "1.0",
            "error": {"code": 2107, "message": "Transport Level Error"},
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/streamstatus.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                result = await stream_status.get_stream_status(client)

        assert result == []

    @pytest.mark.asyncio
    async def test_method_not_supported_returns_empty(self):
        """Method not supported (2102) should return empty list."""
        mock_resp = {
            "apiVersion": "1.0",
            "error": {"code": 2102, "message": "Method not supported"},
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/streamstatus.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                result = await stream_status.get_stream_status(client)

        assert result == []

    @pytest.mark.asyncio
    async def test_other_vapix_error_raised(self):
        """Non-stream errors should propagate."""
        mock_resp = {
            "apiVersion": "1.0",
            "error": {"code": 1000, "message": "Internal Error"},
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/streamstatus.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                with pytest.raises(VapixError, match="Internal Error"):
                    await stream_status.get_stream_status(client)


# ---------------------------------------------------------------------------
# MQTT Client
# ---------------------------------------------------------------------------

class TestMQTTClient:
    @pytest.mark.asyncio
    async def test_get_client_status(self):
        """Should return status and config."""
        mock_resp = {
            "apiVersion": "1.6",
            "method": "getClientStatus",
            "data": {
                "status": {"state": "inactive", "connectionStatus": "disconnected"},
                "config": {
                    "server": {"protocol": "tcp", "host": "192.168.0.1", "port": 1883},
                    "clientId": "client_ABC123",
                    "keepAliveInterval": 60,
                },
            },
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/mqtt/client.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                result = await mqtt.get_client_status(client)

        assert result["status"]["state"] == "inactive"
        assert result["config"]["server"]["host"] == "192.168.0.1"

    @pytest.mark.asyncio
    async def test_configure_client(self):
        """Should send correct params to configure MQTT."""
        mock_resp = {"apiVersion": "1.0", "method": "configureClient", "data": {}}
        cam = _make_camera()
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/mqtt/client.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                await mqtt.configure_client(
                    client,
                    host="mqtt.example.com",
                    port=8883,
                    protocol="ssl",
                    username="user1",
                    password="pass1",
                )

        req_body = json.loads(route.calls.last.request.content)
        assert req_body["method"] == "configureClient"
        assert req_body["params"]["server"]["host"] == "mqtt.example.com"
        assert req_body["params"]["server"]["port"] == 8883
        assert req_body["params"]["username"] == "user1"

    @pytest.mark.asyncio
    async def test_activate_client(self):
        """Should call activateClient method."""
        mock_resp = {"apiVersion": "1.0", "method": "activateClient", "data": {}}
        cam = _make_camera()
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/mqtt/client.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                await mqtt.activate_client(client)

        req_body = json.loads(route.calls.last.request.content)
        assert req_body["method"] == "activateClient"

    @pytest.mark.asyncio
    async def test_deactivate_client(self):
        """Should call deactivateClient method."""
        mock_resp = {"apiVersion": "1.0", "method": "deactivateClient", "data": {}}
        cam = _make_camera()
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/mqtt/client.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                await mqtt.deactivate_client(client)

        req_body = json.loads(route.calls.last.request.content)
        assert req_body["method"] == "deactivateClient"


# ---------------------------------------------------------------------------
# MQTT Event Publication
# ---------------------------------------------------------------------------

class TestMQTTEventPublication:
    @pytest.mark.asyncio
    async def test_get_event_publication_config(self):
        """Should return event publication settings."""
        mock_resp = {
            "apiVersion": "1.2",
            "method": "getEventPublicationConfig",
            "data": {
                "eventPublicationConfig": {
                    "topicPrefix": "default",
                    "customTopicPrefix": "",
                    "appendEventTopic": True,
                    "includeTopicNamespaces": True,
                    "eventFilterList": [],
                }
            },
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/mqtt/event.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                result = await mqtt.get_event_publication_config(client)

        assert result["topicPrefix"] == "default"
        assert result["eventFilterList"] == []

    @pytest.mark.asyncio
    async def test_configure_event_publication(self):
        """Should send event publication config."""
        mock_resp = {"apiVersion": "1.0", "method": "configureEventPublication", "data": {}}
        cam = _make_camera()
        filters = [{"topicFilter": "onvif:Device/axis:IO/VirtualPort"}]
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/mqtt/event.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                await mqtt.configure_event_publication(
                    client,
                    event_filter_list=filters,
                    topic_prefix="custom",
                    custom_topic_prefix="home/cameras",
                )

        req_body = json.loads(route.calls.last.request.content)
        cfg = req_body["params"]["eventPublicationConfig"]
        assert cfg["topicPrefix"] == "custom"
        assert cfg["customTopicPrefix"] == "home/cameras"
        assert len(cfg["eventFilterList"]) == 1
