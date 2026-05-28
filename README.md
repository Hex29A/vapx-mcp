# VAPX MCP Server

A **Model Context Protocol (MCP)** server that wraps **Axis camera VAPIX APIs**, enabling AI assistants (Claude, etc.) to control and query Axis network cameras directly.

> **Disclaimer**: This project is not affiliated with, endorsed by, or in any way officially connected to [Axis Communications AB](https://www.axis.com/). VAPIX is a registered trademark of Axis Communications AB.

Built to run in **Docker** for easy deployment.

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
| `export_recording` | Download recording as .mkv file | `/axis-cgi/record/export/exportrecording.cgi` |
| `get_time_info` | Get camera date/time, timezone, DST status | `/axis-cgi/time.cgi` |
| `set_timezone` | Set camera timezone (IANA name) | `/axis-cgi/time.cgi` |
| `get_daynight_config` | Get IR-cut filter day/night settings | `/axis-cgi/daynight.cgi` |
| `set_daynight_config` | Configure day/night switching thresholds | `/axis-cgi/daynight.cgi` |
| `list_stream_profiles` | List video stream profiles | `/axis-cgi/streamprofile.cgi` |
| `create_stream_profile` | Create a stream profile (resolution, codec, FPS) | `/axis-cgi/streamprofile.cgi` |
| `remove_stream_profile` | Remove a stream profile by name | `/axis-cgi/streamprofile.cgi` |
| `get_geolocation` | Get camera GPS coordinates and heading | `/axis-cgi/geolocation/get.cgi` |
| `set_geolocation` | Set camera GPS coordinates and heading | `/axis-cgi/geolocation/set.cgi` |
| `get_audio_settings` | Get audio device settings (gain, mute, input) | `/axis-cgi/audiodevicecontrol.cgi` |
| `set_audio_settings` | Update audio device settings | `/axis-cgi/audiodevicecontrol.cgi` |
| `poll_events` | Collect camera events via WebSocket (1-30s poll) | `ws://device/vapix/ws-data-stream` |
| `get_capture_modes` | List available capture modes (resolution/FPS) | `/axis-cgi/capturemode.cgi` |
| `set_capture_mode` | Set capture mode (requires reboot) | `/axis-cgi/capturemode.cgi` |
| `get_orientation` | Read physical orientation sensor values | `/axis-cgi/orientation/*.cgi` |
| `get_ntp_status` | Get NTP synchronization status | `/axis-cgi/ntp.cgi` |
| `set_ntp_config` | Configure NTP client settings | `/axis-cgi/ntp.cgi` |
| `list_analytics_producers` | List analytics metadata producers | `/axis-cgi/analyticsmetadataconfig.cgi` |
| `set_analytics_producers` | Enable/disable analytics producers | `/axis-cgi/analyticsmetadataconfig.cgi` |
| `get_temperature` | Read temperature sensors and heater status | `/axis-cgi/temperaturecontrol.cgi` |
| `get_stream_status` | Real-time stream diagnostics | `/axis-cgi/streamstatus.cgi` |
| `get_mqtt_config` | Get MQTT client configuration | `/axis-cgi/mqtt.cgi` |
| `configure_mqtt` | Configure MQTT broker connection | `/axis-cgi/mqtt.cgi` |
| `enable_mqtt` | Activate the MQTT client | `/axis-cgi/mqtt.cgi` |
| `disable_mqtt` | Deactivate the MQTT client | `/axis-cgi/mqtt.cgi` |
| `reboot_camera` | Reboot camera (offline ~30-60s after call) | `/axis-cgi/firmwaremanagement.cgi` |
| `get_system_log` | Read system log, optionally last N lines | `/axis-cgi/admin/systemlog.cgi` |
| `get_audit_log` | Read security audit log (logins, config changes) | `/axis-cgi/auditlog.cgi` |
| `check_systemready` | Check if camera is ready to handle requests | `/axis-cgi/systemready.cgi` |
| `snapshot_all` | Capture snapshots from all cameras at once | Multi-camera batch |
| `status_all` | Get online/offline status of all cameras | Multi-camera batch |

**65 tools** across 23 VAPIX API families.

## Additional Features

- **Auto-capability detection**: Add `auto` to a camera's capabilities list to auto-discover supported APIs via VAPIX API Discovery. Detected capabilities are merged with manually specified ones.
- **MCP Resources**: Cameras expose `camera://{id}/snapshot` (live JPEG) and `camera://{id}/info` (device properties) as MCP resources.
- **Streamable HTTP transport**: Run with `--transport streamable-http` for the latest MCP transport protocol.
- **Typed dispatch**: Handler-function registry with per-tool capability checking — easy to extend.
- **GitHub Actions CI**: Automated linting (ruff), Docker test builds, and unit tests on every push/PR.

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
    "vapx": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--network=host",
        "-v", "/path/to/cameras.yaml:/app/cameras.yaml:ro",
        "-v", "/path/to/exports:/exports",
        "--env-file", "/path/to/.env",
        "vapx-mcp"
      ]
    }
  }
}
```

> **`--network=host`** is required so the container can reach cameras on your local LAN.
> **`-v .../exports:/exports`** is needed if you use `export_recording` — without it, exported files are lost when the container exits. Set `VAPIX_EXPORTS_DIR` env var to change the export path.

### 5. Alternative: SSE/HTTP mode

For web-based access or debugging:

```bash
# SSE mode
docker compose up vapx-sse
# Server available at http://localhost:8080/sse

