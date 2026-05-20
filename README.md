# VPX MCP Server

A **Model Context Protocol (MCP)** server that wraps **Axis camera VAPIX APIs**, enabling AI assistants (Claude, etc.) to control and query Axis network cameras directly.

Built to run in **Docker** for easy deployment.

> This is an independent hobby project and is not affiliated with, endorsed by, or sponsored by Axis Communications AB. VAPIX is a trademark of Axis Communications AB.

## Features

| Tool | Description | VAPIX Endpoint |
|------|-------------|----------------|
| `list_cameras` | List all configured cameras and capabilities | — (config) |
| `get_camera_info` | Device info: model, serial, firmware, etc. | `/axis-cgi/basicdeviceinfo.cgi` |
| `get_snapshot` | Capture a JPEG still image | `/axis-cgi/jpg/image.cgi` |
| `ptz_move` | Move to absolute pan/tilt/zoom position | `/axis-cgi/com/ptz.cgi` |
| `ptz_relative` | Move by relative offset | `/axis-cgi/com/ptz.cgi` |
| `ptz_home` | Return to home position | `/axis-cgi/com/ptz.cgi` |
| `ptz_preset` | Go to named preset | `/axis-cgi/com/ptz.cgi` |
| `ptz_status` | Get current PTZ position | `/axis-cgi/com/ptz.cgi` |
| `get_io_ports` | List I/O ports and states | `/axis-cgi/io/portmanagement.cgi` |
| `set_io_port` | Set output port state (open/closed) | `/axis-cgi/io/portmanagement.cgi` |
| `get_lights` | List lights (IR, white, indicator) | `/axis-cgi/lightcontrol.cgi` |
| `toggle_light` | Turn a light on or off | `/axis-cgi/lightcontrol.cgi` |
| `discover_apis` | List all VAPIX APIs a camera supports | `/axis-cgi/apidiscovery.cgi` |
| `list_overlays` | List dynamic text/image overlays | `/axis-cgi/dynamicoverlay/dynamicoverlay.cgi` |
| `add_overlay` | Add a text overlay to the video stream | `/axis-cgi/dynamicoverlay/dynamicoverlay.cgi` |
| `remove_overlay` | Remove an overlay by identity | `/axis-cgi/dynamicoverlay/dynamicoverlay.cgi` |
| `get_motion_config` | Get VMD4 motion detection zones/settings | `/local/vmd/control.cgi` |
| `set_motion_config` | Configure motion detection zones | `/local/vmd/control.cgi` |
| `list_guard_tours` | List PTZ guard tours | `/axis-cgi/param.cgi` |
| `start_guard_tour` | Start an automated PTZ patrol | `/axis-cgi/param.cgi` |
| `stop_guard_tour` | Stop a running guard tour | `/axis-cgi/param.cgi` |
| `get_siren_status` | Get siren/strobe device status | `/axis-cgi/siren_and_light.cgi` |
| `activate_siren` | Activate siren and/or strobe light | `/axis-cgi/siren_and_light.cgi` |
| `stop_siren` | Stop active siren and lights | `/axis-cgi/siren_and_light.cgi` |
| `get_disk_status` | SD card / storage disk status and health | `/axis-cgi/disks/list.cgi`, `/axis-cgi/disks/gethealth.cgi` |
| `list_recordings` | List edge storage recordings by time range | `/axis-cgi/record/list.cgi` |
| `get_recording_info` | Get recording export properties (size, times) | `/axis-cgi/record/export/properties.cgi` |
| `get_clear_view_info` | Available wiper/speed-dry services and limits | `/axis-cgi/clearviewcontrol.cgi` |
| `start_clear_view` | Activate wiper or speed-dry to clean the lens | `/axis-cgi/clearviewcontrol.cgi` |
| `stop_clear_view` | Stop a running cleaning operation | `/axis-cgi/clearviewcontrol.cgi` |
| `list_privacy_masks` | List all privacy masks with coordinates | `/axis-cgi/privacymask.cgi` |
| `add_privacy_mask` | Add a privacy mask (percent or pixel polygon) | `/axis-cgi/privacymask.cgi` |
| `remove_privacy_mask` | Remove a privacy mask by name | `/axis-cgi/privacymask.cgi` |

## Quick Start (Docker)

### 1. Configure cameras

```bash
cp cameras.example.yaml cameras.yaml
# Edit cameras.yaml with your camera details
```

### 2. Set passwords

```bash
cp .env.example .env
# Edit .env with your camera passwords
```

### 3. Build the Docker image

