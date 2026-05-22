"""
Tests for server.py — MCP server tool dispatch and integration.

Tests cover:
    - Tool listing
    - list_cameras tool
    - Camera validation (missing camera, missing capability)
    - Tool dispatch for each major tool
    - Error handling (VAPIX errors, connection errors)

Uses respx for HTTP mocking and tests the _dispatch_tool function directly
to avoid needing a real MCP transport.
"""

import json

import httpx
import pytest
import respx
from mcp.types import ImageContent, TextContent

# We need to set up config before importing server internals
import server as srv
from config import AppConfig, CameraConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_config():
    """Set up a test config for all tests in this module."""
    srv.config = AppConfig(
        cameras=[
            CameraConfig(
                id="test-cam",
                name="Test Camera",
                host="192.168.1.100",
                port=443,
                https=True,
                verify_ssl=False,
                username="root",
                password="testpass",
                capabilities=["snapshot", "ptz", "io", "light", "overlay", "vmd", "guard_tour", "siren"],
            ),
            CameraConfig(
                id="snapshot-only",
                name="Snapshot Only Camera",
                host="192.168.1.101",
                port=443,
                https=True,
                verify_ssl=False,
                username="root",
                password="testpass",
                capabilities=["snapshot"],
            ),
        ]
    )
    # Clear cached clients
    srv._clients.clear()
    yield
    # Cleanup clients after test
    srv._clients.clear()


BASE_URL = "https://192.168.1.100:443"
BASE_URL_2 = "https://192.168.1.101:443"


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

class TestToolListing:
    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        """All defined tools should be returned."""
        tools = await srv.handle_list_tools()
        tool_names = [t.name for t in tools]

        assert "list_cameras" in tool_names
        assert "get_camera_info" in tool_names
        assert "get_snapshot" in tool_names
        assert "ptz_move" in tool_names
        assert "ptz_home" in tool_names
        assert "ptz_preset" in tool_names
        assert "ptz_status" in tool_names
        assert "get_io_ports" in tool_names
        assert "set_io_port" in tool_names
        assert "get_lights" in tool_names
        assert "toggle_light" in tool_names

    @pytest.mark.asyncio
    async def test_all_tools_have_input_schema(self):
        """Every tool should have a valid inputSchema."""
        tools = await srv.handle_list_tools()
        for tool in tools:
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"


# ---------------------------------------------------------------------------
# list_cameras
# ---------------------------------------------------------------------------

class TestListCameras:
    @pytest.mark.asyncio
    async def test_list_cameras(self):
        """list_cameras should return all configured cameras."""
        result = await srv._dispatch_tool("list_cameras", {})

        assert len(result) == 1
        assert isinstance(result[0], TextContent)

        data = json.loads(result[0].text)
        assert len(data) == 2
        assert data[0]["id"] == "test-cam"
        assert data[1]["id"] == "snapshot-only"
        assert "ptz" in data[0]["capabilities"]


# ---------------------------------------------------------------------------
# Camera validation
# ---------------------------------------------------------------------------

class TestCameraValidation:
    @pytest.mark.asyncio
    async def test_missing_camera_id(self):
        """Should return an error for missing camera_id."""
        result = await srv.handle_call_tool("get_camera_info", {})

        assert len(result) == 1
        assert "Error" in result[0].text
        assert "camera_id is required" in result[0].text

    @pytest.mark.asyncio
    async def test_unknown_camera_id(self):
        """Should return an error with available camera IDs."""
        result = await srv.handle_call_tool(
            "get_camera_info", {"camera_id": "nonexistent"}
        )

        assert "Error" in result[0].text
        assert "nonexistent" in result[0].text
        assert "test-cam" in result[0].text  # lists available cameras

    @pytest.mark.asyncio
    async def test_missing_capability(self):
        """Should error when camera lacks required capability."""
        result = await srv.handle_call_tool(
            "ptz_home", {"camera_id": "snapshot-only"}
        )

        assert "Error" in result[0].text
        assert "ptz" in result[0].text
        assert "capability" in result[0].text.lower()


# ---------------------------------------------------------------------------
# get_camera_info
# ---------------------------------------------------------------------------

class TestGetCameraInfo:
    @pytest.mark.asyncio
    async def test_get_camera_info_success(self):
        """Should return device properties as JSON."""
        mock_resp = {
            "apiVersion": "1.0",
            "data": {
                "propertyList": {
                    "Brand": "AXIS",
                    "ProdNbr": "M2036-LE",
                    "Version": "11.6.54",
                }
            },
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/basicdeviceinfo.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await srv._dispatch_tool(
                "get_camera_info", {"camera_id": "test-cam"}
            )

            data = json.loads(result[0].text)
            assert data["Brand"] == "AXIS"
            assert data["ProdNbr"] == "M2036-LE"


# ---------------------------------------------------------------------------
# get_snapshot
# ---------------------------------------------------------------------------

class TestGetSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_returns_image_content(self):
        """Snapshot should return ImageContent with base64 JPEG."""
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/jpg/image.cgi").mock(
                return_value=httpx.Response(
                    200,
                    content=fake_jpeg,
                    headers={"content-type": "image/jpeg"},
                )
            )

            result = await srv._dispatch_tool(
                "get_snapshot", {"camera_id": "test-cam"}
            )

            assert len(result) == 1
            assert isinstance(result[0], ImageContent)
            assert result[0].mimeType == "image/jpeg"

            # Verify it's valid base64
            import base64
            decoded = base64.b64decode(result[0].data)
            assert decoded[:4] == b"\xff\xd8\xff\xe0"


