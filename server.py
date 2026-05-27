"""
VPX MCP Server — Main entry point.

A Model Context Protocol (MCP) server that exposes Axis camera VAPIX APIs
as tools for AI assistants. Runs over stdio transport by default, with
optional SSE/HTTP transport for Docker deployments.

Usage:
    # stdio mode (default — for MCP client integration)
    python server.py

    # SSE mode (for Docker / web access)
    python server.py --transport sse --port 8080

Environment:
    VAPIX_CONFIG: Path to cameras.yaml (default: ./cameras.yaml)

Tools provided:
    - list_cameras: List all configured cameras and capabilities
    - get_camera_info: Get device info (model, firmware, serial)
    - get_snapshot: Capture a still JPEG image
    - ptz_move: Move camera to absolute pan/tilt/zoom position
    - ptz_relative: Move camera by relative offset
    - ptz_home: Return camera to home position
    - ptz_preset: Move camera to a named preset
    - ptz_status: Get current PTZ position
    - get_io_ports: List all I/O ports and their states
    - set_io_port: Set an output port state (open/closed)
    - get_lights: List all lights and their states
    - toggle_light: Turn a camera light on or off
"""

import argparse
import base64
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.types import (
    AnyUrl,
    BlobResourceContents,
    ImageContent,
    Resource,
    TextContent,
    Tool,
)

from config import AppConfig, CameraConfig, load_config
from vapix import (
    analytics_metadata,
    audio,
    capture_mode,
    clear_view,
    daynight,
    device,
    discovery,
    events,
    geolocation,
    guard_tour,
    imaging,
    io_ports,
    light,
    mqtt,
    ntp,
    orientation,
    overlay,
    privacy_mask,
    ptz,
    siren,
    storage,
    stream_profiles,
    stream_status,
    temperature,
    time_service,
    vmd,
)
from vapix.client import VapixClient, VapixError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,  # MCP uses stdout for protocol; logs go to stderr
)
logger = logging.getLogger("vpx-mcp")

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
app = Server("vpx-mcp")
config: AppConfig | None = None
# Cache VapixClient instances per camera_id
_clients: dict[str, VapixClient] = {}

# Map VAPIX API discovery IDs to our capability names.
# Note: param-cgi is the legacy parameter API; we map it to daynight since
# day/night config is served via param.cgi and has no dedicated JSON API.
_API_TO_CAPABILITY: dict[str, str] = {
    "io-port-management": "io",
    "light-control": "light",
    "ptz-control": "ptz",
    "dynamicoverlay": "overlay",
    "guard-tour": "guard_tour",
    "siren-and-light": "siren",
    "disk-management": "storage",
    "recording": "storage",
    "recording-export": "storage",
    "clear-view": "clear_view",
    "privacy-mask": "privacy_mask",
    "time-service": "time",
    "stream-profiles": "stream_profiles",
    "audio-device-control": "audio",
    "event-streaming-over-websocket": "events",
    "capture-mode": "capture_mode",
    "orientation": "orientation",
    "ntp": "time",
    "analytics-metadata-config": "analytics_metadata",
    "temperaturecontrol": "temperature",
    "streamstatus": "stream_status",
    "mqtt-client": "mqtt",
    "event-mqtt-bridge": "mqtt",
    "param-cgi": "daynight",
}


def _get_config() -> AppConfig:
    """Get the loaded config, raising if not initialized."""
    global config
    if config is None:
        config = load_config()
    return config


def _get_client(camera: CameraConfig) -> VapixClient:
    """Get or create a VapixClient for a camera (connection pooling)."""
    if camera.id not in _clients:
        _clients[camera.id] = VapixClient(camera)
    return _clients[camera.id]


async def _auto_detect_capabilities(camera: CameraConfig) -> None:
    """
    Auto-detect capabilities via API Discovery and merge into camera config.

    Called when capabilities contains "auto". Discovered capabilities are
    merged with any explicitly listed ones (manual entries take precedence).
    """
    client = _get_client(camera)
    try:
        apis = await discovery.get_api_list(client)
        discovered = {"snapshot"}  # snapshot is always available
        for api_info in apis:
            api_id = api_info.get("id", "")
            cap = _API_TO_CAPABILITY.get(api_id)
            if cap:
                discovered.add(cap)
        # Merge: keep manual capabilities, add discovered ones
        manual = {c for c in camera.capabilities if c != "auto"}
        camera.capabilities = sorted(manual | discovered)
        logger.info(
            "Auto-detected capabilities for %s: %s",
            camera.id,
            camera.capabilities,
        )
    except Exception as e:
        logger.warning(
            "Auto-detection failed for %s: %s — using manual capabilities",
            camera.id, e,
        )
        camera.capabilities = [c for c in camera.capabilities if c != "auto"]
        if not camera.capabilities:
            camera.capabilities = ["snapshot"]


def _resolve_camera(camera_id: str) -> tuple[CameraConfig, VapixClient]:
    """
    Look up a camera by ID and return its config + client.

    Raises ValueError with a helpful message if the camera ID is not found.
    """
    cfg = _get_config()
    camera = cfg.get_camera(camera_id)
    if camera is None:
        available = ", ".join(cfg.camera_ids())
        raise ValueError(
            f"Camera '{camera_id}' not found. Available cameras: {available}"
        )
    return camera, _get_client(camera)


def _check_capability(camera: CameraConfig, capability: str) -> None:
    """Raise ValueError if the camera doesn't support a capability."""
    if capability not in camera.capabilities:
        raise ValueError(
            f"Camera '{camera.id}' ({camera.name}) does not have the "
            f"'{capability}' capability. Its capabilities: {camera.capabilities}"
        )


