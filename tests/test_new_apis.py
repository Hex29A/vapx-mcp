"""
Tests for the new VAPIX API modules: discovery, overlay, vmd, guard_tour, siren.

Uses respx to mock HTTP responses — no real cameras needed.
"""

import json
import pytest
import httpx
import respx

from config import CameraConfig
from vapix.client import VapixClient, VapixError
from vapix import discovery, overlay, vmd, guard_tour, siren, storage, clear_view, privacy_mask


def _make_camera(**overrides):
    defaults = dict(
        id="test-cam",
        name="Test Camera",
        host="192.168.1.100",
        port=443,
        https=True,
        verify_ssl=False,
        username="root",
        password="testpass",
        capabilities=["snapshot", "ptz", "io", "light", "overlay", "vmd", "guard_tour", "siren"],
    )
    defaults.update(overrides)
    return CameraConfig(**defaults)


BASE_URL = "https://192.168.1.100:443"


# ---------------------------------------------------------------------------
# API Discovery
# ---------------------------------------------------------------------------

class TestDiscoveryAPI:
    @pytest.mark.asyncio
    async def test_get_api_list(self):
        """Should return list of supported APIs."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getApiList",
            "data": {
                "apiList": [
                    {"id": "basic-device-info", "version": "1.2", "name": "Basic Device Information", "status": "released"},
                    {"id": "io-port-management", "version": "1.0", "name": "I/O Port Management", "status": "released"},
                    {"id": "light-control", "version": "1.1", "name": "Light Control", "status": "released"},
                ]
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/apidiscovery.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            apis = await discovery.get_api_list(client)
            assert len(apis) == 3
            assert apis[0]["id"] == "basic-device-info"
            assert apis[2]["version"] == "1.1"

    @pytest.mark.asyncio
    async def test_check_api_support_found(self):
        """Should return API info when the API is supported."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getApiList",
            "data": {
                "apiList": [
                    {"id": "light-control", "version": "1.1", "status": "released"},
                ]
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/apidiscovery.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await discovery.check_api_support(client, "light-control")
            assert result is not None
            assert result["version"] == "1.1"

    @pytest.mark.asyncio
    async def test_check_api_support_not_found(self):
        """Should return None when the API is not supported."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getApiList",
            "data": {"apiList": []},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/apidiscovery.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await discovery.check_api_support(client, "nonexistent")
            assert result is None


# ---------------------------------------------------------------------------
# Dynamic Overlay
# ---------------------------------------------------------------------------

class TestOverlayAPI:
    @pytest.mark.asyncio
    async def test_list_overlays(self):
        """Should return overlay lists."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "list",
            "data": {
                "imageFiles": ["/etc/overlays/logo.ovl"],
                "imageOverlays": [],
                "textOverlays": [
                    {"camera": 1, "identity": 0, "text": "Test", "fontSize": 80},
                ],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await overlay.list_overlays(client)
            assert len(result["textOverlays"]) == 1
            assert result["textOverlays"][0]["text"] == "Test"
            assert len(result["imageFiles"]) == 1

    @pytest.mark.asyncio
    async def test_add_text(self):
        """Should add a text overlay and return its identity."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "addText",
            "data": {"camera": 1, "identity": 5},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            identity = await overlay.add_text(
                client, "ALERT: Motion detected", position="topRight", text_color="red"
            )
            assert identity == 5

            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "addText"
            assert body["params"]["text"] == "ALERT: Motion detected"
            assert body["params"]["position"] == "topRight"
            assert body["params"]["textColor"] == "red"

    @pytest.mark.asyncio
    async def test_remove_overlay(self):
        """Should remove an overlay by identity."""
        mock_resp = {"apiVersion": "1.0", "method": "remove", "data": {}}
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await overlay.remove_overlay(client, identity=3)

            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "remove"
            assert body["params"]["identity"] == 3


# ---------------------------------------------------------------------------
# VMD4 Motion Detection
# ---------------------------------------------------------------------------

class TestVMD4API:
    @pytest.mark.asyncio
    async def test_get_configuration(self):
        """Should return VMD4 config with cameras and profiles."""
        mock_resp = {
            "apiVersion": "1.3",
            "method": "getConfiguration",
            "data": {
                "cameras": [{"active": True, "id": 1, "rotation": 0}],
                "profiles": [
                    {
                        "name": "Profile 1",
                        "uid": 1,
                        "camera": 1,
                        "filters": [],
                        "triggers": [{"type": "includeArea", "data": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
                    }
                ],
                "configurationStatus": 0,
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/local/vmd/control.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await vmd.get_configuration(client)
            assert len(result["cameras"]) == 1
            assert result["cameras"][0]["active"] is True
            assert len(result["profiles"]) == 1
            assert result["profiles"][0]["name"] == "Profile 1"

    @pytest.mark.asyncio
    async def test_set_configuration(self):
        """Should send correct setConfiguration payload."""
        mock_resp = {"apiVersion": "1.3", "method": "setConfiguration", "data": {}}
        cameras = [{"active": True, "id": 1, "rotation": 0}]
        profiles = [{"name": "Profile 1", "uid": 1, "camera": 1, "filters": [], "triggers": []}]

        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/local/vmd/control.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await vmd.set_configuration(client, cameras=cameras, profiles=profiles)

            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "setConfiguration"
            assert body["params"]["cameras"] == cameras
            assert body["params"]["profiles"] == profiles

    @pytest.mark.asyncio
    async def test_get_configuration_capabilities(self):
        """Should return VMD4 capabilities."""
        mock_resp = {
            "apiVersion": "1.3",
            "method": "getConfigurationCapabilities",
            "data": {"alarmOverlay": {"isSupported": False}},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/local/vmd/control.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await vmd.get_configuration_capabilities(client)
            assert result["alarmOverlay"]["isSupported"] is False


# ---------------------------------------------------------------------------
# Guard Tour
# ---------------------------------------------------------------------------

class TestGuardTourAPI:
    @pytest.mark.asyncio
    async def test_list_tours(self):
        """Should parse param.cgi response into structured tour data."""
        response_text = (
            "root.GuardTour.G0.Name=DayTour\n"
            "root.GuardTour.G0.Running=no\n"
            "root.GuardTour.G0.CamNbr=1\n"
            "root.GuardTour.G0.RandomEnabled=no\n"
            "root.GuardTour.G0.TimeBetweenSequences=10\n"
            "root.GuardTour.G0.Tour.T0.PresetNbr=1\n"
            "root.GuardTour.G0.Tour.T0.MoveSpeed=70\n"
            "root.GuardTour.G0.Tour.T0.WaitTime=15\n"
            "root.GuardTour.G0.Tour.T1.PresetNbr=2\n"
            "root.GuardTour.G0.Tour.T1.MoveSpeed=50\n"
            "root.GuardTour.G0.Tour.T1.WaitTime=20\n"
        )
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text=response_text)
            )
            tours = await guard_tour.list_tours(client)

            assert len(tours) == 1
            tour = tours[0]
            assert tour["id"] == "G0"
            assert tour["name"] == "DayTour"
            assert tour["running"] is False
            assert tour["camera"] == 1
            assert len(tour["presets"]) == 2
            assert tour["presets"][0]["preset_number"] == 1
            assert tour["presets"][1]["wait_time"] == 20

    @pytest.mark.asyncio
    async def test_list_tours_empty(self):
        """Should return empty list when no tours are configured."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text="")
            )
            tours = await guard_tour.list_tours(client)
            assert tours == []

    @pytest.mark.asyncio
    async def test_start_tour(self):
        """Should send Running=yes to start a tour."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text="OK")
            )
            await guard_tour.start_tour(client, "G0")

            url = str(route.calls[0].request.url)
            assert "action=update" in url
            assert "GuardTour.G0.Running=yes" in url

    @pytest.mark.asyncio
    async def test_stop_tour(self):
        """Should send Running=no to stop a tour."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/param.cgi").mock(
                return_value=httpx.Response(200, text="OK")
            )
            await guard_tour.stop_tour(client, "G1")

            url = str(route.calls[0].request.url)
            assert "action=update" in url
            assert "GuardTour.G1.Running=no" in url