# ---------------------------------------------------------------------------
# PTZ tools
# ---------------------------------------------------------------------------

class TestPTZTools:
    @pytest.mark.asyncio
    async def test_ptz_move(self):
        """ptz_move should send absolute coordinates."""
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="")
            )

            result = await srv._dispatch_tool(
                "ptz_move",
                {"camera_id": "test-cam", "pan": 45, "tilt": -10, "zoom": 500},
            )

            assert "45" in result[0].text
            assert "-10" in result[0].text

    @pytest.mark.asyncio
    async def test_ptz_home(self):
        """ptz_home should send home command."""
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="")
            )

            result = await srv._dispatch_tool(
                "ptz_home", {"camera_id": "test-cam"}
            )

            assert "home" in result[0].text.lower()
            assert "move=home" in str(route.calls[0].request.url)

    @pytest.mark.asyncio
    async def test_ptz_status(self):
        """ptz_status should return current position."""
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(
                    200, text="pan=12.34\ntilt=-5.67\nzoom=100\n"
                )
            )

            result = await srv._dispatch_tool(
                "ptz_status", {"camera_id": "test-cam"}
            )

            data = json.loads(result[0].text)
            assert data["pan"] == pytest.approx(12.34)
            assert data["tilt"] == pytest.approx(-5.67)


# ---------------------------------------------------------------------------
# I/O port tools
# ---------------------------------------------------------------------------

class TestIOPortTools:
    @pytest.mark.asyncio
    async def test_get_io_ports(self):
        """get_io_ports should return port list."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getPorts",
            "data": {
                "numberOfPorts": 1,
                "items": [
                    {"port": "0", "state": "open", "direction": "output", "name": "Relay"},
                ],
            },
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/io/portmanagement.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await srv._dispatch_tool(
                "get_io_ports", {"camera_id": "test-cam"}
            )

            data = json.loads(result[0].text)
            assert len(data) == 1
            assert data[0]["port"] == "0"

    @pytest.mark.asyncio
    async def test_set_io_port(self):
        """set_io_port should send setPorts request."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "setPorts",
            "data": {"ports": ["1"]},
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/io/portmanagement.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await srv._dispatch_tool(
                "set_io_port",
                {"camera_id": "test-cam", "port": "1", "state": "closed"},
            )

            assert "closed" in result[0].text


# ---------------------------------------------------------------------------
# Light tools
# ---------------------------------------------------------------------------

class TestLightTools:
    @pytest.mark.asyncio
    async def test_get_lights(self):
        """get_lights should return light information."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getLightInformation",
            "data": {
                "items": [
                    {"lightID": "led0", "lightType": "IR", "enabled": True, "lightState": False},
                ]
            },
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await srv._dispatch_tool(
                "get_lights", {"camera_id": "test-cam"}
            )

            data = json.loads(result[0].text)
            assert data[0]["lightID"] == "led0"

    @pytest.mark.asyncio
    async def test_toggle_light_on(self):
        """toggle_light with on=true should call activateLight."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "activateLight",
            "data": {},
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await srv._dispatch_tool(
                "toggle_light",
                {"camera_id": "test-cam", "light_id": "led0", "on": True},
            )

            assert "Activated" in result[0].text

            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "activateLight"

    @pytest.mark.asyncio
    async def test_toggle_light_off(self):
        """toggle_light with on=false should call deactivateLight."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "deactivateLight",
            "data": {},
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await srv._dispatch_tool(
                "toggle_light",
                {"camera_id": "test-cam", "light_id": "led0", "on": False},
            )

            assert "Deactivated" in result[0].text

            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "deactivateLight"


# ---------------------------------------------------------------------------
# New API tools — Discovery, Overlay, VMD, Guard Tour, Siren
# ---------------------------------------------------------------------------

class TestDiscoverAPIs:
    @pytest.mark.asyncio
    async def test_discover_apis(self):
        """discover_apis should return the API list."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getApiList",
            "data": {
                "apiList": [
                    {"id": "basic-device-info", "version": "1.2", "status": "released"},
                ]
            },
        }
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/apidiscovery.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool("discover_apis", {"camera_id": "test-cam"})
            data = json.loads(result[0].text)
            assert data[0]["id"] == "basic-device-info"


