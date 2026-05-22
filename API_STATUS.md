# VAPIX API Implementation Status

Tracking document for VAPIX API integrations in the MCP server.
Checked items are implemented, tested, and available as MCP tools.

---

## Implemented

- [x] **Basic Device Information** — `vapix/device.py`
  - Endpoint: `POST /axis-cgi/basicdeviceinfo.cgi`
  - Tools: `get_camera_info`
  - Read-only. Works on all Axis devices.
  - Pros: Essential for identification. Always available.
  - Cons: None.

- [x] **Snapshot / Imaging** — `vapix/imaging.py`
  - Endpoint: `GET /axis-cgi/jpg/image.cgi`
  - Tools: `get_snapshot`
  - Read-only. Returns JPEG bytes.
  - Pros: Core capability — lets AI see what the camera sees.
  - Cons: Single frame only; no video streaming.

- [x] **PTZ Control** — `vapix/ptz.py`
  - Endpoint: `GET /axis-cgi/com/ptz.cgi`
  - Tools: `ptz_move`, `ptz_relative`, `ptz_home`, `ptz_preset`, `ptz_status`
  - Read-write. Only works on PTZ cameras.
  - Pros: Full pan/tilt/zoom control with presets.
  - Cons: Not all cameras have PTZ. Requires `ptz` capability.

- [x] **I/O Port Management** — `vapix/io_ports.py`
  - Endpoint: `POST /axis-cgi/io/portmanagement.cgi`
  - Tools: `get_io_ports`, `set_io_port`
  - Read-write. Controls digital I/O (relays, inputs).
  - Pros: Can trigger physical actions (door locks, alarms, gates).
  - Cons: Some cameras have input-only ports. Requires `io` capability.

- [x] **Light Control** — `vapix/light.py`
  - Endpoint: `POST /axis-cgi/lightcontrol.cgi`
  - Tools: `get_lights`, `toggle_light`
  - Read-write. Controls IR/white/status LEDs.
  - Pros: Night vision illumination, deterrence.
  - Cons: Only cameras with built-in LEDs. Requires `light` capability.

- [x] **API Discovery** — `vapix/discovery.py`
  - Endpoint: `POST /axis-cgi/apidiscovery.cgi`
  - Tools: `discover_apis`
  - Read-only. Lists all VAPIX APIs supported by a device.
  - Pros: Essential for knowing what a camera supports. Enables auto-detection.
  - Cons: None. Available on all modern firmware (AXIS OS 9.80+).

- [x] **Dynamic Overlay** — `vapix/overlay.py`
  - Endpoint: `POST /axis-cgi/dynamicoverlay/dynamicoverlay.cgi`
  - Tools: `list_overlays`, `add_overlay`, `remove_overlay`
  - Read-write. Adds/removes text and image overlays on live video.
  - Pros: AI can annotate the view with alerts, labels, timestamps.
  - Cons: Max 512 chars per text. Overlay IDs may change after reboot. Requires `overlay` capability.

- [x] **Video Motion Detection 4** — `vapix/vmd.py`
  - Endpoint: `POST /local/vmd/control.cgi`
  - Tools: `get_motion_config`, `set_motion_config`
  - Read-write. Configures motion detection zones and filters.
  - Pros: Core security feature. AI can tune sensitivity, exclude areas, configure triggers.
  - Cons: Coordinate-based zone config is complex. Requires `vmd` capability.

- [x] **Guard Tour** — `vapix/guard_tour.py`
  - Endpoint: `GET /axis-cgi/param.cgi` (param-based, not JSON POST)
  - Tools: `list_guard_tours`, `start_guard_tour`, `stop_guard_tour`
  - Read-write. Creates/manages automated PTZ patrol routes.
  - Pros: Automated surveillance patrols. Natural for AI orchestration.
  - Cons: Parameter-based API (older style). Requires PTZ camera. Requires `guard_tour` capability.