```bash
docker compose build
```

### 4. Use with an MCP client (stdio mode)

The MCP server communicates over **stdio** — the standard way MCP clients
(Claude Desktop, etc.) launch tool servers.

Add to your MCP client config (e.g. `~/.claude.json`):

```json
{
  "mcpServers": {
    "vpx": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--network=host",
        "-v", "/path/to/cameras.yaml:/app/cameras.yaml:ro",
        "--env-file", "/path/to/.env",
        "vpx-mcp"
      ]
    }
  }
}
```

> **`--network=host`** is required so the container can reach cameras on your local LAN.

### 5. Alternative: SSE/HTTP mode

For web-based access or debugging, run in SSE mode:

```bash
docker compose up vpx-sse
# Server available at http://localhost:8080/sse
```

## Project Structure

```
├── server.py              # MCP server entry point & tool definitions
├── config.py              # YAML config loading with env var substitution
├── vapix/
│   ├── client.py          # Base HTTP client (auth, requests, errors)
│   ├── device.py          # Basic Device Information API
│   ├── imaging.py         # JPEG snapshot capture
│   ├── ptz.py             # Pan/Tilt/Zoom control
│   ├── io_ports.py        # I/O port management
│   └── light.py           # Light control (IR/white LEDs)
├── tests/
│   ├── test_config.py     # Config loading & validation tests
│   ├── test_client.py     # HTTP client & auth tests
│   ├── test_vapix_apis.py # VAPIX API module tests
│   └── test_server.py     # MCP server integration tests
├── Dockerfile
├── docker-compose.yml
├── cameras.example.yaml   # Example camera config
├── .env.example            # Example environment variables
├── requirements.txt
└── spec.md                # Original implementation spec
```

## Configuration

### cameras.yaml

```yaml
cameras:
  - id: front-door           # Unique ID used in tool calls
    name: "Front Door"       # Human-readable name
    host: "192.168.1.100"    # IP or hostname (no http://)
    port: 443                # Default: 443 (HTTPS) or 80 (HTTP)
    https: true              # Use HTTPS (recommended)
    verify_ssl: false        # false for self-signed certs (typical for Axis)
    username: "root"
    password: "${FRONT_DOOR_PASS}"  # References .env variable
    capabilities:            # What this camera supports
      - snapshot
      - ptz
      - events
      - io
      - light
```

### Capabilities

Only declare capabilities your camera actually has:

| Capability | Required for |
|------------|-------------|
| `snapshot` | `get_snapshot` |
| `ptz` | `ptz_move`, `ptz_relative`, `ptz_home`, `ptz_preset`, `ptz_status` |
| `io` | `get_io_ports`, `set_io_port` |
| `light` | `get_lights`, `toggle_light` |

`get_camera_info` and `list_cameras` work regardless of capabilities.

## Authentication

The server follows [Axis VAPIX authentication guidelines](https://developer.axis.com/vapix/authentication/):

| Protocol | Auth Method | Why |
|----------|------------|-----|
| **HTTPS** | Basic auth | Encrypted channel protects credentials |
| **HTTP** | Digest auth | Credentials never sent in plaintext |

This is handled automatically based on the `https` setting in `cameras.yaml`.

## Running Without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Run in stdio mode
python server.py --config cameras.yaml

# Run in SSE mode
python server.py --transport sse --port 8080
```

## Running Tests

Tests use mocked HTTP responses — no real cameras needed.

```bash
pip install -r requirements.txt
pytest -v
```

## Architecture Decisions

1. **Digest vs Basic auth**: Auto-selected per Axis documentation (HTTP→Digest, HTTPS→Basic).
2. **`activateLight`/`deactivateLight`**: The actual VAPIX methods — there is no `setLightState`.
3. **I/O port states**: Use `"open"`/`"closed"` strings, not booleans (per VAPIX spec).
4. **Connection pooling**: One `httpx.AsyncClient` per camera, reused across tool calls.
5. **Docker stdio**: Uses `docker run -i` so MCP clients can communicate via stdin/stdout.
6. **No `axis` PyPI package**: All VAPIX calls implemented directly for full control.

## VAPIX API Reference

- [VAPIX Documentation](https://developer.axis.com/vapix/)
- [Authentication](https://developer.axis.com/vapix/authentication/)
- [Basic Device Information](https://developer.axis.com/vapix/network-video/basic-device-information/)
- [I/O Port Management](https://developer.axis.com/vapix/network-video/io-port-management/)
- [Light Control](https://developer.axis.com/vapix/network-video/light-control/)