# ---------------------------------------------------------------------------
# Siren & Light
# ---------------------------------------------------------------------------

class TestSirenAPI:
    @pytest.mark.asyncio
    async def test_get_status_idle(self):
        """Should return empty dict when idle."""
        mock_resp = {"apiVersion": "1.0", "method": "getStatus", "data": {}}
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            status = await siren.get_status(client)
            assert status == {}

    @pytest.mark.asyncio
    async def test_get_status_active(self):
        """Should return active siren/light details."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getStatus",
            "data": {
                "siren": [{"sirenId": 1, "pattern": "Alarm: Horror", "intensity": 5}],
                "light": [{"lightId": 2, "pattern": "Alternate", "colors": ["red", "blue"]}],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            status = await siren.get_status(client)
            assert len(status["siren"]) == 1
            assert status["siren"][0]["pattern"] == "Alarm: Horror"

    @pytest.mark.asyncio
    async def test_start_with_profile(self):
        """Should send profile name when using profile-based activation."""
        mock_resp = {"apiVersion": "1.0", "method": "start", "data": {"sirenId": 1, "lightId": 1}}
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await siren.start(client, profile="Intrusion Alert")
            assert result["sirenId"] == 1

            body = json.loads(route.calls[0].request.content)
            assert body["params"]["profile"] == "Intrusion Alert"

    @pytest.mark.asyncio
    async def test_start_direct(self):
        """Should send siren and light config directly."""
        mock_resp = {"apiVersion": "1.0", "method": "start", "data": {"sirenId": 1, "lightId": 2}}
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await siren.start(
                client,
                siren={"pattern": "Alarm: Car alarm", "intensity": 4},
                light={"pattern": "Pulse", "speed": 2, "colors": ["blue", "red"], "intensity": 1},
                duration=30,
            )
            assert result["sirenId"] == 1
            assert result["lightId"] == 2

            body = json.loads(route.calls[0].request.content)
            assert body["params"]["siren"]["pattern"] == "Alarm: Car alarm"
            assert body["params"]["siren"]["duration"] == {"unit": "seconds", "value": 30}
            assert body["params"]["light"]["colors"] == ["blue", "red"]

    @pytest.mark.asyncio
    async def test_stop(self):
        """Should stop all sirens and lights."""
        mock_resp = {"apiVersion": "1.0", "method": "stop", "data": {}}
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await siren.stop(client)

            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "stop"
            assert body["params"]["all"] == ["siren", "light"]

    @pytest.mark.asyncio
    async def test_get_profiles(self):
        """Should return saved profiles."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getProfiles",
            "data": {
                "profiles": [
                    {"name": "Intrusion", "siren": {"pattern": "Alarm: Horror"}, "light": {"pattern": "Alternate"}},
                ]
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/siren_and_light.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            profiles = await siren.get_profiles(client)
            assert len(profiles) == 1
            assert profiles[0]["name"] == "Intrusion"


# =============================================================================
# Edge Storage tests
# =============================================================================

DISK_LIST_XML = """<?xml version="1.0" ?>
<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <disks>
    <disk diskid="SD_DISK" name="SD card" totalsize="15558144"
          freesize="12345678" status="OK" filesystem="ext4"
          locked="NO" full="NO" readonly="NO"
          group="S0" cleanuppolicy="fifo" />
  </disks>
</root>"""

DISK_HEALTH_XML = """<?xml version="1.0"?>
<HealthStatusResponse xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:noNamespaceSchemaLocation="http://www.axis.com/vapix/http_cgi/disk/gethealth.xsd">
  <HealthStatusSuccess>
    <HealthStatus diskid="SD_DISK" wear="1"/>
    <HealthStatus diskid="NetworkShare" wear="-3"/>
  </HealthStatusSuccess>
</HealthStatusResponse>"""

RECORDINGS_XML = """<?xml version="1.0" ?>
<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:noNamespaceSchemaLocation="http://www.axis.com/vapix/http_cgi/recording/list1.xsd">
  <recordings totalnumberofrecordings="2" numberofrecordings="2">
    <recording diskid="SD_DISK"
      recordingid="20240115_081211_016F_00408C1834FD"
      starttime="2024-01-15T08:12:11Z"
      stoptime="2024-01-15T09:30:30Z"
      recordingtype="continuous"
      eventtrigger="continuous_0">
      <video mimetype="video/x-h264" width="1920" height="1080" framerate="30" />
      <audio mimetype="audio/axis-mulaw" samplerate="8000" />
    </recording>
    <recording diskid="SD_DISK"
      recordingid="20240115_093530_025B_00408C1834FD"
      starttime="2024-01-15T09:35:30Z"
      stoptime="2024-01-15T10:30:30Z"
      recordingtype="continuous"
      eventtrigger="continuous_0">
      <video mimetype="video/x-h264" width="1920" height="1080" framerate="30" />
    </recording>
  </recordings>
</root>"""

EXPORT_PROPS_XML = """<?xml version="1.0" encoding="utf-8"?>
<ExportRecordingResponse xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  SchemaVersion="1.1"
  xsi:noNamespaceSchemaLocation="http://www.axis.com/vapix/http_cgi/exportrecording1.xsd">
  <PropertiesSuccess>
    <ExportProperties RecordingId="20240115_081211_016F_00408C1834FD"
      ExportFormat="matroska" EstimatedFileSize="123456"
      Starttime="2024-01-15T08:12:11Z" Stoptime="2024-01-15T09:30:30Z"/>
  </PropertiesSuccess>
</ExportRecordingResponse>"""


class TestListDisks:
    @pytest.mark.asyncio
    async def test_list_disks(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/disks/list.cgi").mock(
                return_value=httpx.Response(200, text=DISK_LIST_XML,
                                           headers={"content-type": "text/xml"})
            )
            disks = await storage.list_disks(client)
            assert len(disks) == 1
            assert disks[0]["diskid"] == "SD_DISK"
            assert disks[0]["totalsize"] == "15558144"
            assert disks[0]["freesize"] == "12345678"
            assert disks[0]["status"] == "OK"
            assert disks[0]["filesystem"] == "ext4"

    @pytest.mark.asyncio
    async def test_list_disks_specific(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/disks/list.cgi").mock(
                return_value=httpx.Response(200, text=DISK_LIST_XML,
                                           headers={"content-type": "text/xml"})
            )
            await storage.list_disks(client, disk_id="SD_DISK")
            assert route.calls.last.request.url.params["diskid"] == "SD_DISK"


class TestDiskHealth:
    @pytest.mark.asyncio
    async def test_get_disk_health_xml(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/disks/gethealth.cgi").mock(
                return_value=httpx.Response(200, text=DISK_HEALTH_XML,
                                           headers={"content-type": "text/xml"})
            )
            health = await storage.get_disk_health(client)
            assert len(health) == 2
            assert health[0]["diskid"] == "SD_DISK"
            assert health[0]["wear"] == "1"
            assert health[1]["diskid"] == "NetworkShare"

    @pytest.mark.asyncio
    async def test_get_disk_health_json(self):
        json_resp = '{"data": {"disks": [{"diskid": "SD_DISK", "overallHealth": "OK", "wearLevel": 5}]}}'
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/disks/gethealth.cgi").mock(
                return_value=httpx.Response(200, text=json_resp,
                                           headers={"content-type": "application/json"})
            )
            health = await storage.get_disk_health(client)
            assert health[0]["diskid"] == "SD_DISK"
            assert health[0]["overallHealth"] == "OK"


