"""
VAPIX Edge Storage — Disk status, health, and recording management.

Endpoints:
    GET /axis-cgi/disks/list.cgi       — list disks (SD card, network share)
    GET /axis-cgi/disks/gethealth.cgi  — disk health (wear, temperature)
    GET /axis-cgi/record/list.cgi      — list recordings
    GET /axis-cgi/record/export/properties.cgi  — export properties (size, times)
    GET /axis-cgi/record/export/exportrecording.cgi — download recording as .mkv

Docs: https://developer.axis.com/vapix/network-video/edge-storage-api/

All these APIs return XML (except export which returns binary .mkv).
We parse XML into Python dicts for JSON output.
"""

import os
import xml.etree.ElementTree as ET
from typing import Any

from .client import VapixClient


def _xml_to_dicts(xml_text: str, element_tag: str) -> list[dict[str, str]]:
    """Parse XML and extract all elements matching tag as attribute dicts."""
    root = ET.fromstring(xml_text)
    results = []
    for elem in root.iter(element_tag):
        results.append(dict(elem.attrib))
    return results


async def list_disks(client: VapixClient, disk_id: str = "all") -> list[dict[str, str]]:
    """
    List available disks (SD cards, network shares).

    Returns list of dicts with keys:
        diskid, name, totalsize, freesize, status, filesystem,
        locked, full, readonly, group, cleanuppolicy, etc.

    Sizes are in kilobytes.
    """
    response = await client.get(
        "/axis-cgi/disks/list.cgi",
        {"diskid": disk_id},
    )
    return _xml_to_dicts(response.text, "disk")


async def get_disk_health(client: VapixClient) -> list[dict[str, Any]]:
    """
    Get health status of all disks (wear level, temperature, overall).

    Returns list of dicts with keys like:
        diskid, overallHealth, temperature, wearLevel
    """
    response = await client.get("/axis-cgi/disks/gethealth.cgi")
    text = response.text

    # gethealth.cgi may return JSON on newer firmware or XML on older
    if text.strip().startswith("{"):
        import json
        data = json.loads(text)
        return data.get("data", {}).get("disks", [data.get("data", {})])

    # XML fallback
    root = ET.fromstring(text)
    disks = []

    # Modern format: <HealthStatus diskid="..." wear="..." />
    for hs in root.iter("HealthStatus"):
        disks.append(dict(hs.attrib))

    # Older format: <disk diskid="..."><overallHealth>...</overallHealth></disk>
    if not disks:
        for disk_elem in root.iter("disk"):
            disk: dict[str, Any] = dict(disk_elem.attrib)
            for child in disk_elem:
                disk[child.tag] = child.text or dict(child.attrib)
            disks.append(disk)

    return disks if disks else [{"raw": text.strip()}]


# XML attribute names (Axis convention) -> snake_case keys matching the
# camera_id/recording_id/disk_id params expected by get_recording_info and
# export_recording, so list_recordings output can be fed straight back in
# without an LLM having to silently translate the names (issue #17).
_RECORDING_KEY_MAP = {
    "recordingid": "recording_id",
    "diskid": "disk_id",
    "starttime": "start_time",
    "starttimelocal": "start_time_local",
    "stoptime": "stop_time",
    "stoptimelocal": "stop_time_local",
    "recordingtype": "recording_type",
    "eventtrigger": "event_trigger",
}


