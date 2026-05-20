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
import sys
from typing import Any

from mcp.server import Server
from mcp.types import (
    ImageContent,
    TextContent,
    Tool,
)

from config import AppConfig, CameraConfig, load_config
from vapix.client import VapixClient, VapixError
from vapix import device, imaging, ptz, io_ports, light, discovery, overlay, vmd, guard_tour, siren, storage, clear_view, privacy_mask

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
]


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------
@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return the list of available VAPIX tools."""
    return TOOLS


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

    # --- list_cameras (no camera_id needed) ---
    if name == "list_cameras":
        cfg = _get_config()
        cameras_info = [
            {
                "id": cam.id,
                "name": cam.name,
                "host": cam.host,
                "capabilities": cam.capabilities,
            }
            for cam in cfg.cameras
        ]
        return _text_result(cameras_info)

    # --- All other tools require camera_id ---
    camera_id = args.get("camera_id")
    if not camera_id:
        raise ValueError("camera_id is required")

    camera, client = _resolve_camera(camera_id)

    # --- get_camera_info ---
    if name == "get_camera_info":
        props = await device.get_all_properties(client)
        return _text_result(props)

    # --- get_snapshot ---
    if name == "get_snapshot":
        _check_capability(camera, "snapshot")
        resolution = args.get("resolution", "1920x1080")
        jpeg_bytes = await imaging.get_snapshot(client, resolution=resolution)
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        return [ImageContent(type="image", data=b64, mimeType="image/jpeg")]

    # --- PTZ tools ---
    if name == "ptz_move":
        _check_capability(camera, "ptz")
        result = await ptz.move_absolute(
            client,
            pan=args["pan"],
            tilt=args["tilt"],
            zoom=args["zoom"],
        )
        return _text_result(f"Moved {camera.name} to pan={args['pan']}, tilt={args['tilt']}, zoom={args['zoom']}")

    if name == "ptz_relative":
        _check_capability(camera, "ptz")
        result = await ptz.move_relative(
            client,
            rpan=args.get("rpan", 0),
            rtilt=args.get("rtilt", 0),
            rzoom=args.get("rzoom", 0),
        )
        return _text_result(f"Moved {camera.name} by relative offset")

    if name == "ptz_home":
        _check_capability(camera, "ptz")
        await ptz.go_home(client)
        return _text_result(f"Sent {camera.name} to home position")

    if name == "ptz_preset":
        _check_capability(camera, "ptz")
        preset = args["preset_name"]
        await ptz.go_to_preset(client, preset)
        return _text_result(f"Sent {camera.name} to preset '{preset}'")

    if name == "ptz_status":
        _check_capability(camera, "ptz")
        position = await ptz.get_position(client)
        return _text_result(position)

    # --- I/O port tools ---
    if name == "get_io_ports":
        _check_capability(camera, "io")
        ports = await io_ports.get_ports(client)
        return _text_result(ports)

    if name == "set_io_port":
        _check_capability(camera, "io")
        result = await io_ports.set_port_state(
            client, port=args["port"], state=args["state"]
        )
        return _text_result(
            f"Set port {args['port']} on {camera.name} to '{args['state']}'"
        )

    # --- Light tools ---
    if name == "get_lights":
        _check_capability(camera, "light")
        lights = await light.get_light_information(client)
        return _text_result(lights)

    if name == "toggle_light":
        _check_capability(camera, "light")
        light_id = args["light_id"]
        on = args["on"]
        if on:
            await light.activate_light(client, light_id)
            return _text_result(f"Activated light '{light_id}' on {camera.name}")
        else:
            await light.deactivate_light(client, light_id)
            return _text_result(f"Deactivated light '{light_id}' on {camera.name}")

    # --- API Discovery ---
    if name == "discover_apis":
        apis = await discovery.get_api_list(client)
        return _text_result(apis)

    # --- Overlay tools ---
    if name == "list_overlays":
        _check_capability(camera, "overlay")
        result = await overlay.list_overlays(client)
        return _text_result(result)

    if name == "add_overlay":
        _check_capability(camera, "overlay")
        identity = await overlay.add_text(
            client,
            text=args["text"],
            position=args.get("position", "topLeft"),
            text_color=args.get("text_color", "white"),
            text_bg_color=args.get("text_bg_color", "transparent"),
        )
        return _text_result(f"Added text overlay on {camera.name} (identity={identity})")

    if name == "remove_overlay":
        _check_capability(camera, "overlay")
        await overlay.remove_overlay(client, identity=args["identity"])
        return _text_result(f"Removed overlay {args['identity']} from {camera.name}")

    # --- Motion Detection tools ---
    if name == "get_motion_config":
        _check_capability(camera, "vmd")
        config_data = await vmd.get_configuration(client)
        return _text_result(config_data)

    if name == "set_motion_config":
        _check_capability(camera, "vmd")
        await vmd.set_configuration(
            client,
            cameras=args["cameras"],
            profiles=args["profiles"],
        )
        return _text_result(f"Updated motion detection configuration on {camera.name}")

    # --- Guard Tour tools ---
    if name == "list_guard_tours":
        _check_capability(camera, "guard_tour")
        tours = await guard_tour.list_tours(client)
        return _text_result(tours)

    if name == "start_guard_tour":
        _check_capability(camera, "guard_tour")
        await guard_tour.start_tour(client, tour_id=args["tour_id"])
        return _text_result(f"Started guard tour {args['tour_id']} on {camera.name}")

    if name == "stop_guard_tour":
        _check_capability(camera, "guard_tour")
        await guard_tour.stop_tour(client, tour_id=args["tour_id"])
        return _text_result(f"Stopped guard tour {args['tour_id']} on {camera.name}")

    # --- Siren & Light tools ---
    if name == "get_siren_status":
        _check_capability(camera, "siren")
        status = await siren.get_status(client)
        return _text_result(status)

    if name == "activate_siren":
        _check_capability(camera, "siren")
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
                light_config = {
                    "pattern": args["light_pattern"],
                    "speed": 1,
                }
                if args.get("light_colors"):
                    light_config["colors"] = args["light_colors"]
                if args.get("light_intensity"):
                    light_config["intensity"] = args["light_intensity"]
            result = await siren.start(
                client,
                siren=siren_config,
                light=light_config,
                duration=args.get("duration"),
            )
        return _text_result(f"Activated siren/light on {camera.name}: {result}")

    if name == "stop_siren":
        _check_capability(camera, "siren")
        await siren.stop(client)
        return _text_result(f"Stopped siren and light on {camera.name}")

    # --- Edge Storage tools ---
    if name == "get_disk_status":
        _check_capability(camera, "storage")
        disks = await storage.list_disks(client)
        return _text_result(disks)

    if name == "list_recordings":
        _check_capability(camera, "storage")
        recordings = await storage.list_recordings(
            client,
            disk_id=args.get("disk_id"),
            start_time=args.get("start_time"),
            stop_time=args.get("stop_time"),
            max_recordings=args.get("max_recordings"),
        )
        return _text_result(recordings)

    if name == "get_recording_info":
        _check_capability(camera, "storage")
        props = await storage.get_export_properties(
            client,
            recording_id=args["recording_id"],
            disk_id=args["disk_id"],
            start_time=args.get("start_time"),
            stop_time=args.get("stop_time"),
        )
        return _text_result(props)

    # --- Clear View tools ---
    if name == "get_clear_view_info":
        _check_capability(camera, "clear_view")
        services = await clear_view.get_service_info(client)
        return _text_result(services)

    if name == "start_clear_view":
        _check_capability(camera, "clear_view")
        service_id = args.get("service_id", 0)
        duration = args.get("duration")
        await clear_view.start(client, service_id=service_id, duration=duration)
        return _text_result(
            f"Started Clear View service {service_id} on {camera.name}"
            + (f" (duration={duration}s)" if duration else "")
        )

    if name == "stop_clear_view":
        _check_capability(camera, "clear_view")
        service_id = args.get("service_id", 0)
        await clear_view.stop(client, service_id=service_id)
        return _text_result(f"Stopped Clear View service {service_id} on {camera.name}")

    # --- Privacy Mask tools ---
    if name == "list_privacy_masks":
        _check_capability(camera, "privacy_mask")
        masks = await privacy_mask.list_masks(client)
        return _text_result(masks)

    if name == "add_privacy_mask":
        _check_capability(camera, "privacy_mask")
        await privacy_mask.add_mask(
            client,
            name=args["name"],
            width=args.get("width"),
            height=args.get("height"),
            center_x=args.get("center_x"),
            center_y=args.get("center_y"),
            polygon=args.get("polygon"),
        )
        return _text_result(f"Added privacy mask '{args['name']}' on {camera.name}")

    if name == "remove_privacy_mask":
        _check_capability(camera, "privacy_mask")
        await privacy_mask.remove_mask(client, name=args["name"])
        return _text_result(f"Removed privacy mask '{args['name']}' from {camera.name}")

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def main():
    """Run the VPX MCP server."""
    parser = argparse.ArgumentParser(description="VPX MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port for SSE transport (default: 8080)",
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

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    elif args.transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route
        import uvicorn

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
                Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
            ],
        )
        uvicorn.run(starlette_app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
