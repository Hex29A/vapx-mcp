"""
Tests for Phase 3 features: capture_mode, orientation, ntp, analytics_metadata,
auto-capability detection, batch tools, MCP resources, dispatch refactor.

Uses respx to mock HTTP responses.
"""

import json

import httpx
import pytest
import respx

from config import CameraConfig
from vapix import analytics_metadata, capture_mode, ntp, orientation
from vapix.client import VapixClient


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
        capabilities=[
            "snapshot", "ptz", "io", "light", "storage",
            "capture_mode", "orientation", "time", "analytics_metadata",
        ],
    )
    defaults.update(overrides)
    return CameraConfig(**defaults)


BASE_URL = "https://192.168.1.100:443"


# ---------------------------------------------------------------------------
# Capture Mode API
# ---------------------------------------------------------------------------

class TestCaptureModeAPI:
    @pytest.mark.asyncio
    async def test_get_capture_modes(self):
        """Should return list of capture modes per channel."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getCaptureModes",
            "data": [
                {
                    "channel": 0,
                    "captureMode": [
                        {"captureModeId": 0, "enabled": True, "maxFPS": 30.0,
                         "description": "1920x1080 (16:9) @ 30/60 fps"},
                        {"captureModeId": 1, "enabled": False,
                         "description": "1280x720 (16:9) @ 30/60 fps"},
                    ],
                }
            ],
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/capturemode.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await capture_mode.get_capture_modes(client)
            assert len(result) == 1
            assert result[0]["channel"] == 0
            assert len(result[0]["captureMode"]) == 2
            assert result[0]["captureMode"][0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_set_capture_mode(self):
        """Should send correct channel and mode ID."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "setCaptureMode",
            "data": {},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/capturemode.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await capture_mode.set_capture_mode(client, channel=0, capture_mode_id=1)
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["channel"] == 0
            assert body["params"]["captureModeId"] == 1


# ---------------------------------------------------------------------------
# Orientation API
# ---------------------------------------------------------------------------

