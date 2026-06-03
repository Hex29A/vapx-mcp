"""
VAPIX Audio Clip Management — List, play, upload, and delete audio clips.

Endpoints:
  GET  /axis-cgi/mediaclip.cgi?action=list              — list stored clips
  GET  /axis-cgi/mediaclip.cgi?action=play&clip=<id>   — trigger playback
  GET  /axis-cgi/mediaclip.cgi?action=stop              — stop playback
  GET  /axis-cgi/mediaclip.cgi?action=remove&clip=<id> — delete a clip
  POST /axis-cgi/mediaclip.cgi?action=upload&name=<n>  — upload .wav (multipart)
  GET  /axis-cgi/param.cgi?action=list&group=MediaClip  — clip metadata

Docs: https://developer.axis.com/vapix/network-video/audio/

Clips are addressed by integer ID on the wire, but the param.cgi group
stores human-readable names (root.MediaClip.M<id>.Name).  All public
functions accept either a clip name (string) or an integer ID so the
caller never needs to look up IDs manually.

Requires cameras with built-in speaker hardware.
"""

from typing import Any

import httpx

from .client import VapixClient, VapixError

_MEDIACLIP = "/axis-cgi/mediaclip.cgi"
_PARAM_CGI = "/axis-cgi/param.cgi"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_clips(text: str) -> list[dict[str, Any]]:
    """Parse param.cgi MediaClip group text into a list of clip dicts."""
    entries: dict[int, dict[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # key format: root.MediaClip.M<id>.Name / .Location / .Type
        parts = key.split(".")
        if len(parts) != 4 or parts[0] != "root" or parts[1] != "MediaClip":
            continue
        id_part = parts[2]
        if not id_part.startswith("M"):
            continue
        try:
            clip_id = int(id_part[1:])
        except ValueError:
            continue
        field = parts[3]
        entry = entries.setdefault(clip_id, {"id": clip_id})
        if field == "Name":
            entry["name"] = value
        elif field == "Location":
            entry["location"] = value
        elif field == "Type":
            entry["type"] = value
    return [entries[k] for k in sorted(entries)]


async def _resolve_id(client: VapixClient, name_or_id: str | int) -> int:
    """Resolve a clip name or ID to an integer ID."""
    if isinstance(name_or_id, int):
        return name_or_id
    try:
        return int(name_or_id)
    except ValueError:
        pass
    # Name lookup via param.cgi
    resp = await client.get(_PARAM_CGI, {"action": "list", "group": "MediaClip"})
    clips = _parse_clips(resp.text)
    name_lower = name_or_id.lower()
    for c in clips:
        if c.get("name", "").lower() == name_lower:
            return int(c["id"])
    raise VapixError(0, f"Audio clip '{name_or_id}' not found on camera")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def list_clips(client: VapixClient) -> list[dict[str, Any]]:
    """
    List audio clips stored on the camera.

    Returns list of dicts with keys: id, name, location, type (optional).
    Raises VapixError if the camera has no media clip support.
    """
    resp = await client.get(_PARAM_CGI, {"action": "list", "group": "MediaClip"})
    text = resp.text.strip()
    if not text or text.startswith("# Error:"):
        raise VapixError(0, "Audio clip management not available on this camera")
    clips = _parse_clips(text)
    return clips


async def play_clip(client: VapixClient, name_or_id: str | int) -> dict[str, Any]:
    """
    Trigger playback of an audio clip on the camera's built-in speaker.

    Args:
        name_or_id: Clip name (string) or integer ID.

    Returns:
        Dict with resolved clip id.
    """
    clip_id = await _resolve_id(client, name_or_id)
    await client.get(_MEDIACLIP, {"action": "play", "clip": str(clip_id)})
    return {"clip_id": clip_id, "status": "playing"}


async def stop_clips(client: VapixClient) -> dict[str, str]:
    """Stop any currently playing audio clip."""
    await client.get(_MEDIACLIP, {"action": "stop"})
    return {"status": "stopped"}


async def delete_clip(client: VapixClient, name_or_id: str | int) -> dict[str, Any]:
    """
    Delete an audio clip from the camera.

    Args:
        name_or_id: Clip name (string) or integer ID.

    Returns:
        Dict with resolved clip id.
    """
    clip_id = await _resolve_id(client, name_or_id)
    await client.get(_MEDIACLIP, {"action": "remove", "clip": str(clip_id)})
    return {"clip_id": clip_id, "status": "deleted"}


async def upload_clip(
    client: VapixClient,
    file_bytes: bytes,
    clip_name: str,
    filename: str = "clip.wav",
) -> dict[str, Any]:
    """
    Upload an audio clip (.wav) to the camera.

    The camera assigns an integer ID to the clip. The clip_name becomes
    the display name stored in root.MediaClip.M<id>.Name.

    Args:
        file_bytes: Raw .wav file content.
        clip_name:  Display name for the clip on the camera.
        filename:   Filename in the multipart body (default: "clip.wav").

    Returns:
        Dict with clip_name and assigned clip_id (if parseable from response).
    """
    files = {"file": (filename, file_bytes, "audio/wav")}
    params = {"action": "upload", "name": clip_name}
    # Use the underlying httpx client directly for multipart upload
    url = f"{_MEDIACLIP}?" + "&".join(f"{k}={v}" for k, v in params.items())
    response = await client._client.post(url, files=files)
    response.raise_for_status()

    # Parse assigned ID from response body ("uploaded=<id>" or "replaced=<id>")
    clip_id: int | None = None
    for line in response.text.splitlines():
        lower = line.strip().lower()
        for prefix in ("uploaded=", "replaced="):
            if lower.startswith(prefix):
                try:
                    clip_id = int(lower[len(prefix):].strip())
                except ValueError:
                    pass

    result: dict[str, Any] = {"clip_name": clip_name, "status": "uploaded"}
    if clip_id is not None:
        result["clip_id"] = clip_id
    return result
