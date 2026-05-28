"""
Tests for VAPIX API modules — device, imaging, ptz, io_ports, light.

All tests use respx to mock HTTP responses. No real cameras are contacted.
Tests are non-destructive: they verify request structure and response parsing.

Each test validates:
    - Correct VAPIX endpoint is called
    - Request payload is properly structured
    - Response data is correctly parsed and returned
"""

import httpx
import pytest
import respx

from config import CameraConfig
from vapix import device, imaging, io_ports, light, ptz
from vapix.client import VapixClient, VapixError

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_client() -> tuple[CameraConfig, VapixClient]:
    """Create a test camera config and client."""
    camera = CameraConfig(
        id="test-cam",
        name="Test Camera",
        host="192.168.1.100",
        port=443,
        https=True,
        verify_ssl=False,
        username="root",
        password="testpass",
        capabilities=["snapshot", "ptz", "io", "light"],
    )
    return camera, VapixClient(camera)


BASE_URL = "https://192.168.1.100:443"


# ---------------------------------------------------------------------------
# Device API tests
# ---------------------------------------------------------------------------

class TestDeviceAPI:
    @pytest.mark.asyncio
    async def test_get_all_properties(self):
        """Test retrieving all device properties."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "context": "vapx-mcp",
            "method": "getAllProperties",
            "data": {
                "propertyList": {
                    "Architecture": "armv7hf",
                    "Brand": "AXIS",
                    "ProdFullName": "AXIS M2036-LE Network Camera",
                    "ProdNbr": "M2036-LE",
                    "SerialNumber": "ACCC8E123456",
                    "Version": "11.6.54",
                }
            },
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/basicdeviceinfo.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await device.get_all_properties(client)

            assert result["Brand"] == "AXIS"
            assert result["ProdNbr"] == "M2036-LE"
            assert result["SerialNumber"] == "ACCC8E123456"
            assert route.called

        await client.close()

    @pytest.mark.asyncio
    async def test_get_specific_properties(self):
        """Test retrieving a subset of device properties."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "data": {
                "propertyList": {
                    "Brand": "AXIS",
                    "Version": "11.6.54",
                }
            },
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/basicdeviceinfo.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await device.get_properties(client, ["Brand", "Version"])

            assert result["Brand"] == "AXIS"
            assert result["Version"] == "11.6.54"

            # Verify the request payload structure
            req = route.calls[0].request
            import json
            body = json.loads(req.content)
            assert body["method"] == "getProperties"
            assert body["params"]["propertyList"] == ["Brand", "Version"]

        await client.close()


# ---------------------------------------------------------------------------
# Imaging (snapshot) API tests
# ---------------------------------------------------------------------------

class TestImagingAPI:
    @pytest.mark.asyncio
    async def test_get_snapshot(self):
        """Test capturing a JPEG snapshot."""
        _camera, client = _make_client()
        # Minimal valid JPEG: starts with FFD8 (SOI marker)
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/jpg/image.cgi").mock(
                return_value=httpx.Response(
                    200,
                    content=fake_jpeg,
                    headers={"content-type": "image/jpeg"},
                )
            )

            result = await imaging.get_snapshot(client, resolution="640x480")

            assert result[:2] == b"\xff\xd8"  # JPEG SOI marker
            assert route.called

            # Verify query parameters
            req = route.calls[0].request
            assert "resolution=640x480" in str(req.url)
            assert "compression=20" in str(req.url)

        await client.close()

    @pytest.mark.asyncio
    async def test_snapshot_custom_compression(self):
        """Test snapshot with custom compression."""
        _camera, client = _make_client()
        fake_jpeg = b"\xff\xd8" + b"\x00" * 50

        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/jpg/image.cgi").mock(
                return_value=httpx.Response(200, content=fake_jpeg)
            )

            await imaging.get_snapshot(client, resolution="1920x1080", compression=50)

            req = route.calls[0].request
            assert "compression=50" in str(req.url)

        await client.close()


# ---------------------------------------------------------------------------
# PTZ API tests
# ---------------------------------------------------------------------------

