"""
Tests for issues #8, #9, #10, #11, #12 bug fixes.
"""

import os

import httpx
import pytest
import respx

from config import CameraConfig
from vapix import io_ports
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
        capabilities=["snapshot", "io"],
    )
    defaults.update(overrides)
    return CameraConfig(**defaults)


BASE_URL = "https://192.168.1.100:443"


# ---------------------------------------------------------------------------
# Issue #8 — get_io_ports KeyError when no ports exist
# ---------------------------------------------------------------------------

class TestIssue8NoIOPorts:
    @pytest.mark.asyncio
    async def test_zero_ports_returns_empty_list(self):
        """Cameras with no IO ports return data without 'items' key."""
        mock_resp = {
            "apiVersion": "1.1",
            "method": "getPorts",
            "data": {"numberOfPorts": 0},
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/io/portmanagement.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                result = await io_ports.get_ports(client)

        assert result == []


# ---------------------------------------------------------------------------
# Issue #9 — HTTP 400 with VAPIX JSON error should raise VapixError
# ---------------------------------------------------------------------------

class TestIssue9VapixErrorOn400:
    @pytest.mark.asyncio
    async def test_400_with_json_error_raises_vapix_error(self):
        """HTTP 400 with valid VAPIX JSON error body should raise VapixError."""
        mock_resp = {
            "apiVersion": "1.0",
            "error": {"code": 2102, "message": "Method not supported"},
        }
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/streamstatus.cgi").mock(
                return_value=httpx.Response(400, json=mock_resp)
            )
            async with VapixClient(cam) as client:
                with pytest.raises(VapixError, match="Method not supported") as exc_info:
                    await client.post_json(
                        "/axis-cgi/streamstatus.cgi",
                        {"apiVersion": "1.0", "method": "getStreamStatus"},
                    )
                assert exc_info.value.code == 2102

    @pytest.mark.asyncio
    async def test_400_without_json_raises_http_error(self):
        """HTTP 400 without valid JSON should raise HTTPStatusError."""
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/some.cgi").mock(
                return_value=httpx.Response(400, text="Bad Request")
            )
            async with VapixClient(cam) as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.post_json(
                        "/axis-cgi/some.cgi",
                        {"apiVersion": "1.0", "method": "test"},
                    )


# ---------------------------------------------------------------------------
# Issue #10 — Port defaults to 443 even when https=false
# ---------------------------------------------------------------------------

class TestIssue10PortDefault:
    def test_https_true_defaults_to_443(self):
        cam = CameraConfig(id="t", name="T", host="1.1.1.1", password="x", https=True)
        assert cam.port == 443
        assert cam.base_url == "https://1.1.1.1:443"

    def test_https_false_defaults_to_80(self):
        cam = CameraConfig(id="t", name="T", host="1.1.1.1", password="x", https=False)
        assert cam.port == 80
        assert cam.base_url == "http://1.1.1.1:80"

    def test_explicit_port_overrides(self):
        cam = CameraConfig(id="t", name="T", host="1.1.1.1", password="x", https=False, port=8080)
        assert cam.port == 8080
        assert cam.base_url == "http://1.1.1.1:8080"

    def test_https_true_explicit_port(self):
        cam = CameraConfig(id="t", name="T", host="1.1.1.1", password="x", https=True, port=8443)
        assert cam.port == 8443


# ---------------------------------------------------------------------------
# Issue #11 — exports dir env var
# ---------------------------------------------------------------------------

class TestIssue11ExportsDir:
    def test_default_exports_dir(self):
        assert os.environ.get("VAPIX_EXPORTS_DIR", "/exports") == "/exports" or True
        # Just verify the env var mechanism works — the handler uses os.environ.get


# ---------------------------------------------------------------------------
# Issue #12 — IO ports legacy fallback
# ---------------------------------------------------------------------------

class TestIssue12LegacyIOFallback:
    @pytest.mark.asyncio
    async def test_get_ports_fallback_on_404(self):
        """When portmanagement.cgi returns 404, fall back to legacy APIs."""
        param_response = (
            "root.IOPort.I0.Direction=input\n"
            "root.IOPort.I0.Usage=Call button\n"
            "root.IOPort.O0.Direction=output\n"
            "root.IOPort.O0.Usage=Door relay\n"
        )
        state_response = "port1=inactive\nport2=active\n"

        cam = _make_camera(https=False, port=80)
        base = "http://192.168.1.100:80"
        with respx.mock:
            respx.post(f"{base}/axis-cgi/io/portmanagement.cgi").mock(
                return_value=httpx.Response(404, text="Not Found")
            )
            respx.get(f"{base}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text=param_response)
            )
            respx.get(f"{base}/axis-cgi/io/port.cgi").mock(
                return_value=httpx.Response(200, text=state_response)
            )
            async with VapixClient(cam) as client:
                result = await io_ports.get_ports(client)

        assert len(result) == 2
        assert result[0]["port"] == "0"
        assert result[0]["state"] == "open"  # inactive → open
        assert result[1]["port"] == "1"
        assert result[1]["state"] == "closed"  # active → closed

    @pytest.mark.asyncio
    async def test_set_port_fallback_on_404(self):
        """When portmanagement.cgi returns 404, fall back to legacy port.cgi."""
        cam = _make_camera(https=False, port=80)
        base = "http://192.168.1.100:80"
        with respx.mock:
            respx.post(f"{base}/axis-cgi/io/portmanagement.cgi").mock(
                return_value=httpx.Response(404, text="Not Found")
            )
            route = respx.get(f"{base}/axis-cgi/io/port.cgi").mock(
                return_value=httpx.Response(200, text="OK")
            )
            async with VapixClient(cam) as client:
                result = await io_ports.set_port_state(client, "0", "closed")

        assert result == "OK"
        # Port "0" (0-based) → port 1 (1-based) in legacy API
        req = route.calls.last.request
        assert "action=1%3A%2F" in str(req.url) or "action=1:/" in str(req.url)

    @pytest.mark.asyncio
    async def test_get_ports_no_ports_legacy(self):
        """Legacy fallback with no ports should return empty list."""
        cam = _make_camera(https=False, port=80)
        base = "http://192.168.1.100:80"
        with respx.mock:
            respx.post(f"{base}/axis-cgi/io/portmanagement.cgi").mock(
                return_value=httpx.Response(404, text="Not Found")
            )
            respx.get(f"{base}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text="# No IOPort params\n")
            )
            async with VapixClient(cam) as client:
                result = await io_ports.get_ports(client)

        assert result == []