class TestListRecordings:
    @pytest.mark.asyncio
    async def test_list_all_recordings(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/record/list.cgi").mock(
                return_value=httpx.Response(200, text=RECORDINGS_XML,
                                           headers={"content-type": "text/xml"})
            )
            recs = await storage.list_recordings(client)
            # First item is summary
            summary = recs[0]
            assert summary["_summary"] is True
            assert summary["total"] == 2
            assert summary["returned"] == 2
            # Actual recordings
            assert recs[1]["recordingid"] == "20240115_081211_016F_00408C1834FD"
            assert recs[1]["starttime"] == "2024-01-15T08:12:11Z"
            assert recs[1]["video"]["width"] == "1920"
            assert "audio" in recs[1]
            assert recs[2]["recordingid"] == "20240115_093530_025B_00408C1834FD"
            assert "audio" not in recs[2]

    @pytest.mark.asyncio
    async def test_list_recordings_with_filters(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/record/list.cgi").mock(
                return_value=httpx.Response(200, text=RECORDINGS_XML,
                                           headers={"content-type": "text/xml"})
            )
            await storage.list_recordings(
                client,
                disk_id="SD_DISK",
                start_time="2024-01-15T00:00:00Z",
                stop_time="2024-01-16T00:00:00Z",
                max_recordings=10,
            )
            params = route.calls.last.request.url.params
            assert params["diskid"] == "SD_DISK"
            assert params["starttime"] == "2024-01-15T00:00:00Z"
            assert params["stoptime"] == "2024-01-16T00:00:00Z"
            assert params["maxnumberofrecordings"] == "10"