class TestPTZAPI:
    @pytest.mark.asyncio
    async def test_move_absolute(self):
        """Test absolute PTZ movement."""
        _camera, client = _make_client()

        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="")
            )

            result = await ptz.move_absolute(client, pan=45.0, tilt=-10.0, zoom=500)

            assert result == "OK"
            req = route.calls[0].request
            url_str = str(req.url)
            assert "pan=45.0" in url_str
            assert "tilt=-10.0" in url_str
            assert "zoom=500" in url_str

        await client.close()

    @pytest.mark.asyncio
    async def test_move_relative(self):
        """Test relative PTZ movement."""
        _camera, client = _make_client()

        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="")
            )

            result = await ptz.move_relative(client, rpan=5.0, rtilt=-2.0, rzoom=100)

            assert result == "OK"
            req = route.calls[0].request
            url_str = str(req.url)
            assert "rpan=5.0" in url_str
            assert "rtilt=-2.0" in url_str

        await client.close()

    @pytest.mark.asyncio
    async def test_go_home(self):
        """Test moving to home position."""
        _camera, client = _make_client()

        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="")
            )

            result = await ptz.go_home(client)

            assert result == "OK"
            req = route.calls[0].request
            assert "move=home" in str(req.url)

        await client.close()

    @pytest.mark.asyncio
    async def test_go_to_preset(self):
        """Test moving to a named preset."""
        _camera, client = _make_client()

        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="")
            )

            result = await ptz.go_to_preset(client, "Entrance")

            assert result == "OK"
            req = route.calls[0].request
            assert "gotoserverpresetname=Entrance" in str(req.url)

        await client.close()

    @pytest.mark.asyncio
    async def test_get_position(self):
        """Test querying current PTZ position."""
        _camera, client = _make_client()

        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(
                    200, text="pan=45.1234\ntilt=-10.5678\nzoom=500\n"
                )
            )

            result = await ptz.get_position(client)

            assert result["pan"] == pytest.approx(45.1234)
            assert result["tilt"] == pytest.approx(-10.5678)
            assert result["zoom"] == pytest.approx(500.0)

        await client.close()


# ---------------------------------------------------------------------------
# I/O Ports API tests
# ---------------------------------------------------------------------------

