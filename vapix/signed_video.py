"""
VAPIX Signed Video — Verify recording integrity status.

Primary endpoint:
  POST /axis-cgi/signedvideo.cgi  (firmware < 12.x, JSON API)

Fallback (firmware 12.x — signedvideo.cgi returns 404 despite being
listed in API discovery on some models, e.g. M3128-LVE, M2035-LE):
  GET /axis-cgi/param.cgi?action=list&group=root.SignedVideo
  GET /axis-cgi/param.cgi?action=list&group=root.Properties.API.SignedVideo

Both paths return signed video configuration.  The response always
includes a `source` field indicating which path was used so the caller
can distinguish live API data from param.cgi fallback data.

Docs: https://developer.axis.com/vapix/network-video/signed-video/
"""

from typing import Any

import httpx

from .client import VapixClient, VapixError

_SIGNED_VIDEO_PATH = "/axis-cgi/signedvideo.cgi"
_PARAM_CGI = "/axis-cgi/param.cgi"


async def get_status(client: VapixClient) -> dict[str, Any]:
    """
    Get signed video status for a camera.

    Tries signedvideo.cgi first; on 404 falls back to param.cgi parameter
    groups.  The returned dict always contains a `source` field:
      - "signedvideo_cgi"  — live JSON API response
      - "param_cgi_fallback" — derived from legacy param.cgi groups

    Returns:
        Dict with signed video configuration and `source` indicator.
        Raises VapixError if neither path is available.
    """
    # 1. Try the JSON API
    try:
        result = await client.post_json(
            _SIGNED_VIDEO_PATH,
            {"apiVersion": "1.0", "method": "getStatus"},
        )
        data = result.get("data", result)
        data["source"] = "signedvideo_cgi"
        return data
    except (VapixError, httpx.HTTPStatusError) as e:
        msg = str(e)
        if "404" not in msg and "Not Found" not in msg:
            raise VapixError(0, msg) from e
        # 404 — fall through to param.cgi

    # 2. Fallback: param.cgi groups
    params: dict[str, Any] = {}
    found = False

    resp1 = await client.get(
        _PARAM_CGI, {"action": "list", "group": "root.SignedVideo"}
    )
    text1 = resp1.text.strip()
    if text1 and not text1.startswith("# Error:"):
        for line in text1.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            short_key = key.replace("root.SignedVideo.", "")
            params[short_key] = value
            found = True

    resp2 = await client.get(
        _PARAM_CGI,
        {"action": "list", "group": "root.Properties.API.SignedVideo"},
    )
    text2 = resp2.text.strip()
    if text2 and not text2.startswith("# Error:"):
        for line in text2.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            short_key = key.replace("root.Properties.API.", "")
            params[short_key] = value
            found = True

    if not found:
        raise VapixError(
            0,
            "Signed video status not available on this camera "
            "(signedvideo.cgi returned 404 and no SignedVideo parameters found). "
            "Use discover_apis to check supported APIs.",
        )

    return {"signedVideo": params, "source": "param_cgi_fallback"}