- [x] **Siren & Light** — `vapix/siren.py`
  - Endpoint: `POST /axis-cgi/siren_and_light.cgi`
  - Tools: `get_siren_status`, `activate_siren`, `stop_siren`
  - Read-write. Controls combo siren+strobe devices (e.g. D2050-VE).
  - Pros: Physical deterrence — activate sirens and strobe lights.
  - Cons: Only for dedicated siren/light devices. Different from `light.py`. Requires `siren` capability.

---

## Implemented (continued)

- [x] **Edge Storage** — `vapix/storage.py`
  - Endpoints: `GET /axis-cgi/disks/list.cgi`, `GET /axis-cgi/disks/gethealth.cgi`, `GET /axis-cgi/record/list.cgi`, `GET /axis-cgi/record/export/properties.cgi`, `GET /axis-cgi/record/export/exportrecording.cgi`
  - Tools: `get_disk_status`, `list_recordings`, `get_recording_info`, `export_recording`
  - Read-only/write. Check disk status/health, list recordings, get export metadata, download .mkv clips.
  - **Note**: Unlike other APIs, these return XML (not JSON). Parsed internally. Export returns binary .mkv.
  - Pros: Monitor SD card health/space, find recordings by time range, download footage for review.
  - Cons: Large files need mounted volume. Long downloads for big clips. Requires `storage` capability.

- [x] **Clear View** — `vapix/clear_view.py`
  - Endpoint: `POST /axis-cgi/clearviewcontrol.cgi`
  - Tools: `get_clear_view_info`, `start_clear_view`, `stop_clear_view`
  - Read-write. Activates wiper or speed-dry to clean the camera lens.
  - Pros: AI can trigger lens cleaning when image quality degrades. Simple JSON POST API.
  - Cons: Only cameras with wiper/speed-dry hardware. Requires `clear_view` capability.

- [x] **Privacy Mask** — `vapix/privacy_mask.py`
  - Endpoint: `GET /axis-cgi/privacymask.cgi`
  - Tools: `list_privacy_masks`, `add_privacy_mask`, `remove_privacy_mask`
  - Read-write. Manage privacy masks that cover sensitive areas in the video.
  - Position via width/height in percent or pixel polygon coordinates.
  - Masks auto-adapt to PTZ changes. Camera has max mask limit.
  - Pros: AI can dynamically mask/unmask regions. Important for GDPR compliance.
  - Cons: Coordinate-based positioning. Requires `privacy_mask` capability.

- [x] **Time Service** — `vapix/time_service.py`
  - Endpoint: `POST /axis-cgi/time.cgi`
  - Tools: `get_time_info`, `set_timezone`
  - Read-write. Check/set camera date, time, and timezone.
  - Pros: Multi-camera time sync verification. Simple API.
  - Cons: Deprecated as of AXIS OS 12.4 (still functional). Requires `time` capability.

- [x] **Day/Night** — `vapix/daynight.py`
  - Endpoint: `POST /axis-cgi/daynight.cgi`
  - Tools: `get_daynight_config`, `set_daynight_config`
  - Read-write. Configure IR-cut filter switching thresholds and dwell times.
  - Pros: Tune image quality for changing light conditions.
  - Cons: Not available on all cameras. Requires `daynight` capability.

- [x] **Stream Profiles** — `vapix/stream_profiles.py`
  - Endpoint: `POST /axis-cgi/streamprofile.cgi`
  - Tools: `list_stream_profiles`, `create_stream_profile`, `remove_stream_profile`
  - Read-write. Manage video stream preset configurations (resolution, codec, FPS).
  - Pros: Create optimized streaming profiles per scenario.
  - Cons: Configuration task. Requires `stream_profiles` capability.

- [x] **Geolocation** — `vapix/geolocation.py`
  - Endpoints: `GET /axis-cgi/geolocation/get.cgi`, `GET /axis-cgi/geolocation/set.cgi`
  - Tools: `get_geolocation`, `set_geolocation`
  - Read-write. GPS coordinates (WGS-84) and compass heading.
  - **Note**: Legacy XML API, not JSON POST pattern.
  - Pros: Fleet management, map integration, spatial awareness.
  - Cons: Manual coordinates (no GPS hardware on most cameras). Requires `geolocation` capability.