class TestExportProperties:
    @pytest.mark.asyncio
    async def test_get_export_properties(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/record/export/properties.cgi").mock(
                return_value=httpx.Response(200, text=EXPORT_PROPS_XML,
                                           headers={"content-type": "text/xml"})
            )
            props = await storage.get_export_properties(
                client,
                recording_id="20240115_081211_016F_00408C1834FD",
                disk_id="SD_DISK",
            )
            assert props["RecordingId"] == "20240115_081211_016F_00408C1834FD"
            assert props["ExportFormat"] == "matroska"
            assert props["EstimatedFileSize"] == "123456"
            assert props["Starttime"] == "2024-01-15T08:12:11Z"
            assert props["Stoptime"] == "2024-01-15T09:30:30Z"

    @pytest.mark.asyncio
    async def test_get_export_properties_with_clip(self):
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/record/export/properties.cgi").mock(
                return_value=httpx.Response(200, text=EXPORT_PROPS_XML,
                                           headers={"content-type": "text/xml"})
            )
            await storage.get_export_properties(
                client,
                recording_id="20240115_081211_016F_00408C1834FD",
                disk_id="SD_DISK",
                start_time="2024-01-15T08:30:00Z",
                stop_time="2024-01-15T09:00:00Z",
            )
            params = route.calls.last.request.url.params
            assert params["starttime"] == "2024-01-15T08:30:00Z"
            assert params["stoptime"] == "2024-01-15T09:00:00Z"