class TestIOPortsAPI:
    @pytest.mark.asyncio
    async def test_get_ports(self):
        """Test retrieving I/O port information."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "getPorts",
            "data": {
                "numberOfPorts": 2,
                "items": [
                    {
                        "port": "0",
                        "state": "open",
                        "configurable": True,
                        "direction": "input",
                        "name": "Button",
                        "normalState": "open",
                    },
                    {
                        "port": "1",
                        "state": "closed",
                        "configurable": True,
                        "direction": "output",
                        "name": "Relay",
                        "normalState": "open",
                    },
                ],
            },
        }

        with respx.mock:
            route = respx.post(
                f"{BASE_URL}/axis-cgi/io/portmanagement.cgi"
            ).mock(return_value=httpx.Response(200, json=mock_resp))

            result = await io_ports.get_ports(client)

            assert len(result) == 2
            assert result[0]["port"] == "0"
            assert result[0]["direction"] == "input"
            assert result[1]["state"] == "closed"

        await client.close()

    @pytest.mark.asyncio
    async def test_set_port_state(self):
        """Test setting an output port state."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "setPorts",
            "data": {"ports": ["1"]},
        }

        with respx.mock:
            route = respx.post(
                f"{BASE_URL}/axis-cgi/io/portmanagement.cgi"
            ).mock(return_value=httpx.Response(200, json=mock_resp))

            result = await io_ports.set_port_state(client, port="1", state="closed")

            assert result == "OK"

            # Verify request structure
            import json
            req = route.calls[0].request
            body = json.loads(req.content)
            assert body["method"] == "setPorts"
            assert body["params"]["ports"][0]["port"] == "1"
            assert body["params"]["ports"][0]["state"] == "closed"

        await client.close()

    @pytest.mark.asyncio
    async def test_invalid_state_rejected(self):
        """Test that invalid port states are rejected locally."""
        _camera, client = _make_client()
        with pytest.raises(ValueError, match="must be 'open' or 'closed'"):
            await io_ports.set_port_state(client, "1", "active")

    @pytest.mark.asyncio
    async def test_pulse_port(self):
        """Test pulsing an output port with setStateSequence."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "setStateSequence",
            "data": {"port": "1"},
        }

        with respx.mock:
            route = respx.post(
                f"{BASE_URL}/axis-cgi/io/portmanagement.cgi"
            ).mock(return_value=httpx.Response(200, json=mock_resp))

            result = await io_ports.pulse_port(client, port="1", duration_ms=2000)

            assert result == "OK"

            import json
            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "setStateSequence"
            assert body["params"]["port"] == "1"
            assert len(body["params"]["sequence"]) == 2
            assert body["params"]["sequence"][0]["state"] == "closed"
            assert body["params"]["sequence"][0]["time"] == 2000

        await client.close()


# ---------------------------------------------------------------------------
# Light Control API tests
# ---------------------------------------------------------------------------

class TestLightAPI:
    @pytest.mark.asyncio
    async def test_get_light_information(self):
        """Test retrieving light information."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "getLightInformation",
            "data": {
                "items": [
                    {
                        "lightID": "led0",
                        "lightType": "IR",
                        "enabled": True,
                        "synchronizeDayNightMode": True,
                        "lightState": False,
                        "automaticIntensityMode": False,
                        "nrOfLEDs": 1,
                        "error": False,
                        "errorInfo": "",
                    },
                    {
                        "lightID": "led1",
                        "lightType": "WHITE",
                        "enabled": True,
                        "lightState": True,
                        "nrOfLEDs": 2,
                        "error": False,
                        "errorInfo": "",
                    },
                ]
            },
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await light.get_light_information(client)

            assert len(result) == 2
            assert result[0]["lightID"] == "led0"
            assert result[0]["lightType"] == "IR"
            assert result[1]["lightState"] is True

        await client.close()

    @pytest.mark.asyncio
    async def test_activate_light(self):
        """Test activating (turning on) a light."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "activateLight",
            "data": {},
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await light.activate_light(client, "led0")

            assert result == "OK"

            import json
            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "activateLight"
            assert body["params"]["lightID"] == "led0"

        await client.close()

    @pytest.mark.asyncio
    async def test_deactivate_light(self):
        """Test deactivating (turning off) a light."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "deactivateLight",
            "data": {},
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await light.deactivate_light(client, "led0")

            assert result == "OK"

            import json
            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "deactivateLight"
            assert body["params"]["lightID"] == "led0"

        await client.close()

    @pytest.mark.asyncio
    async def test_get_light_status(self):
        """Test checking light on/off status."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "getLightStatus",
            "data": {"status": True},
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await light.get_light_status(client, "led0")
            assert result is True

        await client.close()

    @pytest.mark.asyncio
    async def test_activate_invalid_light_raises_vapix_error(self):
        """Test that activating an invalid light ID returns a VAPIX error."""
        _camera, client = _make_client()

        error_resp = {
            "apiVersion": "1.0",
            "method": "activateLight",
            "error": {
                "code": 1002,
                "message": "Provided lightID parameter is not valid for the device.",
            },
        }

        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=error_resp)
            )

            with pytest.raises(VapixError) as exc_info:
                await light.activate_light(client, "nonexistent")

            assert exc_info.value.code == 1002
            assert "not valid" in exc_info.value.message

        await client.close()

    @pytest.mark.asyncio
    async def test_set_manual_intensity(self):
        """Test setting light intensity."""
        _camera, client = _make_client()

        mock_resp = {
            "apiVersion": "1.0",
            "method": "setManualIntensity",
            "data": {},
        }

        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/lightcontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )

            result = await light.set_manual_intensity(client, "led0", 75)

            assert result == "OK"

            import json
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["intensity"] == 75

        await client.close()
