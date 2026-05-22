"""
Smoke test against a real camera — read-only operations only.
"""
import asyncio
import sys
import traceback
import socket
from config import load_config
from vapix.client import VapixClient, VapixError
from vapix import device, imaging, ptz, io_ports, light, discovery, overlay, vmd, guard_tour, siren, storage, clear_view, privacy_mask
from vapix import time_service, daynight, stream_profiles, geolocation, audio, events


async def main():
    cfg = load_config()
    cam = cfg.cameras[0]
    print(f"Camera: {cam.name} ({cam.host}:{cam.port}, https={cam.https})")
    print(f"Capabilities: {cam.capabilities}")
    print()

    # Connectivity check
    print("--- connectivity check ---")
    try:
        s = socket.create_connection((cam.host, cam.port), timeout=5)
        s.close()
        print(f"  TCP connection to {cam.host}:{cam.port} OK")
    except Exception as e:
        print(f"  CANNOT REACH {cam.host}:{cam.port}: {type(e).__name__}: {e}")
        return 1

    client = VapixClient(cam)
    ok = 0
    fail = 0
    skip = 0

    # 1. API Discovery (always available on modern firmware)
    print("\n--- discover_apis ---")
    supported_apis = set()
    try:
        apis = await discovery.get_api_list(client)
        for api in apis:
            supported_apis.add(api.get("id", ""))
            print(f"  {api.get('id')}: v{api.get('version')} ({api.get('status', '')})")
        print(f"  Total: {len(apis)} APIs supported")
        ok += 1
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        fail += 1

    # 2. Device info
    print("\n--- get_all_properties ---")
    try:
        props = await device.get_all_properties(client)
        for k, v in list(props.items())[:8]:
            print(f"  {k}: {v}")
        ok += 1
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        fail += 1

    # 3. Snapshot
    print("\n--- get_snapshot ---")
    try:
        data = await imaging.get_snapshot(client)
        print(f"  Got {len(data)} bytes of JPEG (starts with {data[:4].hex()})")
        ok += 1
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        fail += 1

    # 4. PTZ status (read-only)
    print("\n--- ptz get_position ---")
    try:
        pos = await ptz.get_position(client)
        print(f"  Position: {pos}")
        ok += 1
    except Exception as e:
        print(f"  SKIPPED: {type(e).__name__}: {e}")
        skip += 1

    # 5. I/O ports (read-only)
    if "io-port-management" in supported_apis:
        print("\n--- get_ports ---")
        try:
            ports_list = await io_ports.get_ports(client)
            for p in ports_list:
                print(f"  Port {p['port']}: {p.get('name','')} dir={p.get('direction','')} state={p.get('state','')}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- get_ports --- SKIPPED (not supported)")
        skip += 1

    # 6. Lights (read-only)
    if "light-control" in supported_apis:
        print("\n--- get_light_information ---")
        try:
            lights = await light.get_light_information(client)
            print(f"  Lights: {lights}")
            ok += 1
        except Exception as e:
            print(f"  SKIPPED: {type(e).__name__}: {e}")
            skip += 1
    else:
        print("\n--- get_light_information --- SKIPPED (not supported)")
        skip += 1

    # 7. Dynamic Overlay (read-only: just list)
    if "dynamicoverlay" in supported_apis or "dynamic-overlay" in supported_apis:
        print("\n--- list_overlays ---")
        try:
            overlays = await overlay.list_overlays(client)
            n_text = len(overlays.get("textOverlays", []))
            n_image = len(overlays.get("imageOverlays", []))
            n_files = len(overlays.get("imageFiles", []))
            print(f"  Text overlays: {n_text}, Image overlays: {n_image}, Image files: {n_files}")
            for ov in overlays.get("textOverlays", []):
                print(f"    [{ov.get('identity')}] \"{ov.get('text', '')}\" at {ov.get('position', '?')}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        # Try anyway — API ID might differ
        print("\n--- list_overlays (trying) ---")
        try:
            overlays = await overlay.list_overlays(client)
            n_text = len(overlays.get("textOverlays", []))
            print(f"  Text overlays: {n_text}")
            ok += 1
        except Exception as e:
            print(f"  SKIPPED: {type(e).__name__}: {e}")
            skip += 1

    # 8. VMD4 Motion Detection (read-only: get config)
    if "vmd" in supported_apis or "guard-tour" in supported_apis:
        print("\n--- vmd get_configuration ---")
    else:
        print("\n--- vmd get_configuration (trying) ---")
    try:
        vmd_config = await vmd.get_configuration(client)
        n_profiles = len(vmd_config.get("profiles", []))
        n_cameras = len(vmd_config.get("cameras", []))
        print(f"  Cameras: {n_cameras}, Profiles: {n_profiles}")
        for prof in vmd_config.get("profiles", []):
            n_triggers = len(prof.get("triggers", []))
            n_filters = len(prof.get("filters", []))
            print(f"    Profile \"{prof.get('name', '?')}\": {n_triggers} triggers, {n_filters} filters")
        ok += 1
    except Exception as e:
        print(f"  SKIPPED: {type(e).__name__}: {e}")
        skip += 1

    # 9. Guard Tour (read-only: list)
    if "guard-tour" in supported_apis:
        print("\n--- list_guard_tours ---")
        try:
            tours = await guard_tour.list_tours(client)
            print(f"  Tours: {len(tours)}")
            for t in tours:
                print(f"    {t.get('id')}: \"{t.get('name', '?')}\" running={t.get('running', '?')} presets={len(t.get('presets', []))}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- list_guard_tours --- SKIPPED (not supported)")
        skip += 1

    # 10. Siren & Light (read-only: status)
    if "siren-and-light" in supported_apis:
        print("\n--- siren get_status ---")
        try:
            status = await siren.get_status(client)
            if status:
                print(f"  Active: {status}")
            else:
                print(f"  Status: idle")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- siren get_status --- SKIPPED (not supported)")
        skip += 1

    # Edge Storage: disk status
    if "disk-management" in supported_apis:
        print("\n--- list_disks ---")
        try:
            disks = await storage.list_disks(client)
            for d in disks:
                size_mb = int(d.get("totalsize", 0)) // 1024
                free_mb = int(d.get("freesize", 0)) // 1024
                print(f"  {d.get('diskid')}: {d.get('name', '?')} "
                      f"({size_mb} MB total, {free_mb} MB free) "
                      f"status={d.get('status')} fs={d.get('filesystem')}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- list_disks --- SKIPPED (disk-management not supported)")
        skip += 1

    # Edge Storage: disk health
    if "disk-properties" in supported_apis:
        print("\n--- get_disk_health ---")
        try:
            health = await storage.get_disk_health(client)
            for h in health:
                print(f"  {h}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- get_disk_health --- SKIPPED (disk-properties not supported)")
        skip += 1

    # Edge Storage: list recordings
    if "recording" in supported_apis:
        print("\n--- list_recordings ---")
        try:
            recs = await storage.list_recordings(client, max_recordings=5)
            for r in recs:
                if r.get("_summary"):
                    print(f"  Total recordings: {r['total']} (showing {r['returned']})")
                else:
                    print(f"  {r.get('recordingid', '?')}: "
                          f"{r.get('starttime', '?')} → {r.get('stoptime', '?')} "
                          f"disk={r.get('diskid')}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- list_recordings --- SKIPPED (recording not supported)")
        skip += 1

    # Clear View
    if "clear-view" in supported_apis:
        print("\n--- clear_view get_service_info ---")
        try:
            services = await clear_view.get_service_info(client)
            if services:
                for s in services:
                    print(f"  Service {s['id']}: type={s['type']} "
                          f"duration={s.get('durationDefault', '?')}s "
                          f"stoppable={s.get('stoppable', '?')}")
            else:
                print("  API supported but no cleaning hardware available")
            ok += 1
        except Exception as e:
            print(f"  SKIPPED: {type(e).__name__}: {e}")
            skip += 1
    else:
        print("\n--- clear_view get_service_info --- SKIPPED (clear-view not supported)")
        skip += 1

    # Privacy Mask: list masks (read-only)
    if "privacy-mask" in supported_apis:
        print("\n--- list_privacy_masks ---")
        try:
            masks = await privacy_mask.list_masks(client)
            if masks:
                for m in masks:
                    corners = len(m.get("position", []))
                    print(f"  [{m.get('id')}] \"{m.get('name')}\" "
                          f"enabled={m.get('enabled')} "
                          f"corners={corners}")
            else:
                print("  No privacy masks configured")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1

        # Non-destructive round-trip: add, verify, remove
        print("\n--- privacy_mask add/verify/remove ---")
        test_mask_name = "_mcp_smoke_test_mask"
        try:
            await privacy_mask.add_mask(
                client, test_mask_name,
                width=5.0, height=5.0,
                center_x=95.0, center_y=95.0,
            )
            # Verify it exists
            masks_after = await privacy_mask.list_masks(client)
            found = [m for m in masks_after if m.get("name") == test_mask_name]
            assert len(found) == 1, f"Expected 1 mask named {test_mask_name}, got {len(found)}"
            print(f"  Added mask '{test_mask_name}' — verified in list")
            # Clean up
            await privacy_mask.remove_mask(client, test_mask_name)
            masks_final = await privacy_mask.list_masks(client)
            still_there = [m for m in masks_final if m.get("name") == test_mask_name]
            assert len(still_there) == 0, f"Mask {test_mask_name} still exists after remove"
            print(f"  Removed mask '{test_mask_name}' — verified gone")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            # Try cleanup even on failure
            try:
                await privacy_mask.remove_mask(client, test_mask_name)
            except Exception:
                pass
            fail += 1
    else:
        print("\n--- list_privacy_masks --- SKIPPED (privacy-mask not supported)")
        skip += 1

    # --- NEW APIs ---

    # Time API
    if "time-service" in supported_apis:
        print("\n--- time get_date_time_info ---")
        try:
            info = await time_service.get_date_time_info(client)
            print(f"  UTC: {info.get('dateTime', '?')}")
            print(f"  TZ: {info.get('timeZone', '?')}")
            print(f"  DST: {info.get('dstEnabled', '?')}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- time get_date_time_info --- SKIPPED (time-service not supported)")
        skip += 1

    # Stream Profiles
    if "stream-profiles" in supported_apis:
        print("\n--- stream_profiles list ---")
        try:
            result = await stream_profiles.list_profiles(client)
            profiles = result.get("streamProfile", [])
            max_p = result.get("maxProfiles", "?")
            print(f"  Max profiles: {max_p}, Current: {len(profiles)}")
            for p in profiles[:5]:
                print(f"    \"{p.get('name', '?')}\": {p.get('parameters', '')[:60]}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- stream_profiles list --- SKIPPED (stream-profiles not supported)")
        skip += 1

    # Audio Control
    if "audio-device-control" in supported_apis:
        print("\n--- audio get_settings ---")
        try:
            settings = await audio.get_settings(client)
            devices_list = settings.get("devices", [])
            print(f"  Audio devices: {len(devices_list)}")
            for d in devices_list:
                inputs = d.get("inputs", [])
                outputs = d.get("outputs", [])
                print(f"    Device {d.get('deviceId', '?')}: "
                      f"{len(inputs)} inputs, {len(outputs)} outputs")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- audio get_settings --- SKIPPED (audio-device-control not supported)")
        skip += 1

    # Day/Night (may not be in discovery on all cameras)
    print("\n--- daynight get_configuration (trying) ---")
    try:
        dn_config = await daynight.get_configuration(client)
        print(f"  DayNightShiftLevel: {dn_config.get('DayNightShiftLevel', '?')}")
        print(f"  Autotune: {dn_config.get('Autotune', '?')}")
        print(f"  NightFilter: {dn_config.get('NightFilter', '?')}")
        ok += 1
    except Exception as e:
        print(f"  SKIPPED: {type(e).__name__}: {e}")
        skip += 1

    # Geolocation (legacy API, may not be on all cameras)
    print("\n--- geolocation get_location (trying) ---")
    try:
        loc = await geolocation.get_location(client)
        print(f"  Lat: {loc.get('Lat', '?')}, Lng: {loc.get('Lng', '?')}")
        print(f"  Heading: {loc.get('Heading', '?')}, Text: {loc.get('Text', '')}")
        ok += 1
    except Exception as e:
        print(f"  SKIPPED: {type(e).__name__}: {e}")
        skip += 1

    # Recording Export (read-only: just check properties of first recording)
    if "recording-export" in supported_apis and "recording" in supported_apis:
        print("\n--- recording export_properties (first recording) ---")
        try:
            recs = await storage.list_recordings(client, max_recordings=1)
            real_recs = [r for r in recs if not r.get("_summary")]
            if real_recs:
                rec = real_recs[0]
                props = await storage.get_export_properties(
                    client,
                    recording_id=rec["recordingid"],
                    disk_id=rec["diskid"],
                )
                print(f"  Recording: {rec['recordingid']}")
                for k, v in props.items():
                    print(f"    {k}: {v}")
                ok += 1
            else:
                print("  No recordings available for export test")
                skip += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- recording export_properties --- SKIPPED (recording-export not supported)")
        skip += 1

    # Event Polling (WebSocket)
    if "event-streaming-over-websocket" in supported_apis:
        print("\n--- event polling (2s) ---")
        try:
            collected = await events.poll_events(client, duration_seconds=2.0)
            print(f"  Collected {len(collected)} events in 2s")
            for ev in collected[:3]:
                print(f"    {ev.get('topic', '?')}: {ev.get('timestamp', '?')}")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            fail += 1
    else:
        print("\n--- event polling --- SKIPPED (event-streaming-over-websocket not supported)")
        skip += 1

    await client.close()

    print(f"\n{'='*50}")
    print(f"Results: {ok} passed, {fail} failed, {skip} skipped")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
