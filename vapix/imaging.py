"""
VAPIX Snapshot API — Capture still images from Axis cameras.

Uses the classic CGI endpoint /axis-cgi/jpg/image.cgi which returns
a JPEG image as raw bytes.

Reference: https://developer.axis.com/vapix/network-video/
    (Under "Video streaming" → "Image requests")

Parameters:
    - resolution: Image resolution, e.g. "1920x1080", "640x480"
    - compression: JPEG compression 0 (best quality) to 100 (smallest file)
    - camera: Video channel (1-4, for multi-sensor cameras)
"""

from vapix.client import VapixClient


async def get_snapshot(
    client: VapixClient,
    resolution: str = "1920x1080",
    compression: int = 20,
    camera: int = 1,
) -> bytes:
    """
    Capture a JPEG snapshot from the camera.

    Args:
        client: VapixClient for the target camera.
        resolution: Desired image resolution (e.g. "1920x1080").
                    Camera will use closest supported resolution.
        compression: JPEG quality 0-100 (0 = best quality, 100 = most compressed).
                     Default 20 gives good quality at reasonable size.
        camera: Video channel number (1-4). Only relevant for
                multi-sensor cameras like the M3128-LVE.

    Returns:
        Raw JPEG image bytes.
    """
    params: dict = {
        "resolution": resolution,
        "compression": compression,
    }
    if camera > 1:
        params["camera"] = camera

    return await client.get_bytes("/axis-cgi/jpg/image.cgi", params=params)