# =============================================================================
# Clear View tests
# =============================================================================

CLEAR_VIEW_SERVICE_INFO_RESP = {
    "apiVersion": "1.0",
    "method": "getServiceInfo",
    "data": {
        "serviceInfo": [
            {
                "id": 0,
                "type": "wiper",
                "durationVariable": True,
                "durationMin": 5,
                "durationMax": 120,
                "durationDefault": 5,
                "idleTimeMin": 0,
                "stoppable": True,
            },
            {
                "id": 1,
                "type": "speeddry",
                "durationVariable": False,
                "durationDefault": 10,
                "idleTimeMin": 15,
                "stoppable": False,
            },
        ]
    },
}

CLEAR_VIEW_STATUS_IDLE = {
    "apiVersion": "1.0",
    "method": "getStatus",
    "data": {"state": "idle"},
}

CLEAR_VIEW_STATUS_RUNNING = {
    "apiVersion": "1.0",
    "method": "getStatus",
    "data": {"state": "running", "stopsIn": 23},
}

CLEAR_VIEW_START_RESP = {
    "apiVersion": "1.0",
    "method": "start",
    "data": {},
}

CLEAR_VIEW_STOP_RESP = {
    "apiVersion": "1.0",
    "method": "stop",
    "data": {},
}

CV_URL = f"{BASE_URL}/axis-cgi/clearviewcontrol.cgi"