class TestOrientationAPI:
    @pytest.mark.asyncio
    async def test_get_orientation(self):
        """Should parse XML orientation values."""
        long_xml = """<?xml version="1.0"?>
        <LongitudinalValue xmlns="http://www.axis.com/vapix/http_cgi/orientation1">
            <Value>45.5</Value>
        </LongitudinalValue>"""
        lat_xml = """<?xml version="1.0"?>
        <LateralValue xmlns="http://www.axis.com/vapix/http_cgi/orientation1">
            <Value>90.0</Value>
        </LateralValue>"""

        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(url__regex=r".*getlongitudinalvalue.*").mock(
                return_value=httpx.Response(200, text=long_xml)
            )
            respx.get(url__regex=r".*getlateralvalue.*").mock(
                return_value=httpx.Response(200, text=lat_xml)
            )
            result = await orientation.get_orientation(client)
            assert result["longitudinal"] == 45.5
            assert result["lateral"] == 90.0
            assert result["available"] is True

    @pytest.mark.asyncio
    async def test_get_orientation_unavailable(self):
        """Should handle missing orientation sensor gracefully."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(url__regex=r".*getlongitudinalvalue.*").mock(
                return_value=httpx.Response(404, text="Not found")
            )
            respx.get(url__regex=r".*getlateralvalue.*").mock(
                return_value=httpx.Response(404, text="Not found")
            )
            result = await orientation.get_orientation(client)
            assert result["available"] is False


# ---------------------------------------------------------------------------
# NTP API
# ---------------------------------------------------------------------------

class TestNTPAPI:
    @pytest.mark.asyncio
    async def test_get_ntp_info(self):
        """Should return NTP status and configuration."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getNTPInfo",
            "data": {
                "client": {
                    "enabled": True,
                    "serversSource": "static",
                    "staticServers": ["pool.ntp.org"],
                    "synced": True,
                    "timeOffset": 0.5,
                }
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/ntp.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await ntp.get_ntp_info(client)
            assert result["client"]["enabled"] is True
            assert result["client"]["synced"] is True

    @pytest.mark.asyncio
    async def test_set_ntp_config(self):
        """Should send NTP configuration correctly."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "setNTPClientConfiguration",
            "data": {},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/ntp.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await ntp.set_ntp_config(
                client,
                enabled=True,
                servers_source="static",
                static_servers=["time.google.com"],
            )
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["enabled"] is True
            assert body["params"]["staticServers"] == ["time.google.com"]


# ---------------------------------------------------------------------------
# Analytics Metadata API
# ---------------------------------------------------------------------------

class TestAnalyticsMetadataAPI:
    @pytest.mark.asyncio
    async def test_list_producers(self):
        """Should return list of analytics producers."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "listProducers",
            "data": {
                "producers": [
                    {
                        "name": "ObjectAnalytics",
                        "niceName": "Object Analytics",
                        "videochannels": [
                            {"channel": 0, "enabled": True},
                        ],
                    },
                    {
                        "name": "MotionGuard",
                        "niceName": "Motion Guard",
                        "videochannels": [
                            {"channel": 0, "enabled": False},
                        ],
                    },
                ],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/analyticsmetadataconfig.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await analytics_metadata.list_producers(client)
            assert len(result) == 2
            assert result[0]["name"] == "ObjectAnalytics"
            assert result[0]["videochannels"][0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_set_enabled_producers(self):
        """Should send producer enable/disable config."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "setEnabledProducers",
            "data": {},
        }
        producers = [
            {"name": "ObjectAnalytics", "videochannels": [{"channel": 0, "enabled": True}]},
        ]
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/analyticsmetadataconfig.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await analytics_metadata.set_enabled_producers(client, producers=producers)
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["producers"][0]["name"] == "ObjectAnalytics"

    @pytest.mark.asyncio
    async def test_get_supported_metadata(self):
        """Should return sample metadata XML."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getSupportedMetadata",
            "data": {
                "producers": [
                    {
                        "name": "ObjectAnalytics",
                        "sampleFrameXML": "<tt:MetadataStream>...</tt:MetadataStream>",
                    },
                ],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/analyticsmetadataconfig.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await analytics_metadata.get_supported_metadata(client)
            assert result[0]["name"] == "ObjectAnalytics"
            assert "MetadataStream" in result[0]["sampleFrameXML"]


# ---------------------------------------------------------------------------
# Server integration tests
# ---------------------------------------------------------------------------

class TestServerPhase3:
    @pytest.mark.asyncio
    async def test_tool_list_includes_all_new_tools(self):
        """All Phase 3 tools should be in the tools list."""
        from server import TOOLS
        tool_names = {t.name for t in TOOLS}
        new_tools = {
            "get_capture_modes", "set_capture_mode",
            "get_orientation",
            "get_ntp_status", "set_ntp_config",
            "list_analytics_producers", "set_analytics_producers",
            "snapshot_all", "status_all",
        }
        for tool in new_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

    @pytest.mark.asyncio
    async def test_total_tool_count(self):
        """Should have 65 tools total."""
        from server import TOOLS
        assert len(TOOLS) == 65, f"Expected 65 tools, got {len(TOOLS)}"

    @pytest.mark.asyncio
    async def test_handler_registry_complete(self):
        """Every camera tool should have a handler in the registry."""
        from server import _CAMERA_HANDLERS, _GLOBAL_HANDLERS, TOOLS
        all_handlers = set(_CAMERA_HANDLERS.keys()) | set(_GLOBAL_HANDLERS.keys())
        for tool in TOOLS:
            assert tool.name in all_handlers, f"Tool '{tool.name}' has no handler"

    @pytest.mark.asyncio
    async def test_dispatch_uses_handler_dict(self):
        """Dispatch should use the handler dict, not if/elif."""
        from server import _CAMERA_HANDLERS
        # Verify dict is populated with all expected handlers
        assert len(_CAMERA_HANDLERS) >= 52
        # Each entry should be (capability_or_None, callable)
        for name, (cap, handler) in _CAMERA_HANDLERS.items():
            assert callable(handler), f"Handler for {name} is not callable"
            assert cap is None or isinstance(cap, str), f"Bad capability for {name}"

    @pytest.mark.asyncio
    async def test_auto_capability_map_complete(self):
        """API-to-capability mapping should cover key APIs."""
        from server import _API_TO_CAPABILITY
        assert _API_TO_CAPABILITY["io-port-management"] == "io"
        assert _API_TO_CAPABILITY["ptz-control"] == "ptz"
        assert _API_TO_CAPABILITY["capture-mode"] == "capture_mode"
        assert _API_TO_CAPABILITY["ntp"] == "time"
        assert _API_TO_CAPABILITY["analytics-metadata-config"] == "analytics_metadata"
