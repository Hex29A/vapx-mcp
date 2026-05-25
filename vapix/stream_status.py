"""
VAPIX Stream Status — Real-time stream diagnostics.

Endpoint: POST /axis-cgi/streamstatus.cgi
API Discovery ID: streamstatus

Returns information about active video streams including client count,
bitrate, FPS, resolution, and codec.  When no streams are active the
API returns an error code 2107 ("Transport Level Error") which this
module translates to an empty list.
"""

from typing import Any

from .client import VapixClient, VapixError

_PATH = "/axis-cgi/streamstatus.cgi"


async def get_stream_status(client: VapixClient) -> list[dict[str, Any]]:
    """
    Get status of all active video streams.

    Returns list of stream dicts, each containing:
        clients    — Number of connected clients
        bitrate    — Current bitrate in kbps
        fps        — Frames per second
        resolution — e.g. "1920x1080"
        codec      — e.g. "h264", "h265", "mjpeg"

    Returns empty list when no streams are active.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getStreamStatus",
    }
    try:
        data = await client.post_json(_PATH, payload)
    except VapixError as exc:
        # 2107 = Transport Level Error (no active streams)
        # 2102 = Method not supported (older firmware)
        if exc.code in (2107, 2102):
            return []
        raise

    streams = data.get("data", {}).get("streams", [])
    return streams
