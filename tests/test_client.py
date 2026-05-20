"""
Tests for vapix/client.py — VapixClient HTTP client.

Tests cover:
    - Auth method selection (Basic for HTTPS, Digest for HTTP)
    - JSON POST requests with successful and error responses
    - GET requests for raw content
    - VapixError parsing from VAPIX error responses
    - Connection lifecycle (close)

Uses respx to mock httpx requests — no real cameras needed.
"""

import pytest
import httpx
import respx

from config import CameraConfig
from vapix.client import VapixClient, VapixError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_camera(https: bool = True, port: int = 443) -> CameraConfig:
    """Create a test CameraConfig."""
    return CameraConfig(
        id="test-cam",
        name="Test Camera",
        host="192.168.1.100",
        port=port,
        https=https,
        verify_ssl=False,
        username="root",
        password="testpass",
        capabilities=["snapshot", "ptz", "io", "light"],
    )


# ---------------------------------------------------------------------------
# Auth method selection
# ---------------------------------------------------------------------------

class TestAuthSelection:
    def test_https_uses_basic_auth(self):
        """HTTPS cameras should use Basic auth (per Axis docs)."""
        camera = _make_camera(https=True)
        client = VapixClient(camera)
        assert isinstance(client._client.auth, httpx.BasicAuth)
        assert not isinstance(client._client.auth, httpx.DigestAuth)

    def test_http_uses_digest_auth(self):
        """HTTP cameras should use Digest auth (per Axis docs)."""
        camera = _make_camera(https=False, port=80)
        client = VapixClient(camera)
        assert isinstance(client._client.auth, httpx.DigestAuth)


# ---------------------------------------------------------------------------
# POST JSON requests
# ---------------------------------------------------------------------------

class TestPostJson:
    @pytest.mark.asyncio
    async def test_successful_post(self):
        """Test a successful JSON POST to a VAPIX endpoint."""
        camera = _make_camera()
        client = VapixClient(camera)

        mock_response = {
            "apiVersion": "1.0",
            "context": "vpx-mcp",
            "method": "getAllProperties",
            "data": {
                "propertyList": {
                    "Brand": "AXIS",
                    "ProdNbr": "M2036-LE",
                    "Version": "11.6.54",
                }
            },
        }

        with respx.mock:
            respx.post(
                f"{camera.base_url}/axis-cgi/basicdeviceinfo.cgi"
            ).mock(return_value=httpx.Response(200, json=mock_response))

            result = await client.post_json(
                "/axis-cgi/basicdeviceinfo.cgi",
                {"apiVersion": "1.0", "method": "getAllProperties"},
            )

            assert result["data"]["propertyList"]["Brand"] == "AXIS"
            assert result["data"]["propertyList"]["ProdNbr"] == "M2036-LE"

        await client.close()

    @pytest.mark.asyncio
    async def test_vapix_error_response(self):
        """Test that VAPIX error responses raise VapixError."""
        camera = _make_camera()
        client = VapixClient(camera)

        error_response = {
            "apiVersion": "1.0",
            "method": "getProperties",
            "error": {
                "code": 1000,
                "message": "Property not supported: invalid_prop",
            },
        }

        with respx.mock:
            respx.post(
                f"{camera.base_url}/axis-cgi/basicdeviceinfo.cgi"
            ).mock(return_value=httpx.Response(200, json=error_response))

            with pytest.raises(VapixError) as exc_info:
                await client.post_json(
                    "/axis-cgi/basicdeviceinfo.cgi",
                    {"apiVersion": "1.0", "method": "getProperties"},
                )

            assert exc_info.value.code == 1000
            assert "Property not supported" in exc_info.value.message

        await client.close()

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        """Test that HTTP errors (401, 500) raise httpx.HTTPStatusError."""
        camera = _make_camera()
        client = VapixClient(camera)

        with respx.mock:
            respx.post(
                f"{camera.base_url}/axis-cgi/basicdeviceinfo.cgi"
            ).mock(return_value=httpx.Response(401, text="Unauthorized"))

            with pytest.raises(httpx.HTTPStatusError):
                await client.post_json(
                    "/axis-cgi/basicdeviceinfo.cgi",
                    {"apiVersion": "1.0", "method": "getAllProperties"},
                )

        await client.close()


# ---------------------------------------------------------------------------
# GET requests
# ---------------------------------------------------------------------------

class TestGetRequests:
    @pytest.mark.asyncio
    async def test_get_returns_response(self):
        """Test a successful GET request."""
        camera = _make_camera()
        client = VapixClient(camera)

        with respx.mock:
            respx.get(f"{camera.base_url}/axis-cgi/com/ptz.cgi").mock(
                return_value=httpx.Response(200, text="pan=0.0\ntilt=0.0\nzoom=1\n")
            )

            response = await client.get(
                "/axis-cgi/com/ptz.cgi", {"query": "position"}
            )
            assert "pan=0.0" in response.text

        await client.close()

    @pytest.mark.asyncio
    async def test_get_bytes_returns_content(self):
        """Test getting raw bytes (e.g. JPEG snapshot)."""
        camera = _make_camera()
        client = VapixClient(camera)
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG magic + padding

        with respx.mock:
            respx.get(f"{camera.base_url}/axis-cgi/jpg/image.cgi").mock(
                return_value=httpx.Response(
                    200,
                    content=fake_jpeg,
                    headers={"content-type": "image/jpeg"},
                )
            )

            data = await client.get_bytes("/axis-cgi/jpg/image.cgi")
            assert data[:4] == b"\xff\xd8\xff\xe0"
            assert len(data) == 104

        await client.close()


# ---------------------------------------------------------------------------
# Context manager / lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test that VapixClient works as an async context manager."""
        camera = _make_camera()
        async with VapixClient(camera) as client:
            assert client.camera.id == "test-cam"
        # After exiting, client should be closed (no assertion needed,
        # just verify no exception)