class TestClearViewServiceInfo:
    @pytest.mark.asyncio
    async def test_get_service_info(self):
        """Should return list of available cleaning services."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_SERVICE_INFO_RESP)
            )
            services = await clear_view.get_service_info(client)
            assert len(services) == 2
            assert services[0]["type"] == "wiper"
            assert services[0]["id"] == 0
            assert services[0]["durationVariable"] is True
            assert services[0]["durationMin"] == 5
            assert services[0]["durationMax"] == 120
            assert services[0]["stoppable"] is True
            assert services[1]["type"] == "speeddry"
            assert services[1]["stoppable"] is False


class TestClearViewStatus:
    @pytest.mark.asyncio
    async def test_get_status_idle(self):
        """Should return idle state."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_STATUS_IDLE)
            )
            status = await clear_view.get_status(client, service_id=0)
            assert status["state"] == "idle"

    @pytest.mark.asyncio
    async def test_get_status_running(self):
        """Should return running state with stopsIn."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_STATUS_RUNNING)
            )
            status = await clear_view.get_status(client, service_id=0)
            assert status["state"] == "running"
            assert status["stopsIn"] == 23


class TestClearViewStart:
    @pytest.mark.asyncio
    async def test_start_default_duration(self):
        """Should start wiper with default duration."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_START_RESP)
            )
            await clear_view.start(client, service_id=0)
            body = json.loads(route.calls.last.request.content)
            assert body["method"] == "start"
            assert body["params"]["id"] == 0
            assert "duration" not in body["params"]

    @pytest.mark.asyncio
    async def test_start_custom_duration(self):
        """Should start wiper with specified duration."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_START_RESP)
            )
            await clear_view.start(client, service_id=0, duration=30)
            body = json.loads(route.calls.last.request.content)
            assert body["params"]["duration"] == 30

    @pytest.mark.asyncio
    async def test_start_speeddry(self):
        """Should start speed-dry service (id=1)."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_START_RESP)
            )
            await clear_view.start(client, service_id=1)
            body = json.loads(route.calls.last.request.content)
            assert body["params"]["id"] == 1