# Streamable HTTP mode (latest MCP transport)
python server.py --transport streamable-http --port 8080
```

## Project Structure

```
├── server.py              # MCP server entry point, tool definitions & dispatch
├── config.py              # YAML config loading with env var substitution
├── vapix/
│   ├── client.py          # Base HTTP client (auth, requests, errors)
│   ├── device.py          # Basic Device Information API
│   ├── imaging.py         # JPEG snapshot capture
│   ├── ptz.py             # Pan/Tilt/Zoom control
│   ├── io_ports.py        # I/O port management
│   ├── light.py           # Light control (IR/white LEDs)
│   ├── discovery.py       # API Discovery
│   ├── overlay.py         # Dynamic text/image overlays
│   ├── vmd.py             # VMD4 motion detection
│   ├── guard_tour.py      # PTZ guard tours
│   ├── siren.py           # Siren & strobe light control
│   ├── storage.py         # Edge storage & recording export
│   ├── clear_view.py      # Wiper / speed-dry control
│   ├── privacy_mask.py    # Privacy mask management
│   ├── time_service.py    # Date/time & timezone
│   ├── daynight.py        # IR-cut filter day/night switching
│   ├── stream_profiles.py # Video stream profiles
│   ├── geolocation.py     # GPS coordinates
│   ├── audio.py           # Audio device control
│   ├── events.py          # WebSocket event streaming
│   ├── capture_mode.py    # Capture mode (resolution/FPS)
│   ├── orientation.py     # Physical orientation sensor
│   ├── ntp.py             # NTP synchronization
│   ├── analytics_metadata.py # Analytics metadata producers
│   ├── temperature.py     # Temperature sensors & heaters
│   ├── stream_status.py   # Real-time stream diagnostics
│   ├── mqtt.py            # MQTT client & event bridge config
│   └── system.py          # Reboot, system log, audit log, systemready
├── tests/                 # Unit & integration tests (mocked HTTP)
├── .github/workflows/ci.yml  # GitHub Actions CI
├── Dockerfile
├── docker-compose.yml
├── cameras.example.yaml   # Example camera config
├── .env.example           # Example environment variables
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

### vapx format (also supported)