class TestOverlayTools:
    @pytest.mark.asyncio
    async def test_list_overlays(self):
        mock_resp = {
            "apiVersion": "1.0",
            "method": "list",
            "data": {"textOverlays": [], "imageOverlays": [], "imageFiles": []},
        }
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool("list_overlays", {"camera_id": "test-cam"})
            data = json.loads(result[0].text)
            assert "textOverlays" in data

    @pytest.mark.asyncio
    async def test_add_overlay(self):
        mock_resp = {
            "apiVersion": "1.0",
            "method": "addText",
            "data": {"camera": 1, "identity": 7},
        }
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool(
                "add_overlay", {"camera_id": "test-cam", "text": "ALERT"}
            )
            assert "identity=7" in result[0].text

    @pytest.mark.asyncio
    async def test_remove_overlay(self):
        mock_resp = {"apiVersion": "1.0", "method": "remove", "data": {}}
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool(
                "remove_overlay", {"camera_id": "test-cam", "identity": 7}
            )
            assert "Removed" in result[0].text


class TestMotionDetectionTools:
    @pytest.mark.asyncio
    async def test_get_motion_config(self):
        mock_resp = {
            "apiVersion": "1.3",
            "method": "getConfiguration",
            "data": {"cameras": [{"active": True, "id": 1}], "profiles": [], "configurationStatus": 0},
        }
        with respx.mock:
            respx.post(f"{BASE_URL}/local/vmd/control.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool("get_motion_config", {"camera_id": "test-cam"})
            data = json.loads(result[0].text)
            assert data["cameras"][0]["active"] is True

    @pytest.mark.asyncio
    async def test_set_motion_config(self):
        mock_resp = {"apiVersion": "1.3", "method": "setConfiguration", "data": {}}
        with respx.mock:
            respx.post(f"{BASE_URL}/local/vmd/control.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool(
                "set_motion_config",
                {"camera_id": "test-cam", "cameras": [{"active": True, "id": 1}], "profiles": []},
            )
            assert "Updated" in result[0].text


class TestGuardTourTools:
    @pytest.mark.asyncio
    async def test_list_guard_tours(self):
        response_text = "root.GuardTour.G0.Name=Patrol\nroot.GuardTour.G0.Running=no\n"
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text=response_text)
            )
            result = await srv._dispatch_tool("list_guard_tours", {"camera_id": "test-cam"})
            data = json.loads(result[0].text)
            assert len(data) == 1
            assert data[0]["name"] == "Patrol"

    @pytest.mark.asyncio
    async def test_start_guard_tour(self):
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text="OK")
            )
            result = await srv._dispatch_tool(
                "start_guard_tour", {"camera_id": "test-cam", "tour_id": "G0"}
            )
            assert "Started" in result[0].text

    @pytest.mark.asyncio
    async def test_stop_guard_tour(self):
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text="OK")
            )
            result = await srv._dispatch_tool(
                "stop_guard_tour", {"camera_id": "test-cam", "tour_id": "G0"}
            )
            assert "Stopped" in result[0].text


class TestSirenTools:
    @pytest.mark.asyncio
    async def test_get_siren_status(self):
        mock_resp = {"apiVersion": "1.0", "method": "getStatus", "data": {}}
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool("get_siren_status", {"camera_id": "test-cam"})
            data = json.loads(result[0].text)
            assert data == {}

    @pytest.mark.asyncio
    async def test_activate_siren_with_profile(self):
        mock_resp = {"apiVersion": "1.0", "method": "start", "data": {"sirenId": 1, "lightId": 1}}
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool(
                "activate_siren", {"camera_id": "test-cam", "profile": "Intrusion"}
            )
            assert "Activated" in result[0].text

    @pytest.mark.asyncio
    async def test_stop_siren(self):
        mock_resp = {"apiVersion": "1.0", "method": "stop", "data": {}}
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await srv._dispatch_tool("stop_siren", {"camera_id": "test-cam"})
            assert "Stopped" in result[0].text


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_vapix_error_handled(self):
        """VAPIX API errors should be caught and returned as text."""
        error_resp = {
            "apiVersion": "1.0",
            "error": {"code": 2003, "message": "API version not supported"},
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/basicdeviceinfo.cgi").mock(
                return_value=httpx.Response(200, json=error_resp)
            )

            result = await srv.handle_call_tool(
                "get_camera_info", {"camera_id": "test-cam"}
            )

            assert "Error" in result[0].text
            assert "2003" in result[0].text

    @pytest.mark.asyncio
    async def test_unknown_tool_handled(self):
        """Unknown tool names should return an error."""
        result = await srv.handle_call_tool(
            "nonexistent_tool", {"camera_id": "test-cam"}
        )

        assert "Error" in result[0].text
        assert "Unknown tool" in result[0].text