async def list_recordings(
    client: VapixClient,
    *,
    recording_id: str = "all",
    disk_id: str | None = None,
    start_time: str | None = None,
    stop_time: str | None = None,
    max_recordings: int = 1000,
) -> list[dict[str, Any]]:
    """
    List recordings stored on the device.

    Args:
        recording_id: Specific recording ID or "all" (default).
        disk_id: Filter by disk (e.g. "SD_DISK", "NetworkShare").
        start_time: Filter start time (ISO 8601 UTC, e.g. "2024-01-01T00:00:00Z").
        stop_time: Filter stop time.
        max_recordings: Maximum number of recordings to return (default 1000).
            Always sent to the camera — some firmware returns only the single
            most recent recording when this parameter is omitted, despite the
            VAPIX docs saying "returns all if omitted" (issue #16).

    Returns list of dicts with keys:
        recording_id, disk_id, start_time, stop_time, recording_type,
        event_trigger, source (video/audio attributes as nested dicts)
    """
    params: dict[str, Any] = {
        "recordingid": recording_id,
        "maxnumberofrecordings": max_recordings,
    }
    if disk_id:
        params["diskid"] = disk_id
    if start_time:
        params["starttime"] = start_time
    if stop_time:
        params["stoptime"] = stop_time

    response = await client.get("/axis-cgi/record/list.cgi", params)
    text = response.text

    root = ET.fromstring(text)
    recordings = []

    for rec in root.iter("recording"):
        raw: dict[str, Any] = dict(rec.attrib)
        entry: dict[str, Any] = {_RECORDING_KEY_MAP.get(k, k): v for k, v in raw.items()}
        # Extract video/audio sub-elements
        for child in rec:
            if child.tag in ("video", "audio"):
                entry[child.tag] = dict(child.attrib)
        recordings.append(entry)

    # Include summary from root
    for recs_elem in root.iter("recordings"):
        total = recs_elem.attrib.get("totalnumberofrecordings")
        if total:
            recordings.insert(0, {
                "_summary": True,
                "total_recordings": int(total),
                "returned": int(recs_elem.attrib.get("numberofrecordings", 0)),
            })
        break

    return recordings


async def get_export_properties(
    client: VapixClient,
    recording_id: str,
    disk_id: str,
    *,
    start_time: str | None = None,
    stop_time: str | None = None,
) -> dict[str, str]:
    """
    Get export properties for a recording (estimated size, proper timestamps).

    Should be called before exporting to check file size.

    Args:
        recording_id: Recording ID from list_recordings.
        disk_id: Disk ID where the recording is stored.
        start_time: Optional clip start time (ISO 8601 UTC).
        stop_time: Optional clip stop time.

    Returns dict with:
        RecordingId, ExportFormat, EstimatedFileSize, Starttime, Stoptime
    """
    params: dict[str, Any] = {
        "schemaversion": "1",
        "recordingid": recording_id,
        "diskid": disk_id,
    }
    if start_time:
        params["starttime"] = start_time
    if stop_time:
        params["stoptime"] = stop_time

    response = await client.get("/axis-cgi/record/export/properties.cgi", params)
    text = response.text

    root = ET.fromstring(text)
    for props in root.iter("ExportProperties"):
        return dict(props.attrib)

    # Check for error
    for err in root.iter("GeneralError"):
        raise Exception(f"Export error: {err.attrib}")

    return {"raw": text.strip()}


async def export_recording(
    client: VapixClient,
    recording_id: str,
    disk_id: str,
    output_path: str,
    *,
    start_time: str | None = None,
    stop_time: str | None = None,
) -> dict[str, Any]:
    """
    Export a recording (or clip) as a .mkv file to the local filesystem.

    Downloads the binary stream from the camera and writes it to output_path.
    Use get_export_properties() first to check estimated file size.

    Args:
        recording_id: Recording ID from list_recordings.
        disk_id: Disk ID where the recording is stored.
        output_path: Local file path to write the .mkv file.
        start_time: Optional clip start time (ISO 8601 UTC).
        stop_time: Optional clip stop time.

    Returns dict with:
        path: Output file path
        size_bytes: Actual file size in bytes
    """
    params: dict[str, Any] = {
        "schemaversion": "1",
        "recordingid": recording_id,
        "diskid": disk_id,
        "exportformat": "matroska",
    }
    if start_time:
        params["starttime"] = start_time
    if stop_time:
        params["stoptime"] = stop_time

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    response = await client.get(
        "/axis-cgi/record/export/exportrecording.cgi", params
    )

    # Check for XML error response
    content_type = response.headers.get("content-type", "")
    if "xml" in content_type or "text" in content_type:
        text = response.text.strip()
        if "Error" in text or "error" in text:
            raise Exception(f"Export error: {text}")

    # Write binary content to file
    with open(output_path, "wb") as f:
        f.write(response.content)

    file_size = os.path.getsize(output_path)
    return {
        "path": output_path,
        "size_bytes": file_size,
    }
