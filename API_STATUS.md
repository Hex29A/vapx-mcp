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
  - Endpoints: `GET /axis-cgi/disks/list.cgi`, `GET /axis-cgi/disks/gethealth.cgi`, `GET /axis-cgi/record/list.cgi`, `GET /axis-cgi/record/export/properties.cgi`
  - Tools: `get_disk_status`, `list_recordings`, `get_recording_info`
  - Read-only. Check disk status/health, list recordings, get export metadata.
  - **Note**: Unlike other APIs, these return XML (not JSON). Parsed internally.
  - Pros: Monitor SD card health/space, find recordings by time range, check export sizes.
  - Cons: Actual recording playback is RTSP (not feasible in MCP). Binary export not exposed. Requires `storage` capability.

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

---

## Future Candidates (Second Tier)

- [ ] **Recording Export** — `vapix/storage.py` (extend)
  - Endpoint: `GET /axis-cgi/record/export/exportrecording.cgi`
  - Potential tools: `export_recording`
  - Downloads .mkv video clips for a specific time interval to a Docker-mounted volume.
  - Workflow: `list_recordings` → `get_recording_info` (check size) → `export_recording` → file on host.
  - Pros: AI can retrieve actual video footage. Killer feature for incident review.
  - Cons: Large files. Needs mounted volume. Long downloads for big clips. Should warn before exporting large files.

- [ ] **Time API** — `vapix/time.py`
  - Endpoint: `POST /axis-cgi/time.cgi`
  - Potential tools: `get_time`, `set_timezone`
  - Read-write. Diagnostics — check/fix camera time.
  - Pros: Simple. Useful for multi-camera sync verification.
  - Cons: Low frequency of use. NTP should handle this.

- [ ] **Day/Night API** — `vapix/daynight.py`
  - Endpoint: `POST /axis-cgi/daynight.cgi`
  - Potential tools: `get_daynight_config`, `set_daynight_config`
  - Read-write. Tune IR-cut filter auto-switching.
  - Pros: Fix image quality issues in changing light.
  - Cons: Niche. Most cameras handle this well automatically.

- [ ] **Stream Profiles** — `vapix/stream_profiles.py`
  - Endpoint: `POST /axis-cgi/streamprofile.cgi`
  - Potential tools: `list_profiles`, `create_profile`
  - Read-write. Configure video stream settings.
  - Pros: Create optimized profiles per scenario.
  - Cons: Configuration task, not operational. Rarely needed at runtime.

- [ ] **Geolocation** — `vapix/geolocation.py`
  - Endpoints: `/axis-cgi/geolocation/get.cgi`, `/axis-cgi/geolocation/set.cgi`
  - Potential tools: `get_location`, `set_location`
  - Read-write. GPS coordinates + heading.
  - Pros: Fleet management, map integration.
  - Cons: Coordinates are manual (no GPS module on most cameras).

- [ ] **Audio Control** — `vapix/audio.py`
  - Endpoints: `/axis-cgi/audio/receive.cgi`, `/axis-cgi/audio/transmit.cgi`
  - Potential tools: `get_audio_config`, `enable_audio`
  - Read-write. Two-way audio config.
  - Pros: Intercom functionality configuration.
  - Cons: Actual audio streaming is binary/RTSP — not practical via MCP.

- [ ] **Event Streaming (WebSocket)** — `vapix/events.py`
  - Endpoint: `ws://<device>/vapix/ws-data-stream?sources=events`
  - Potential tools: `subscribe_events`, `get_recent_events`
  - Read-only. Real-time event notifications.
  - Pros: Foundation for reactive AI (motion alerts, I/O triggers, etc.).
  - Cons: WebSocket requires persistent connection — complex for MCP tool model.
    Long-lived subscriptions don't fit request/response pattern well.
    May need MCP resources or sampling instead of tools.
    Requires `websocket-client` or `websockets` dependency.

---

## Not Planned (Low Value / High Risk)

- [ ] **Firmware Management** — Too destructive (upgrade, factory reset, reboot).
- [ ] **Network Settings** — Misconfiguration can brick camera connectivity.
- [ ] **User Management** — Security-sensitive, limited scope (password policies only, BETA).
- [ ] **MQTT Client Configuration** — Infrastructure setup, not operational control.
- [ ] **Event Action Rules (SOAP)** — SOAP/XML complexity. WebSocket events are superior.
- [ ] **Param API (new framework)** — BETA, unstable. Domain-specific APIs are better.
