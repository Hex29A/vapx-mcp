"""
VAPIX HTTP Client — Base client for all VAPIX API calls.

Handles authentication (Digest for HTTP, Basic for HTTPS per Axis docs),
connection pooling, and error handling. Each camera gets its own client
instance with persistent HTTP/2 connections.

Reference: https://developer.axis.com/vapix/authentication/
- HTTP  → Digest access authentication
- HTTPS → Basic access authentication
"""

import logging
from typing import Any

import httpx

from config import CameraConfig

logger = logging.getLogger("vapix.client")


class VapixError(Exception):
    """Raised when a VAPIX API call returns an error response."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"VAPIX error {code}: {message}")


class VapixClient:
    """
    Async HTTP client for communicating with a single Axis camera.

    Uses the correct authentication method based on protocol:
    - HTTPS: Basic auth (encrypted channel protects credentials)
    - HTTP: Digest auth (credentials never sent in plaintext)

    Usage:
        client = VapixClient(camera_config)
        result = await client.post_json("/axis-cgi/basicdeviceinfo.cgi", payload)
        await client.close()
    """

    def __init__(self, camera: CameraConfig):
        self.camera = camera

        # Select auth method per Axis documentation:
        # HTTPS → Basic auth, HTTP → Digest auth
        if camera.https:
            auth = (camera.username, camera.password)  # Basic auth
        else:
            auth = httpx.DigestAuth(camera.username, camera.password)

        self._client = httpx.AsyncClient(
            base_url=camera.base_url,
            auth=auth,
            verify=camera.verify_ssl,
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=True,
        )

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        POST a JSON payload to a VAPIX CGI endpoint.

        Most modern VAPIX APIs (device info, light control, I/O ports)
        use this pattern: POST JSON → receive JSON response.

        Args:
            path: CGI path, e.g. "/axis-cgi/basicdeviceinfo.cgi"
            payload: JSON body with apiVersion, method, params, etc.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            VapixError: If the response contains an error object.
            httpx.HTTPStatusError: On HTTP-level errors (401, 500, etc.)
        """
        logger.debug("POST %s %s", path, payload.get("method", ""))
        response = await self._client.post(
            path,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        # Some cameras return HTTP 400 with a valid VAPIX JSON error body.
        # Parse the JSON error before raising HTTPStatusError so callers
        # can catch VapixError with the proper error code.
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                data = response.json()
                if "error" in data:
                    err = data["error"]
                    raise VapixError(
                        code=err.get("code", -1),
                        message=err.get("message", "Unknown VAPIX error"),
                    )
            except (ValueError, KeyError):
                pass
            raise

        data = response.json()

        # VAPIX JSON APIs return errors inside a 200 response with an "error" key
        if "error" in data:
            err = data["error"]
            raise VapixError(
                code=err.get("code", -1),
                message=err.get("message", "Unknown VAPIX error"),
            )

        return data

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        """
        GET request to a VAPIX CGI endpoint.

        Used for older CGI-style APIs (PTZ control, snapshots) that use
        query parameters instead of JSON bodies.

        Args:
            path: CGI path, e.g. "/axis-cgi/com/ptz.cgi"
            params: Query parameters dict.

        Returns:
            Raw httpx.Response (caller handles content type).

        Raises:
            httpx.HTTPStatusError: On HTTP-level errors.
        """
        logger.debug("GET %s params=%s", path, params)
        response = await self._client.get(path, params=params or {})
        response.raise_for_status()
        return response

    async def get_bytes(
        self, path: str, params: dict[str, Any] | None = None
    ) -> bytes:
        """
        GET raw bytes from a VAPIX endpoint (e.g. JPEG snapshot).

        Args:
            path: CGI path, e.g. "/axis-cgi/jpg/image.cgi"
            params: Query parameters.

        Returns:
            Response body as bytes.
        """
        response = await self.get(path, params)
        return response.content

    async def post(
        self, path: str, data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """
        POST form-encoded data to a VAPIX CGI endpoint.

        Used for legacy CGIs (e.g. temperaturecontrol.cgi) that expect
        application/x-www-form-urlencoded bodies.

        Args:
            path: CGI path.
            data: Form fields.

        Returns:
            Raw httpx.Response.
        """
        logger.debug("POST (form) %s", path)
        response = await self._client.post(path, data=data or {})
        response.raise_for_status()
        return response

    async def close(self):
        """Close the underlying HTTP client and release connections."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