- [x] **Audio Device Control** — `vapix/audio.py`
  - Endpoint: `POST /axis-cgi/audiodevicecontrol.cgi`
  - Tools: `get_audio_settings`, `set_audio_settings`
  - Read-write. Configure audio input/output hardware (gain, mute, connection type).
  - Pros: Tune audio for two-way communication. Check mic/speaker status.
  - Cons: Audio streaming itself is RTSP (not practical via MCP). Requires `audio` capability.

- [x] **Event Polling (WebSocket)** — `vapix/events.py`
  - Endpoint: `ws://<device>/vapix/ws-data-stream?sources=events`
  - Tools: `poll_events`
  - Read-only. Opens a WebSocket, collects events for a specified duration (1-30s), returns batch.
  - Uses session token authentication. Supports ONVIF topic filtering.
  - Pros: AI can check what's happening on a camera right now (motion, I/O, tampering).
  - Cons: Polling approach (not persistent subscription). Requires `websockets` package. Requires `events` capability.

- [x] **Capture Mode** — `vapix/capture_mode.py`
  - Endpoint: `POST /axis-cgi/capturemode.cgi`
  - Tools: `get_capture_modes`, `set_capture_mode`
  - Read-write. List and change video capture modes (resolution/FPS combinations).
  - Pros: AI can optimize resolution vs frame rate per scenario.
  - Cons: Changing mode requires camera reboot. Requires `capture_mode` capability.

- [x] **Orientation Sensor** — `vapix/orientation.py`
  - Endpoints: `GET /axis-cgi/orientation/getlongitudinalvalue.cgi`, `GET /axis-cgi/orientation/getlateralvalue.cgi`
  - Tools: `get_orientation`
  - Read-only. Physical mounting angle from accelerometer/gyroscope.
  - **Note**: Legacy XML API. Not video rotation — physical sensor data.
  - Pros: Verify camera is level. Detect tampering (tilt changes).
  - Cons: Not all cameras have orientation sensors. Requires `orientation` capability.

- [x] **NTP** — `vapix/ntp.py`
  - Endpoint: `POST /axis-cgi/ntp.cgi`
  - Tools: `get_ntp_status`, `set_ntp_config`
  - Read-write. Check NTP sync status and configure time servers.
  - Pros: Verify time synchronization. Fleet-wide NTP consistency checks.
  - Cons: Configuration task. Requires `ntp` capability.

- [x] **Analytics Metadata Config** — `vapix/analytics_metadata.py`
  - Endpoint: `POST /axis-cgi/analyticsmetadataconfig.cgi`
  - Tools: `list_analytics_producers`, `set_analytics_producers`
  - Read-write. Enable/disable analytics metadata producers (object detection, motion tracking).
  - Pros: Control what analytics data is generated. Enable only needed producers.
  - Cons: Requires AXIS Object Analytics or similar ACAP. Requires `analytics_metadata` capability.

---

## Server Features (Non-API)

- [x] **Auto-capability detection** — Queries API Discovery and maps supported APIs to capabilities automatically.
- [x] **Multi-camera batch tools** — `snapshot_all` and `status_all` for fleet operations.
- [x] **MCP Resources** — `camera://{id}/snapshot` and `camera://{id}/info` URIs.
- [x] **Streamable HTTP transport** — `--transport streamable-http` for latest MCP protocol.
- [x] **Typed dispatch** — Handler-function registry replaces if/elif chain.
- [x] **GitHub Actions CI** — Automated linting + Docker test builds.

---

## Future Candidates (Second Tier)

All previous future candidates have been implemented. No remaining candidates at this time.

---

## Not Planned (Low Value / High Risk)

- [ ] **Firmware Management** — Too destructive (upgrade, factory reset, reboot).
- [ ] **Network Settings** — Misconfiguration can brick camera connectivity.
- [ ] **User Management** — Security-sensitive, limited scope (password policies only, BETA).
- [ ] **MQTT Client Configuration** — Infrastructure setup, not operational control.
- [ ] **Event Action Rules (SOAP)** — SOAP/XML complexity. WebSocket events are superior.
- [ ] **Param API (new framework)** — BETA, unstable. Domain-specific APIs are better.