If you use [vapx](https://github.com/Hex29A/vapx), vapx-mcp can read the same config file directly:

```yaml
defaults:
  user: root
  https: false
  verify_ssl: false

cameras:
  front-door:
    host: "192.168.1.100"
    pass: "mypassword"
  backyard:
    host: "192.168.1.101"
    pass: "otherpassword"
```

The camera key becomes the `id`, `pass` maps to `password`, `user` maps to `username`, and `defaults` apply to all cameras. When no `capabilities` are listed, they are **auto-discovered** from the camera at startup via VAPIX API Discovery.

### Capabilities

Capabilities control which tools are available per camera. If omitted, capabilities are **auto-discovered** at startup. Use `auto` to force auto-detection even when some capabilities are listed manually.

| Capability | Required for |
|------------|-------------|
| `auto` | Auto-detect via VAPIX API Discovery (merged with manual) |
| `snapshot` | `get_snapshot`, `snapshot_all` |
| `ptz` | `ptz_move`, `ptz_relative`, `ptz_home`, `ptz_preset`, `ptz_status` |
| `io` | `get_io_ports`, `set_io_port` |
| `light` | `get_lights`, `toggle_light` |
| `overlay` | `list_overlays`, `add_overlay`, `remove_overlay` |
| `vmd` | `get_motion_config`, `set_motion_config` |
| `guard_tour` | `list_guard_tours`, `start_guard_tour`, `stop_guard_tour` |
| `siren` | `get_siren_status`, `activate_siren`, `stop_siren` |
| `storage` | `get_disk_status`, `list_recordings`, `get_recording_info`, `export_recording` |
| `clear_view` | `get_clear_view_info`, `start_clear_view`, `stop_clear_view` |
| `privacy_mask` | `list_privacy_masks`, `add_privacy_mask`, `remove_privacy_mask` |
| `time` | `get_time_info`, `set_timezone`, `get_ntp_status`, `set_ntp_config` |
| `daynight` | `get_daynight_config`, `set_daynight_config` |
| `stream_profiles` | `list_stream_profiles`, `create_stream_profile`, `remove_stream_profile` |
| `geolocation` | `get_geolocation`, `set_geolocation` |
| `audio` | `get_audio_settings`, `set_audio_settings` |
| `events` | `poll_events` |
| `capture_mode` | `get_capture_modes`, `set_capture_mode` |
| `orientation` | `get_orientation` |
| `analytics_metadata` | `list_analytics_producers`, `set_analytics_producers` |
| `temperature` | `get_temperature` |
| `stream_status` | `get_stream_status` |
| `mqtt` | `get_mqtt_config`, `configure_mqtt`, `enable_mqtt`, `disable_mqtt` |

`get_camera_info`, `list_cameras`, `discover_apis`, `snapshot_all`, `status_all`, `reboot_camera`, `get_system_log`, `get_audit_log`, and `check_systemready` work regardless of capabilities.

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

# Run in Streamable HTTP mode
python server.py --transport streamable-http --port 8080
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
3. **I/O port states**: Use `"open"`/`"closed"` strings, not booleans (per VAPIX spec). Legacy fallback for older firmware via `io/port.cgi`.
4. **Connection pooling**: One `httpx.AsyncClient` per camera, reused across tool calls.
5. **Docker stdio**: Uses `docker run -i` so MCP clients can communicate via stdin/stdout.
6. **No `axis` PyPI package**: All VAPIX calls implemented directly for full control.
7. **Legacy fallbacks**: `daynight` and `io_ports` modules try modern JSON APIs first, then fall back to `param.cgi` / legacy CGIs for older firmware. `reboot_camera` falls back to `restart.cgi` on firmware < 7.40.

## VAPIX API Reference

- [VAPIX Documentation](https://developer.axis.com/vapix/)
- [Authentication](https://developer.axis.com/vapix/authentication/)
- [Basic Device Information](https://developer.axis.com/vapix/network-video/basic-device-information/)
- [I/O Port Management](https://developer.axis.com/vapix/network-video/io-port-management/)
- [Light Control](https://developer.axis.com/vapix/network-video/light-control/)
- [Firmware Management](https://developer.axis.com/vapix/network-video/firmware-management-api/)
- [Systemready](https://developer.axis.com/vapix/network-video/systemready-api/)
- [Audit Log](https://developer.axis.com/vapix/network-video/audit-log/)

## License

This project is licensed under the [MIT License](LICENSE).

This project is not affiliated with Axis Communications AB. VAPIX is a trademark of Axis Communications AB.