def _text_result(data: Any) -> list[TextContent]:
    """Wrap data as MCP TextContent JSON response."""
    if isinstance(data, str):
        return [TextContent(type="text", text=data)]
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def _error_result(message: str) -> list[TextContent]:
    """Wrap an error message as MCP TextContent."""
    return [TextContent(type="text", text=f"Error: {message}")]


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
TOOLS = [
    Tool(
        name="list_cameras",
        description="List all configured Axis cameras with their IDs, names, and capabilities",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_camera_info",
        description=(
            "Get device information for an Axis camera: model, serial number, "
            "firmware version, hardware ID, architecture, etc."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {
                    "type": "string",
                    "description": "Camera identifier from list_cameras",
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="get_snapshot",
        description=(
            "Capture a still JPEG image from an Axis camera. "
            "Returns the image directly for visual inspection."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {
                    "type": "string",
                    "description": "Camera identifier",
                },
                "resolution": {
                    "type": "string",
                    "description": 'Image resolution, e.g. "1920x1080", "1280x720", "640x480"',
                    "default": "1920x1080",
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="ptz_move",
        description=(
            "Move a PTZ camera to an absolute pan/tilt/zoom position. "
            "Pan: -180 to 180 (degrees), Tilt: -180 to 180, Zoom: 1-9999."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "pan": {
                    "type": "number",
                    "description": "Pan angle in degrees (-180 to 180). Negative=left, positive=right.",
                },
                "tilt": {
                    "type": "number",
                    "description": "Tilt angle in degrees (-180 to 180). Negative=down, positive=up.",
                },
                "zoom": {
                    "type": "integer",
                    "description": "Zoom level (1=wide to 9999=telephoto)",
                    "minimum": 1,
                    "maximum": 9999,
                },
            },
            "required": ["camera_id", "pan", "tilt", "zoom"],
        },
    ),
    Tool(
        name="ptz_relative",
        description="Move a PTZ camera by a relative offset from its current position.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "rpan": {"type": "number", "description": "Relative pan offset", "default": 0},
                "rtilt": {"type": "number", "description": "Relative tilt offset", "default": 0},
                "rzoom": {"type": "integer", "description": "Relative zoom offset", "default": 0},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="ptz_home",
        description="Return a PTZ camera to its home position.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="ptz_preset",
        description="Move a PTZ camera to a named preset position.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "preset_name": {
                    "type": "string",
                    "description": "Name of the preset position (case-sensitive)",
                },
            },
            "required": ["camera_id", "preset_name"],
        },
    ),
    Tool(
        name="ptz_status",
        description="Get the current pan/tilt/zoom position of a PTZ camera.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="get_io_ports",
        description=(
            "List all I/O ports on a camera/device with their current states, "
            "directions (input/output), and configurations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_io_port",
        description=(
            'Set the state of a digital output port. Use "closed" to activate '
            '(energize relay) or "open" to deactivate.'
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "port": {
                    "type": "string",
                    "description": 'Port ID (e.g. "0", "1"). Get from get_io_ports.',
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed"],
                    "description": '"open" = deactivate/inactive, "closed" = activate/active',
                },
            },
            "required": ["camera_id", "port", "state"],
        },
    ),
    Tool(
        name="get_lights",
        description=(
            "List all lights (IR, white, indicator) on a camera with their "
            "current state, type, and configuration."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="toggle_light",
        description=(
            "Turn a camera light on or off. Use get_lights first to find "
            'available light IDs (e.g. "led0").'
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "light_id": {
                    "type": "string",
                    "description": 'Light identifier (e.g. "led0"). Get from get_lights.',
                },
                "on": {
                    "type": "boolean",
                    "description": "true to turn on, false to turn off",
                },
            },
            "required": ["camera_id", "light_id", "on"],
        },
    ),
    # --- API Discovery ---
    Tool(
        name="discover_apis",
        description=(
            "List all VAPIX APIs supported by an Axis device. "
            "Useful for checking what capabilities a camera has before "
            "attempting operations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    # --- Overlay tools ---
    Tool(
        name="list_overlays",
        description=(
            "List all text and image overlays currently on the camera's video stream."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="add_overlay",
        description=(
            "Add a text overlay to the camera's live video stream. "
            "Use format strings like %c for date/time. Max 512 characters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "text": {
                    "type": "string",
                    "description": "Overlay text. Supports %c (date+time), %H (hour), etc.",
                    "maxLength": 512,
                },
                "position": {
                    "type": "string",
                    "enum": ["topLeft", "topRight", "bottomLeft", "bottomRight"],
                    "description": "Position on the video (default: topLeft)",
                    "default": "topLeft",
                },
                "text_color": {
                    "type": "string",
                    "description": "Text color (white, black, red, etc.)",
                    "default": "white",
                },
                "text_bg_color": {
                    "type": "string",
                    "description": "Background color (transparent, black, white, etc.)",
                    "default": "transparent",
                },
            },
            "required": ["camera_id", "text"],
        },
    ),
    Tool(
        name="remove_overlay",
        description="Remove an overlay from the camera's video stream by its identity.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "identity": {
                    "type": "integer",
                    "description": "Overlay identity (from list_overlays or add_overlay)",
                },
            },
            "required": ["camera_id", "identity"],
        },
    ),
    # --- Motion Detection tools ---
    Tool(
        name="get_motion_config",
        description=(
            "Get the current video motion detection (VMD4) configuration, "
            "including detection zones, filters, and trigger areas."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_motion_config",
        description=(
            "Set video motion detection (VMD4) configuration. "
            "Pass the full cameras and profiles arrays as returned by get_motion_config."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "cameras": {
                    "type": "array",
                    "description": "Camera configs array (from get_motion_config)",
                },
                "profiles": {
                    "type": "array",
                    "description": "Detection profile configs (zones, filters, triggers)",
                },
            },
            "required": ["camera_id", "cameras", "profiles"],
        },
    ),
    # --- Guard Tour tools ---
    Tool(
        name="list_guard_tours",
        description=(
            "List all configured guard tours (automated PTZ patrol routes) "
            "on a camera, including their presets and running status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="start_guard_tour",
        description='Start a guard tour (automated PTZ patrol). Use tour ID from list_guard_tours (e.g. "G0").',
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "tour_id": {
                    "type": "string",
                    "description": 'Guard tour ID (e.g. "G0"). Get from list_guard_tours.',
                },
            },
            "required": ["camera_id", "tour_id"],
        },
    ),
    Tool(
        name="stop_guard_tour",
        description="Stop a running guard tour.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "tour_id": {
                    "type": "string",
                    "description": 'Guard tour ID (e.g. "G0").',
                },
            },
            "required": ["camera_id", "tour_id"],
        },
    ),
    # --- Siren & Light tools ---
    Tool(
        name="get_siren_status",
        description=(
            "Get the current status of siren and strobe light devices. "
            "Returns empty if idle, or active siren/light details."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera/device identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="activate_siren",
        description=(
            "Activate a siren and/or strobe light on a deterrence device. "
            "Specify pattern, intensity, colors, and duration. "
            "Or use a saved profile name."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Device identifier"},
                "profile": {
                    "type": "string",
                    "description": "Name of saved profile to activate (alternative to manual config)",
                },
                "siren_pattern": {
                    "type": "string",
                    "description": 'Siren pattern (e.g. "Alarm: Horror", "Alarm: Car alarm")',
                },
                "siren_intensity": {
                    "type": "integer",
                    "description": "Siren intensity (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
                "light_pattern": {
                    "type": "string",
                    "description": 'Light pattern (e.g. "Alternate", "Pulse", "Solid")',
                },
                "light_colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Light colors (e.g. ["red", "blue"])',
                },
                "light_intensity": {
                    "type": "integer",
                    "description": "Light intensity (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds",
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="stop_siren",
        description="Stop all active sirens and lights on a deterrence device.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Device identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    # --- Edge Storage tools ---
    Tool(
        name="get_disk_status",
        description=(
            "Get storage disk status for a camera — SD card and network share info "
            "including total size, free space, health, filesystem, and lock status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="list_recordings",
        description=(
            "List recordings stored on the camera's edge storage (SD card or network share). "
            "Can filter by time range. Returns recording IDs, timestamps, and video/audio info."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "disk_id": {
                    "type": "string",
                    "description": 'Disk ID to filter (e.g. "SD_DISK", "NetworkShare"). Omit for all.',
                },
                "start_time": {
                    "type": "string",
                    "description": 'Filter start time in ISO 8601 UTC (e.g. "2024-01-15T08:00:00Z")',
                },
                "stop_time": {
                    "type": "string",
                    "description": 'Filter stop time in ISO 8601 UTC',
                },
                "max_recordings": {
                    "type": "integer",
                    "description": "Maximum number of recordings to return",
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="get_recording_info",
        description=(
            "Get export properties for a specific recording — "
            "estimated file size, exact start/stop times, export format. "
            "Use before deciding whether to export."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "recording_id": {
                    "type": "string",
                    "description": "Recording ID from list_recordings",
                },
                "disk_id": {
                    "type": "string",
                    "description": "Disk ID where the recording is stored",
                },
                "start_time": {
                    "type": "string",
                    "description": "Optional clip start time (ISO 8601 UTC)",
                },
                "stop_time": {
                    "type": "string",
                    "description": "Optional clip stop time",
                },
            },
            "required": ["camera_id", "recording_id", "disk_id"],
        },
    ),
    # --- Clear View tools ---
    Tool(
        name="get_clear_view_info",
        description=(
            "Get Clear View service info — available cleaning services "
            "(wiper, speed-dry), duration limits, and cooldown times. "
            "Only available on cameras with wiper/speed-dry hardware."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="start_clear_view",
        description=(
            "Activate the camera's wiper or speed-dry function to clean "
            "the lens. Optional duration in seconds."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "service_id": {
                    "type": "integer",
                    "description": "Service ID from get_clear_view_info (default 0 = wiper)",
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds (within min/max from service info)",
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="stop_clear_view",
        description="Stop a running wiper/speed-dry operation (if stoppable).",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "service_id": {
                    "type": "integer",
                    "description": "Service ID to stop (default 0 = wiper)",
                },
            },
            "required": ["camera_id"],
        },
    ),
    # --- Privacy Mask tools ---
    Tool(
        name="list_privacy_masks",
        description=(
            "List all privacy masks on a camera with their pixel coordinates, "
            "names, enabled status, and zoom visibility."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="add_privacy_mask",
        description=(
            "Add a privacy mask to cover a sensitive area in the video. "
            "Specify position as width/height in percent (with optional center), "
            "or as a pixel polygon. Masks adapt to PTZ changes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "name": {
                    "type": "string",
                    "description": "Unique mask name (max 128 chars)",
                },
                "width": {
                    "type": "number",
                    "description": "Mask width as percent of image width (0.0–100.0)",
                },
                "height": {
                    "type": "number",
                    "description": "Mask height as percent of image height (0.0–100.0)",
                },
                "center_x": {
                    "type": "number",
                    "description": "Center X position as percent of image width (default: center)",
                },
                "center_y": {
                    "type": "number",
                    "description": "Center Y position as percent of image height (default: center)",
                },
                "polygon": {
                    "type": "string",
                    "description": 'Pixel polygon "x1,y1:x2,y2:x3,y3" in max resolution (alternative to width/height)',
                },
            },
            "required": ["camera_id", "name"],
        },
    ),
    Tool(
        name="remove_privacy_mask",
        description="Remove a privacy mask by name.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "name": {"type": "string", "description": "Name of the mask to remove"},
            },
            "required": ["camera_id", "name"],
        },
    ),
    # --- Recording Export ---
    Tool(
        name="export_recording",
        description=(
            "Export a recording from the camera's edge storage as a .mkv file. "
            "Downloads to the server's /exports/ directory. Use list_recordings first "
            "to find recording IDs, and get_recording_info to check file size."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "recording_id": {
                    "type": "string",
                    "description": "Recording ID from list_recordings",
                },
                "disk_id": {
                    "type": "string",
                    "description": "Disk ID where the recording is stored",
                },
                "start_time": {
                    "type": "string",
                    "description": "Optional clip start time (ISO 8601 UTC)",
                },
                "stop_time": {
                    "type": "string",
                    "description": "Optional clip stop time",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (default: recording_id.mkv)",
                },
            },
            "required": ["camera_id", "recording_id", "disk_id"],
        },
    ),
    # --- Time API ---
    Tool(
        name="get_time_info",
        description=(
            "Get the camera's current date/time, timezone, and DST status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_timezone",
        description=(
            "Set the camera's timezone using an IANA timezone name "
            '(e.g. "Europe/Stockholm", "America/New_York", "Asia/Tokyo").'
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "timezone": {
                    "type": "string",
                    "description": 'IANA timezone name (e.g. "Europe/Stockholm")',
                },
            },
            "required": ["camera_id", "timezone"],
        },
    ),
    # --- Day/Night ---
    Tool(
        name="get_daynight_config",
        description=(
            "Get the day/night (IR-cut filter) configuration for a camera — "
            "shift levels, dwell times, auto-tune, and IR-pass filter settings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "channel": {
                    "type": "integer",
                    "description": "Video channel (default 0)",
                    "default": 0,
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_daynight_config",
        description=(
            "Configure day/night switching behavior — thresholds for switching "
            "between day mode (color) and night mode (IR/B&W)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "channel": {
                    "type": "integer",
                    "description": "Video channel (default 0)",
                    "default": 0,
                },
                "DayNightShiftLevel": {
                    "type": "integer",
                    "description": "Day→Night threshold (0-100, higher = darker before switching)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "NightDayShiftLevel": {
                    "type": "integer",
                    "description": "Night→Day threshold (0-100)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "DayNightDwellTime": {
                    "type": "integer",
                    "description": "Seconds to wait before day→night switch (1-600)",
                    "minimum": 1,
                    "maximum": 600,
                },
                "NightDayDwellTime": {
                    "type": "integer",
                    "description": "Seconds to wait before night→day switch (1-600)",
                    "minimum": 1,
                    "maximum": 600,
                },
                "Autotune": {
                    "type": "boolean",
                    "description": "Enable auto-tuning of shift levels",
                },
                "NightFilter": {
                    "type": "string",
                    "enum": ["irpass", "clear"],
                    "description": "Night filter mode: 'irpass' for IR, 'clear' for visible light",
                },
            },
            "required": ["camera_id"],
        },
    ),
    # --- Stream Profiles ---
    Tool(
        name="list_stream_profiles",
        description=(
            "List video stream profiles — preset configurations for resolution, "
            "codec, FPS, and other streaming parameters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "name": {
                    "type": "string",
                    "description": "Specific profile name to query (omit for all)",
                },
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="create_stream_profile",
        description=(
            "Create a new video stream profile with specified parameters. "
            "Parameters are URL-encoded (e.g. 'resolution=1920x1080&fps=30&videocodec=h264')."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "name": {
                    "type": "string",
                    "description": "Unique profile name",
                },
                "parameters": {
                    "type": "string",
                    "description": "URL-encoded parameter string (e.g. 'resolution=1920x1080&fps=30')",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description",
                    "default": "",
                },
            },
            "required": ["camera_id", "name", "parameters"],
        },
    ),
    Tool(
        name="remove_stream_profile",
        description="Remove a video stream profile by name.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "name": {
                    "type": "string",
                    "description": "Name of the profile to remove",
                },
            },
            "required": ["camera_id", "name"],
        },
    ),
    # --- Geolocation ---
    Tool(
        name="get_geolocation",
        description=(
            "Get the camera's configured GPS coordinates (latitude, longitude), "
            "compass heading, and location description text."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_geolocation",
        description=(
            "Set the camera's GPS coordinates and heading. "
            "Coordinates are WGS-84 decimal degrees."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "lat": {
                    "type": "number",
                    "description": "Latitude in decimal degrees",
                },
                "lng": {
                    "type": "number",
                    "description": "Longitude in decimal degrees",
                },
                "heading": {
                    "type": "number",
                    "description": "Compass heading in degrees (0-360)",
                },
                "text": {
                    "type": "string",
                    "description": "Location description text",
                },
            },
            "required": ["camera_id"],
        },
    ),
    # --- Audio Control ---
    Tool(
        name="get_audio_settings",
        description=(
            "Get audio device settings — input/output configuration, "
            "gain levels, mute status, and connection types."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_audio_settings",
        description=(
            "Update audio device settings — change gain, mute, "
            "or input source. Pass the devices array from get_audio_settings "
            "with modifications."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "devices": {
                    "type": "array",
                    "description": "Array of device settings (structure from get_audio_settings)",
                },
            },
            "required": ["camera_id", "devices"],
        },
    ),
    # --- Event Polling ---
    Tool(
        name="poll_events",
        description=(
            "Poll for camera events over WebSocket for a specified duration. "
            "Returns a batch of events (motion, I/O changes, tampering, etc.). "
            "Useful for checking what's happening on a camera right now."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "duration": {
                    "type": "number",
                    "description": "How long to listen for events in seconds (1-30, default 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 30,
                },
                "topic_filter": {
                    "type": "string",
                    "description": (
                        'Optional ONVIF topic filter (e.g. '
                        '"tns1:Device/tnsaxis:IO/VirtualPort", '
                        '"tns1:RuleEngine/MotionRegionDetector/Motion")'
                    ),
                },
            },
            "required": ["camera_id"],
        },
    ),
    # --- Capture Mode ---
    Tool(
        name="get_capture_modes",
        description=(
            "List available video capture modes (resolution + max FPS) "
            "for a camera. Shows which mode is currently active."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_capture_mode",
        description=(
            "Switch a camera to a different capture mode (resolution/FPS). "
            "WARNING: Requires camera reboot to take effect."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "channel": {
                    "type": "integer",
                    "description": "Video channel (default 0)",
                    "default": 0,
                },
                "capture_mode_id": {
                    "type": "integer",
                    "description": "Capture mode ID from get_capture_modes",
                },
            },
            "required": ["camera_id", "capture_mode_id"],
        },
    ),
    # --- Orientation Sensor ---
    Tool(
        name="get_orientation",
        description=(
            "Read the camera's physical orientation from its built-in sensor "
            "(accelerometer/gyroscope). Returns longitudinal rotation and "
            "lateral tilt angles. Not all cameras have this hardware."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    # --- NTP ---
    Tool(
        name="get_ntp_status",
        description=(
            "Get NTP time synchronization status — whether NTP is enabled, "
            "sync status, configured servers, time offset, and next sync time."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_ntp_config",
        description=(
            "Configure NTP time synchronization — enable/disable, set server "
            "source (static or DHCP), and configure NTP server addresses."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "enabled": {
                    "type": "boolean",
                    "description": "Enable or disable NTP client",
                },
                "servers_source": {
                    "type": "string",
                    "enum": ["static", "DHCP"],
                    "description": "Source of NTP servers",
                },
                "static_servers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of NTP server addresses (overwrites existing)",
                },
            },
            "required": ["camera_id"],
        },
    ),
    # --- Analytics Metadata ---
    Tool(
        name="list_analytics_producers",
        description=(
            "List analytics metadata producers (object detection, motion, etc.) "
            "and whether they are enabled per video channel."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="set_analytics_producers",
        description=(
            "Enable or disable specific analytics metadata producers per "
            "video channel. Pass the producers array with name and channel settings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "producers": {
                    "type": "array",
                    "description": (
                        "List of producers to configure. Each: "
                        '{name: "producer_name", videochannels: [{channel: 0, enabled: true}]}'
                    ),
                },
            },
            "required": ["camera_id", "producers"],
        },
    ),
    # --- Stream Status ---
    Tool(
        name="get_stream_status",
        description=(
            "Get real-time stream diagnostics for a camera — active client count, "
            "bitrate (kbps), FPS, resolution, and codec for each stream. "
            "Returns an empty list when no streams are active."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    # --- MQTT ---
    Tool(
        name="get_mqtt_config",
        description=(
            "Get MQTT client configuration and connection status — broker address, "
            "port, client ID, connection state, and event publication settings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="configure_mqtt",
        description=(
            "Configure the MQTT client connection on a camera. Once configured and enabled, "
            "the camera publishes events directly to the broker — no MCP involvement at runtime."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
                "host": {"type": "string", "description": "MQTT broker hostname or IP"},
                "port": {"type": "integer", "description": "Broker port (default 1883)", "default": 1883},
                "protocol": {"type": "string", "description": "Protocol: tcp, ssl, ws, wss", "default": "tcp"},
                "client_id": {"type": "string", "description": "Optional MQTT client ID"},
                "username": {"type": "string", "description": "Optional broker username"},
                "password": {"type": "string", "description": "Optional broker password"},
            },
            "required": ["camera_id", "host"],
        },
    ),
    Tool(
        name="enable_mqtt",
        description="Enable (activate) the MQTT client on a camera — connects to the configured broker.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    Tool(
        name="disable_mqtt",
        description="Disable (deactivate) the MQTT client on a camera — disconnects from the broker.",
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    # --- Temperature ---
    Tool(
        name="get_temperature",
        description=(
            "Read temperature sensors (CPU, main board, lens, etc.) and heater status "
            "from a camera. Returns readings in both Celsius and Fahrenheit."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera identifier"},
            },
            "required": ["camera_id"],
        },
    ),
    # --- Multi-camera batch tools ---
    Tool(
        name="snapshot_all",
        description=(
            "Capture a JPEG snapshot from every configured camera simultaneously. "
            "Returns images from all reachable cameras. Useful for a quick overview."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "resolution": {
                    "type": "string",
                    "description": 'Image resolution (e.g. "1280x720"). Default: "640x480" for batch.',
                    "default": "640x480",
                },
            },
        },
    ),
    Tool(
        name="status_all",
        description=(
            "Get a quick status summary of all configured cameras — "
            "model, firmware, online/offline, and key capabilities."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------
@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return the list of available VAPIX tools."""
    return TOOLS


# ---------------------------------------------------------------------------
# MCP Resource handlers — live camera snapshots
# ---------------------------------------------------------------------------
@app.list_resources()
async def handle_list_resources() -> list[Resource]:
    """Expose each camera's live snapshot as a readable resource."""
    cfg = _get_config()
    resources = []
    for cam in cfg.cameras:
        if "snapshot" in cam.capabilities:
            resources.append(
                Resource(
                    uri=AnyUrl(f"camera://{cam.id}/snapshot"),
                    name=f"{cam.name} — Live Snapshot",
                    description=f"Current JPEG snapshot from {cam.name} ({cam.host})",
                    mimeType="image/jpeg",
                )
            )
        resources.append(
            Resource(
                uri=AnyUrl(f"camera://{cam.id}/info"),
                name=f"{cam.name} — Device Info",
                description=f"Device information for {cam.name}",
                mimeType="application/json",
            )
        )
    return resources


@app.read_resource()
async def handle_read_resource(uri: AnyUrl) -> list[BlobResourceContents]:
    """Read a camera resource by URI."""
    uri_str = str(uri)
    if not uri_str.startswith("camera://"):
        raise ValueError(f"Unknown resource URI scheme: {uri_str}")

    # Parse camera://camera_id/resource_type
    parts = uri_str.replace("camera://", "").split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid resource URI: {uri_str}")

    camera_id, resource_type = parts
    camera, client = _resolve_camera(camera_id)

    if resource_type == "snapshot":
        _check_capability(camera, "snapshot")
        jpeg_bytes = await imaging.get_snapshot(client, resolution="1920x1080")
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        return [BlobResourceContents(
            uri=uri,
            mimeType="image/jpeg",
            blob=b64,
        )]
    elif resource_type == "info":
        props = await device.get_all_properties(client)
        from mcp.types import TextResourceContents
        return [TextResourceContents(
            uri=uri,
            mimeType="application/json",
            text=json.dumps(props, ensure_ascii=False, indent=2),
        )]
    else:
        raise ValueError(f"Unknown resource type: {resource_type}")


@app.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[TextContent | ImageContent]:
    """
    Route MCP tool calls to the appropriate VAPIX handler.

    Each handler validates the camera_id, checks capabilities,
    calls the VAPIX API, and returns structured results.
    """
    try:
        return await _dispatch_tool(name, arguments)
    except ValueError as e:
        return _error_result(str(e))
    except VapixError as e:
        return _error_result(f"Camera API error {e.code}: {e.message}")
    except Exception as e:
        logger.exception("Unexpected error in tool %s", name)
        return _error_result(f"Unexpected error: {type(e).__name__}: {e}")


async def _dispatch_tool(
    name: str, args: dict[str, Any]
) -> list[TextContent | ImageContent]:
    """Dispatch a tool call to its handler. Separated for testability."""

    # --- Global tools (no camera_id needed) ---
    if name in _GLOBAL_HANDLERS:
        return await _GLOBAL_HANDLERS[name](args)

    # --- All other tools require camera_id ---
    camera_id = args.get("camera_id")
    if not camera_id:
        raise ValueError("camera_id is required")

    camera, client = _resolve_camera(camera_id)

    if name not in _CAMERA_HANDLERS:
        raise ValueError(f"Unknown tool: {name}")

    capability, handler = _CAMERA_HANDLERS[name]
    if capability:
        _check_capability(camera, capability)

    return await handler(camera, client, args)


# ---------------------------------------------------------------------------
# Global tool handlers (no camera_id)
# ---------------------------------------------------------------------------
async def _h_list_cameras(args: dict) -> list[TextContent]:
    cfg = _get_config()
    return _text_result([
        {"id": c.id, "name": c.name, "host": c.host, "capabilities": c.capabilities}
        for c in cfg.cameras
    ])


async def _h_snapshot_all(args: dict) -> list[TextContent | ImageContent]:
    cfg = _get_config()
    resolution = args.get("resolution", "640x480")
    results: list[TextContent | ImageContent] = []
    for cam in cfg.cameras:
        if "snapshot" not in cam.capabilities:
            continue
        try:
            c = _get_client(cam)
            jpeg_bytes = await imaging.get_snapshot(c, resolution=resolution)
            b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            results.append(TextContent(type="text", text=f"--- {cam.name} ({cam.id}) ---"))
            results.append(ImageContent(type="image", data=b64, mimeType="image/jpeg"))
        except Exception as e:
            results.append(TextContent(type="text", text=f"--- {cam.name} ({cam.id}): Error: {e} ---"))
    return results or _text_result("No cameras with snapshot capability configured")


async def _h_status_all(args: dict) -> list[TextContent]:
    cfg = _get_config()
    statuses = []
    for cam in cfg.cameras:
        status: dict[str, Any] = {
            "id": cam.id, "name": cam.name, "host": cam.host,
            "capabilities": cam.capabilities,
        }
        try:
            c = _get_client(cam)
            props = await device.get_all_properties(c)
            status.update(online=True, model=props.get("ProdNbr", "unknown"),
                          firmware=props.get("Version", "unknown"),
                          serial=props.get("SerialNumber", "unknown"))
        except Exception as e:
            status.update(online=False, error=str(e))
        statuses.append(status)
    return _text_result(statuses)


_GLOBAL_HANDLERS: dict[str, Any] = {
    "list_cameras": _h_list_cameras,
    "snapshot_all": _h_snapshot_all,
    "status_all": _h_status_all,
}


# ---------------------------------------------------------------------------
# Camera tool handlers (camera_id required)
# Each handler signature: async (camera, client, args) -> list[Content]
# ---------------------------------------------------------------------------
async def _h_get_camera_info(cam, client, args):
    return _text_result(await device.get_all_properties(client))


async def _h_get_snapshot(cam, client, args):
    resolution = args.get("resolution", "1920x1080")
    jpeg_bytes = await imaging.get_snapshot(client, resolution=resolution)
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return [ImageContent(type="image", data=b64, mimeType="image/jpeg")]


async def _h_ptz_move(cam, client, args):
    await ptz.move_absolute(client, pan=args["pan"], tilt=args["tilt"], zoom=args["zoom"])
    return _text_result(f"Moved {cam.name} to pan={args['pan']}, tilt={args['tilt']}, zoom={args['zoom']}")


async def _h_ptz_relative(cam, client, args):
    await ptz.move_relative(client, rpan=args.get("rpan", 0), rtilt=args.get("rtilt", 0), rzoom=args.get("rzoom", 0))
    return _text_result(f"Moved {cam.name} by relative offset")


async def _h_ptz_home(cam, client, args):
    await ptz.go_home(client)
    return _text_result(f"Sent {cam.name} to home position")


async def _h_ptz_preset(cam, client, args):
    preset = args["preset_name"]
    await ptz.go_to_preset(client, preset)
    return _text_result(f"Sent {cam.name} to preset '{preset}'")


async def _h_ptz_status(cam, client, args):
    return _text_result(await ptz.get_position(client))


async def _h_get_io_ports(cam, client, args):
    return _text_result(await io_ports.get_ports(client))


async def _h_set_io_port(cam, client, args):
    await io_ports.set_port_state(client, port=args["port"], state=args["state"])
    return _text_result(f"Set port {args['port']} on {cam.name} to '{args['state']}'")


async def _h_get_lights(cam, client, args):
    return _text_result(await light.get_light_information(client))


async def _h_toggle_light(cam, client, args):
    light_id, on = args["light_id"], args["on"]
    if on:
        await light.activate_light(client, light_id)
        return _text_result(f"Activated light '{light_id}' on {cam.name}")
    await light.deactivate_light(client, light_id)
    return _text_result(f"Deactivated light '{light_id}' on {cam.name}")


async def _h_discover_apis(cam, client, args):
    return _text_result(await discovery.get_api_list(client))


async def _h_list_overlays(cam, client, args):
    return _text_result(await overlay.list_overlays(client))


async def _h_add_overlay(cam, client, args):
    identity = await overlay.add_text(
        client, text=args["text"], position=args.get("position", "topLeft"),
        text_color=args.get("text_color", "white"), text_bg_color=args.get("text_bg_color", "transparent"),
    )
    return _text_result(f"Added text overlay on {cam.name} (identity={identity})")


async def _h_remove_overlay(cam, client, args):
    await overlay.remove_overlay(client, identity=args["identity"])
    return _text_result(f"Removed overlay {args['identity']} from {cam.name}")


async def _h_get_motion_config(cam, client, args):
    return _text_result(await vmd.get_configuration(client))


async def _h_set_motion_config(cam, client, args):
    await vmd.set_configuration(client, cameras=args["cameras"], profiles=args["profiles"])
    return _text_result(f"Updated motion detection configuration on {cam.name}")


async def _h_list_guard_tours(cam, client, args):
    return _text_result(await guard_tour.list_tours(client))


async def _h_start_guard_tour(cam, client, args):
    await guard_tour.start_tour(client, tour_id=args["tour_id"])
    return _text_result(f"Started guard tour {args['tour_id']} on {cam.name}")


async def _h_stop_guard_tour(cam, client, args):
    await guard_tour.stop_tour(client, tour_id=args["tour_id"])
    return _text_result(f"Stopped guard tour {args['tour_id']} on {cam.name}")


async def _h_get_siren_status(cam, client, args):
    return _text_result(await siren.get_status(client))


async def _h_activate_siren(cam, client, args):
    profile_name = args.get("profile")
    if profile_name:
        result = await siren.start(client, profile=profile_name)
    else:
        siren_config = None
        light_config = None
        if args.get("siren_pattern"):
            siren_config = {"pattern": args["siren_pattern"]}
            if args.get("siren_intensity"):
                siren_config["intensity"] = args["siren_intensity"]
        if args.get("light_pattern"):
            light_config = {"pattern": args["light_pattern"], "speed": 1}
            if args.get("light_colors"):
                light_config["colors"] = args["light_colors"]
            if args.get("light_intensity"):
                light_config["intensity"] = args["light_intensity"]
        result = await siren.start(client, siren=siren_config, light=light_config, duration=args.get("duration"))
    return _text_result(f"Activated siren/light on {cam.name}: {result}")


async def _h_stop_siren(cam, client, args):
    await siren.stop(client)
    return _text_result(f"Stopped siren and light on {cam.name}")


async def _h_get_disk_status(cam, client, args):
    return _text_result(await storage.list_disks(client))


async def _h_list_recordings(cam, client, args):
    return _text_result(await storage.list_recordings(
        client, disk_id=args.get("disk_id"), start_time=args.get("start_time"),
        stop_time=args.get("stop_time"), max_recordings=args.get("max_recordings"),
    ))


async def _h_get_recording_info(cam, client, args):
    return _text_result(await storage.get_export_properties(
        client, recording_id=args["recording_id"], disk_id=args["disk_id"],
        start_time=args.get("start_time"), stop_time=args.get("stop_time"),
    ))


async def _h_export_recording(cam, client, args):
    filename = args.get("filename") or f"{args['recording_id']}.mkv"
    exports_dir = os.environ.get("VAPIX_EXPORTS_DIR", "/exports")
    return _text_result(await storage.export_recording(
        client, recording_id=args["recording_id"], disk_id=args["disk_id"],
        output_path=f"{exports_dir}/{filename}",
        start_time=args.get("start_time"), stop_time=args.get("stop_time"),
    ))


async def _h_get_clear_view_info(cam, client, args):
    return _text_result(await clear_view.get_service_info(client))


async def _h_start_clear_view(cam, client, args):
    sid, dur = args.get("service_id", 0), args.get("duration")
    await clear_view.start(client, service_id=sid, duration=dur)
    return _text_result(f"Started Clear View service {sid} on {cam.name}" + (f" (duration={dur}s)" if dur else ""))


async def _h_stop_clear_view(cam, client, args):
    sid = args.get("service_id", 0)
    await clear_view.stop(client, service_id=sid)
    return _text_result(f"Stopped Clear View service {sid} on {cam.name}")


async def _h_list_privacy_masks(cam, client, args):
    return _text_result(await privacy_mask.list_masks(client))


async def _h_add_privacy_mask(cam, client, args):
    await privacy_mask.add_mask(
        client, name=args["name"], width=args.get("width"), height=args.get("height"),
        center_x=args.get("center_x"), center_y=args.get("center_y"), polygon=args.get("polygon"),
    )
    return _text_result(f"Added privacy mask '{args['name']}' on {cam.name}")


async def _h_remove_privacy_mask(cam, client, args):
    await privacy_mask.remove_mask(client, name=args["name"])
    return _text_result(f"Removed privacy mask '{args['name']}' from {cam.name}")


async def _h_get_time_info(cam, client, args):
    return _text_result(await time_service.get_date_time_info(client))


async def _h_set_timezone(cam, client, args):
    tz = args["timezone"]
    await time_service.set_timezone(client, tz)
    return _text_result(f"Set timezone on {cam.name} to '{tz}'")


async def _h_get_daynight_config(cam, client, args):
    return _text_result(await daynight.get_configuration(client, channel=args.get("channel", 0)))


async def _h_set_daynight_config(cam, client, args):
    channel = args.get("channel", 0)
    settings = {k: v for k, v in args.items() if k not in ("camera_id", "channel")}
    await daynight.set_configuration(client, channel=channel, **settings)
    return _text_result(f"Updated day/night configuration on {cam.name}")


async def _h_list_stream_profiles(cam, client, args):
    return _text_result(await stream_profiles.list_profiles(client, name=args.get("name")))


async def _h_create_stream_profile(cam, client, args):
    await stream_profiles.create_profile(client, name=args["name"], parameters=args["parameters"], description=args.get("description", ""))
    return _text_result(f"Created stream profile '{args['name']}' on {cam.name}")


async def _h_remove_stream_profile(cam, client, args):
    await stream_profiles.remove_profile(client, name=args["name"])
    return _text_result(f"Removed stream profile '{args['name']}' from {cam.name}")


async def _h_get_geolocation(cam, client, args):
    return _text_result(await geolocation.get_location(client))


async def _h_set_geolocation(cam, client, args):
    await geolocation.set_location(client, lat=args.get("lat"), lng=args.get("lng"), heading=args.get("heading"), text=args.get("text"))
    return _text_result(f"Updated geolocation on {cam.name}")


async def _h_get_audio_settings(cam, client, args):
    return _text_result(await audio.get_settings(client))


async def _h_set_audio_settings(cam, client, args):
    await audio.set_settings(client, devices=args["devices"])
    return _text_result(f"Updated audio settings on {cam.name}")


async def _h_poll_events(cam, client, args):
    collected = await events.poll_events(client, duration_seconds=args.get("duration", 5), topic_filter=args.get("topic_filter"))
    return _text_result({"events_collected": len(collected), "events": collected})


async def _h_get_capture_modes(cam, client, args):
    return _text_result(await capture_mode.get_capture_modes(client))


async def _h_set_capture_mode(cam, client, args):
    channel = args.get("channel", 0)
    await capture_mode.set_capture_mode(client, channel=channel, capture_mode_id=args["capture_mode_id"])
    return _text_result(f"Capture mode set to {args['capture_mode_id']} on {cam.name} (channel {channel}). Camera reboot required.")


async def _h_get_orientation(cam, client, args):
    return _text_result(await orientation.get_orientation(client))


async def _h_get_ntp_status(cam, client, args):
    return _text_result(await ntp.get_ntp_info(client))


async def _h_set_ntp_config(cam, client, args):
    await ntp.set_ntp_config(client, enabled=args.get("enabled"), servers_source=args.get("servers_source"), static_servers=args.get("static_servers"))
    return _text_result(f"Updated NTP configuration on {cam.name}")


async def _h_list_analytics_producers(cam, client, args):
    return _text_result(await analytics_metadata.list_producers(client))


async def _h_set_analytics_producers(cam, client, args):
    await analytics_metadata.set_enabled_producers(client, producers=args["producers"])
    return _text_result(f"Updated analytics producers on {cam.name}")


async def _h_get_temperature(cam, client, args):
    return _text_result(await temperature.get_sensor_list(client))


async def _h_get_stream_status(cam, client, args):
    return _text_result(await stream_status.get_stream_status(client))


async def _h_get_mqtt_config(cam, client, args):
    status = await mqtt.get_client_status(client)
    events_cfg = await mqtt.get_event_publication_config(client)
    return _text_result({"client": status, "eventPublication": events_cfg})


async def _h_configure_mqtt(cam, client, args):
    await mqtt.configure_client(
        client,
        host=args["host"],
        port=args.get("port", 1883),
        protocol=args.get("protocol", "tcp"),
        client_id=args.get("client_id"),
        username=args.get("username"),
        password=args.get("password"),
    )
    return _text_result(f"Configured MQTT on {cam.name} → {args['host']}:{args.get('port', 1883)}")


async def _h_enable_mqtt(cam, client, args):
    await mqtt.activate_client(client)
    return _text_result(f"MQTT enabled on {cam.name}")


async def _h_disable_mqtt(cam, client, args):
    await mqtt.deactivate_client(client)
    return _text_result(f"MQTT disabled on {cam.name}")


# Handler registry: tool_name → (required_capability_or_None, handler_function)
_CAMERA_HANDLERS: dict[str, tuple[str | None, Any]] = {
    "get_camera_info": (None, _h_get_camera_info),
    "get_snapshot": ("snapshot", _h_get_snapshot),
    "ptz_move": ("ptz", _h_ptz_move),
    "ptz_relative": ("ptz", _h_ptz_relative),
    "ptz_home": ("ptz", _h_ptz_home),
    "ptz_preset": ("ptz", _h_ptz_preset),
    "ptz_status": ("ptz", _h_ptz_status),
    "get_io_ports": ("io", _h_get_io_ports),
    "set_io_port": ("io", _h_set_io_port),
    "get_lights": ("light", _h_get_lights),
    "toggle_light": ("light", _h_toggle_light),
    "discover_apis": (None, _h_discover_apis),
    "list_overlays": ("overlay", _h_list_overlays),
    "add_overlay": ("overlay", _h_add_overlay),
    "remove_overlay": ("overlay", _h_remove_overlay),
    "get_motion_config": ("vmd", _h_get_motion_config),
    "set_motion_config": ("vmd", _h_set_motion_config),
    "list_guard_tours": ("guard_tour", _h_list_guard_tours),
    "start_guard_tour": ("guard_tour", _h_start_guard_tour),
    "stop_guard_tour": ("guard_tour", _h_stop_guard_tour),
    "get_siren_status": ("siren", _h_get_siren_status),
    "activate_siren": ("siren", _h_activate_siren),
    "stop_siren": ("siren", _h_stop_siren),
    "get_disk_status": ("storage", _h_get_disk_status),
    "list_recordings": ("storage", _h_list_recordings),
    "get_recording_info": ("storage", _h_get_recording_info),
    "export_recording": ("storage", _h_export_recording),
    "get_clear_view_info": ("clear_view", _h_get_clear_view_info),
    "start_clear_view": ("clear_view", _h_start_clear_view),
    "stop_clear_view": ("clear_view", _h_stop_clear_view),
    "list_privacy_masks": ("privacy_mask", _h_list_privacy_masks),
    "add_privacy_mask": ("privacy_mask", _h_add_privacy_mask),
    "remove_privacy_mask": ("privacy_mask", _h_remove_privacy_mask),
    "get_time_info": ("time", _h_get_time_info),
    "set_timezone": ("time", _h_set_timezone),
    "get_daynight_config": ("daynight", _h_get_daynight_config),
    "set_daynight_config": ("daynight", _h_set_daynight_config),
    "list_stream_profiles": ("stream_profiles", _h_list_stream_profiles),
    "create_stream_profile": ("stream_profiles", _h_create_stream_profile),
    "remove_stream_profile": ("stream_profiles", _h_remove_stream_profile),
    "get_geolocation": ("geolocation", _h_get_geolocation),
    "set_geolocation": ("geolocation", _h_set_geolocation),
    "get_audio_settings": ("audio", _h_get_audio_settings),
    "set_audio_settings": ("audio", _h_set_audio_settings),
    "poll_events": ("events", _h_poll_events),
    "get_capture_modes": ("capture_mode", _h_get_capture_modes),
    "set_capture_mode": ("capture_mode", _h_set_capture_mode),
    "get_orientation": ("orientation", _h_get_orientation),
    "get_ntp_status": ("time", _h_get_ntp_status),
    "set_ntp_config": ("time", _h_set_ntp_config),
    "list_analytics_producers": ("analytics_metadata", _h_list_analytics_producers),
    "set_analytics_producers": ("analytics_metadata", _h_set_analytics_producers),
    "get_temperature": ("temperature", _h_get_temperature),
    "get_stream_status": ("stream_status", _h_get_stream_status),
    "get_mqtt_config": ("mqtt", _h_get_mqtt_config),
    "configure_mqtt": ("mqtt", _h_configure_mqtt),
    "enable_mqtt": ("mqtt", _h_enable_mqtt),
    "disable_mqtt": ("mqtt", _h_disable_mqtt),
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def main():
    """Run the VPX MCP server."""
    parser = argparse.ArgumentParser(description="VPX MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port for SSE/streamable-http transport (default: 8080)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to cameras.yaml config file",
    )
    args = parser.parse_args()

    # Pre-load config to fail fast on startup
    global config
    config = load_config(args.config)
    logger.info(
        "Loaded %d camera(s): %s",
        len(config.cameras),
        ", ".join(f"{c.id} ({c.name})" for c in config.cameras),
    )

    # Auto-detect capabilities for cameras with "auto" or no explicit capabilities
    for cam in config.cameras:
        if "auto" in cam.capabilities or cam.capabilities == ["snapshot"]:
            await _auto_detect_capabilities(cam)

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    elif args.transport == "sse":
        import uvicorn
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0],
                    streams[1],
                    app.create_initialization_options(),
                )

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages", app=sse.handle_post_message),
            ],
        )
        uv_config = uvicorn.Config(starlette_app, host="0.0.0.0", port=args.port)
        server = uvicorn.Server(uv_config)
        await server.serve()

    elif args.transport == "streamable-http":
        import uvicorn
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount

        transport = StreamableHTTPServerTransport(
            mcp_endpoint="/mcp",
            is_json=True,
        )

        async def handle_mcp(scope, receive, send):
            async with transport.connect(scope, receive, send) as streams:
                await app.run(
                    streams[0],
                    streams[1],
                    app.create_initialization_options(),
                )

        starlette_app = Starlette(
            routes=[
                Mount("/mcp", app=handle_mcp),
            ],
        )
        uv_config = uvicorn.Config(starlette_app, host="0.0.0.0", port=args.port)
        server = uvicorn.Server(uv_config)
        await server.serve()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