class TestClearViewStop:
    @pytest.mark.asyncio
    async def test_stop(self):
        """Should stop a running service."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(CV_URL).mock(
                return_value=httpx.Response(200, json=CLEAR_VIEW_STOP_RESP)
            )
            await clear_view.stop(client, service_id=0)
            body = json.loads(route.calls.last.request.content)
            assert body["method"] == "stop"
            assert body["params"]["id"] == 0


# =============================================================================
# Privacy Mask tests
# =============================================================================

PM_URL = f"{BASE_URL}/axis-cgi/privacymask.cgi"

PRIVACY_MASK_LIST_RESP = {
    "listpx": [
        {
            "id": 0,
            "name": "reception_window",
            "enabled": True,
            "zoomlowlimit": 0,
            "zoom_visible": True,
            "position": [
                {"x": 500, "y": 200},
                {"x": 800, "y": 200},
                {"x": 800, "y": 500},
                {"x": 500, "y": 500},
            ],
        },
        {
            "id": 1,
            "name": "license_plate",
            "enabled": False,
            "zoomlowlimit": 0,
            "position": [
                {"x": 100, "y": 100},
                {"x": 300, "y": 100},
                {"x": 300, "y": 200},
                {"x": 100, "y": 200},
            ],
        },
    ]
}


class TestListPrivacyMasks:
    @pytest.mark.asyncio
    async def test_list_masks(self):
        """Should return all masks with coordinates."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(PM_URL).mock(
                return_value=httpx.Response(200, json=PRIVACY_MASK_LIST_RESP)
            )
            masks = await privacy_mask.list_masks(client)
            assert len(masks) == 2
            assert masks[0]["name"] == "reception_window"
            assert masks[0]["enabled"] is True
            assert len(masks[0]["position"]) == 4
            assert masks[1]["name"] == "license_plate"
            assert masks[1]["enabled"] is False

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """Should return empty list when no masks configured."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(PM_URL).mock(
                return_value=httpx.Response(200, json={"listpx": []})
            )
            masks = await privacy_mask.list_masks(client)
            assert masks == []


class TestAddPrivacyMask:
    @pytest.mark.asyncio
    async def test_add_mask_width_height(self):
        """Should add mask with width/height in percent."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.add_mask(
                client, "test_mask", width=20.0, height=15.0
            )
            params = route.calls.last.request.url.params
            assert params["action"] == "add"
            assert params["name"] == "test_mask"
            assert params["width"] == "20.0"
            assert params["height"] == "15.0"

    @pytest.mark.asyncio
    async def test_add_mask_with_center(self):
        """Should add mask with center coordinates."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.add_mask(
                client, "centered_mask",
                width=10.0, height=10.0,
                center_x=30.0, center_y=40.0,
            )
            params = route.calls.last.request.url.params
            assert params["center"] == "30.0,40.0"

    @pytest.mark.asyncio
    async def test_add_mask_polygon(self):
        """Should add mask with pixel polygon."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            poly = "500,500:800,500:700,700:400,700"
            await privacy_mask.add_mask(client, "poly_mask", polygon=poly)
            params = route.calls.last.request.url.params
            assert params["pxpolygon"] == poly

    @pytest.mark.asyncio
    async def test_add_mask_no_position_raises(self):
        """Should raise ValueError if neither width/height nor polygon given."""
        client = VapixClient(_make_camera())
        with pytest.raises(ValueError, match="Must provide either"):
            await privacy_mask.add_mask(client, "bad_mask")

    @pytest.mark.asyncio
    async def test_add_mask_error_response(self):
        """Should raise on error text response."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(PM_URL).mock(
                return_value=httpx.Response(200, text="Error: Name already exists")
            )
            with pytest.raises(Exception, match="Name already exists"):
                await privacy_mask.add_mask(
                    client, "dup_mask", width=10.0, height=10.0
                )


class TestUpdatePrivacyMask:
    @pytest.mark.asyncio
    async def test_update_mask_position(self):
        """Should update mask with new position."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.update_mask(
                client, "test_mask", width=25.0, height=20.0,
                center_x=50.0, center_y=50.0,
            )
            params = route.calls.last.request.url.params
            assert params["action"] == "update"
            assert params["name"] == "test_mask"
            assert params["width"] == "25.0"
            assert params["center"] == "50.0,50.0"

    @pytest.mark.asyncio
    async def test_update_mask_polygon(self):
        """Should update mask with pixel polygon."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.update_mask(
                client, "test_mask",
                polygon="100,100:200,100:200,200:100,200",
            )
            params = route.calls.last.request.url.params
            assert params["action"] == "update"
            assert "pxpolygon" in params


class TestRemovePrivacyMask:
    @pytest.mark.asyncio
    async def test_remove_mask(self):
        """Should remove mask by name."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.remove_mask(client, "old_mask")
            params = route.calls.last.request.url.params
            assert params["action"] == "remove"
            assert params["name"] == "old_mask"

    @pytest.mark.asyncio
    async def test_remove_nonexistent_mask(self):
        """Should raise on error when mask doesn't exist."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(PM_URL).mock(
                return_value=httpx.Response(200, text="Error: Mask not found")
            )
            with pytest.raises(Exception, match="Mask not found"):
                await privacy_mask.remove_mask(client, "ghost_mask")


class TestEnableDisableAll:
    @pytest.mark.asyncio
    async def test_enable_all(self):
        """Should send enable_all action."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.enable_all(client)
            params = route.calls.last.request.url.params
            assert params["action"] == "enable_all"

    @pytest.mark.asyncio
    async def test_disable_all(self):
        """Should send disable_all action."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(PM_URL).mock(
                return_value=httpx.Response(204)
            )
            await privacy_mask.disable_all(client)
            params = route.calls.last.request.url.params
            assert params["action"] == "disable_all"
