"""
Tests for the new VAPIX API modules: time_service, daynight, stream_profiles,
geolocation, audio, storage (export), events.

Uses respx to mock HTTP responses — no real cameras needed.
"""

import json
import os

import httpx
import pytest
import respx

from config import CameraConfig
from vapix import audio, daynight, geolocation, storage, stream_profiles, time_service
from vapix.client import VapixClient


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
        capabilities=[
            "snapshot", "ptz", "io", "light", "storage",
            "time", "daynight", "stream_profiles", "geolocation", "audio", "events",
        ],
    )
    defaults.update(overrides)
    return CameraConfig(**defaults)


BASE_URL = "https://192.168.1.100:443"


# ---------------------------------------------------------------------------
# Time API
# ---------------------------------------------------------------------------

class TestTimeAPI:
    @pytest.mark.asyncio
    async def test_get_date_time_info(self):
        """Should return date/time and timezone info."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getDateTimeInfo",
            "data": {
                "dateTime": {
                    "dateTime": "2024-06-15T10:30:00Z",
                    "localDateTime": "2024-06-15T12:30:00+02:00",
                    "timeZone": "Europe/Stockholm",
                    "posixTimeZone": "CET-1CEST,M3.5.0,M10.5.0/3",
                    "dstEnabled": True,
                }
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/time.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await time_service.get_date_time_info(client)
            assert result["dateTime"]["timeZone"] == "Europe/Stockholm"
            assert result["dateTime"]["dstEnabled"] is True

    @pytest.mark.asyncio
    async def test_get_all(self):
        """Should return date/time info plus timezone list."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getAll",
            "data": {
                "dateTime": {
                    "dateTime": "2024-06-15T10:30:00Z",
                    "timeZone": "Europe/Stockholm",
                },
                "timeZones": ["Europe/Stockholm", "America/New_York", "Asia/Tokyo"],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/time.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await time_service.get_all(client)
            assert "timeZones" in result
            assert "Europe/Stockholm" in result["timeZones"]

    @pytest.mark.asyncio
    async def test_set_timezone(self):
        """Should set timezone without error."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "setTimeZone",
            "data": {},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/time.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await time_service.set_timezone(client, "America/New_York")
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["timeZone"] == "America/New_York"


# ---------------------------------------------------------------------------
# Day/Night API
# ---------------------------------------------------------------------------

class TestDayNightAPI:
    @pytest.mark.asyncio
    async def test_get_capabilities(self):
        """Should return day/night feature support."""
        mock_resp = {
            "apiVersion": "1.2",
            "method": "getCapabilities",
            "data": {
                "AutotuneSupport": True,
                "IrPassSupport": True,
                "NightDayShiftLevelSupport": True,
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/daynight.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await daynight.get_capabilities(client)
            assert result["AutotuneSupport"] is True
            assert result["IrPassSupport"] is True

    @pytest.mark.asyncio
    async def test_get_configuration(self):
        """Should return current day/night settings."""
        mock_resp = {
            "apiVersion": "1.2",
            "method": "getConfiguration",
            "data": {
                "DayNightShiftLevel": 50,
                "DayNightDwellTime": 5,
                "NightDayShiftLevel": 50,
                "NightDayDwellTime": 5,
                "Autotune": True,
                "NightFilter": "irpass",
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/daynight.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await daynight.get_configuration(client)
            assert result["DayNightShiftLevel"] == 50
            assert result["NightFilter"] == "irpass"
            assert result["Autotune"] is True

    @pytest.mark.asyncio
    async def test_set_configuration(self):
        """Should send correct settings payload."""
        mock_resp = {
            "apiVersion": "1.2",
            "method": "setConfiguration",
            "data": {},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/daynight.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await daynight.set_configuration(
                client, channel=0,
                DayNightShiftLevel=70,
                Autotune=False,
            )
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["DayNightShiftLevel"] == 70
            assert body["params"]["Autotune"] is False
            assert body["params"]["channel"] == 0


# ---------------------------------------------------------------------------
# Stream Profiles API
# ---------------------------------------------------------------------------

class TestStreamProfilesAPI:
    @pytest.mark.asyncio
    async def test_list_profiles(self):
        """Should return list of stream profiles."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "list",
            "data": {
                "maxProfiles": 26,
                "streamProfile": [
                    {
                        "name": "Profile1",
                        "description": "High quality",
                        "parameters": "resolution=1920x1080&fps=30&videocodec=h264",
                    },
                    {
                        "name": "Profile2",
                        "description": "Low bandwidth",
                        "parameters": "resolution=640x480&fps=15&videocodec=h264",
                    },
                ],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/streamprofile.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await stream_profiles.list_profiles(client)
            assert result["maxProfiles"] == 26
            assert len(result["streamProfile"]) == 2
            assert result["streamProfile"][0]["name"] == "Profile1"

    @pytest.mark.asyncio
    async def test_list_specific_profile(self):
        """Should query specific profile by name."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "list",
            "data": {
                "maxProfiles": 26,
                "streamProfile": [
                    {
                        "name": "Profile1",
                        "description": "High quality",
                        "parameters": "resolution=1920x1080",
                    },
                ],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/streamprofile.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await stream_profiles.list_profiles(client, name="Profile1")
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["streamProfileName"] == [{"name": "Profile1"}]

    @pytest.mark.asyncio
    async def test_create_profile(self):
        """Should create a profile with correct parameters."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "create",
            "data": {},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/streamprofile.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await stream_profiles.create_profile(
                client,
                name="TestProfile",
                parameters="resolution=1920x1080&fps=30",
                description="Test profile",
            )
            body = json.loads(route.calls[0].request.content)
            assert body["method"] == "create"
            profile = body["params"]["streamProfile"][0]
            assert profile["name"] == "TestProfile"
            assert "resolution=1920x1080" in profile["parameters"]

    @pytest.mark.asyncio
    async def test_remove_profile(self):
        """Should remove a profile by name."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "remove",
            "data": {},
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/streamprofile.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await stream_profiles.remove_profile(client, "TestProfile")
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["streamProfile"][0]["name"] == "TestProfile"


# ---------------------------------------------------------------------------
# Geolocation API
# ---------------------------------------------------------------------------

class TestGeolocationAPI:
    @pytest.mark.asyncio
    async def test_get_location(self):
        """Should parse XML geolocation response."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <GeolocationInfo>
            <Lat>59.3293</Lat>
            <Lng>18.0686</Lng>
            <Heading>180.0</Heading>
            <Text>Office entrance</Text>
            <ValidPosition>true</ValidPosition>
            <ValidHeading>true</ValidHeading>
        </GeolocationInfo>"""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/geolocation/get.cgi").mock(
                return_value=httpx.Response(200, text=xml_response)
            )
            result = await geolocation.get_location(client)
            assert result["Lat"] == 59.3293
            assert result["Lng"] == 18.0686
            assert result["Heading"] == 180.0
            assert result["Text"] == "Office entrance"
            assert result["ValidPosition"] is True

    @pytest.mark.asyncio
    async def test_get_location_empty(self):
        """Should handle empty geolocation gracefully."""
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <GeolocationInfo>
            <Lat></Lat>
            <Lng></Lng>
            <Heading></Heading>
            <Text></Text>
            <ValidPosition>false</ValidPosition>
            <ValidHeading>false</ValidHeading>
        </GeolocationInfo>"""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/geolocation/get.cgi").mock(
                return_value=httpx.Response(200, text=xml_response)
            )
            result = await geolocation.get_location(client)
            assert result["ValidPosition"] is False
            assert result["Lat"] == ""

    @pytest.mark.asyncio
    async def test_set_location(self):
        """Should send correct query params for set."""
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/geolocation/set.cgi").mock(
                return_value=httpx.Response(200, text="OK")
            )
            await geolocation.set_location(
                client, lat=59.3293, lng=18.0686, heading=180.0, text="Office"
            )
            request = route.calls[0].request
            assert "lat=59.3293" in str(request.url)
            assert "lng=18.0686" in str(request.url)

    @pytest.mark.asyncio
    async def test_set_location_error(self):
        """Should raise on error response."""
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/geolocation/set.cgi").mock(
                return_value=httpx.Response(200, text="Error: invalid parameter")
            )
            with pytest.raises(Exception, match="Geolocation error"):
                await geolocation.set_location(client, lat=999.0)


# ---------------------------------------------------------------------------
# Audio Control API
# ---------------------------------------------------------------------------

class TestAudioAPI:
    @pytest.mark.asyncio
    async def test_get_capabilities(self):
        """Should return audio device capabilities."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getDevicesCapabilities",
            "data": {
                "devices": [{
                    "deviceId": 0,
                    "inputs": [{
                        "inputId": 0,
                        "connectionTypes": [{
                            "connectionType": "internal",
                            "signalingTypes": [{
                                "signalingType": "digital",
                                "gainValues": [-12, -6, 0, 6, 12],
                            }],
                        }],
                    }],
                }],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/audiodevicecontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await audio.get_capabilities(client)
            assert len(result["devices"]) == 1
            assert result["devices"][0]["deviceId"] == 0

    @pytest.mark.asyncio
    async def test_get_settings(self):
        """Should return current audio settings."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "getDevicesSettings",
            "data": {
                "devices": [{
                    "deviceId": 0,
                    "inputs": [{
                        "inputId": 0,
                        "connectionType": "internal",
                        "signalingType": "digital",
                        "channels": [{"channelId": 0, "gain": 6, "mute": False}],
                    }],
                }],
            },
        }
        client = VapixClient(_make_camera())
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/audiodevicecontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            result = await audio.get_settings(client)
            device = result["devices"][0]
            assert device["inputs"][0]["channels"][0]["gain"] == 6
            assert device["inputs"][0]["channels"][0]["mute"] is False

    @pytest.mark.asyncio
    async def test_set_settings(self):
        """Should send device settings correctly."""
        mock_resp = {
            "apiVersion": "1.0",
            "method": "setDevicesSettings",
            "data": {},
        }
        devices_payload = [{
            "deviceId": 0,
            "inputs": [{
                "inputId": 0,
                "channels": [{"channelId": 0, "gain": 12, "mute": True}],
            }],
        }]
        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.post(f"{BASE_URL}/axis-cgi/audiodevicecontrol.cgi").mock(
                return_value=httpx.Response(200, json=mock_resp)
            )
            await audio.set_settings(client, devices=devices_payload)
            body = json.loads(route.calls[0].request.content)
            assert body["params"]["devices"][0]["deviceId"] == 0


# ---------------------------------------------------------------------------
# Recording Export
# ---------------------------------------------------------------------------

class TestRecordingExport:
    @pytest.mark.asyncio
    async def test_export_recording(self, tmp_path):
        """Should download binary content and save to file."""
        fake_mkv = b"\x1a\x45\xdf\xa3" * 100  # Fake MKV header bytes
        output_path = str(tmp_path / "test_recording.mkv")

        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/record/export/exportrecording.cgi").mock(
                return_value=httpx.Response(
                    200,
                    content=fake_mkv,
                    headers={"content-type": "video/x-matroska"},
                )
            )
            result = await storage.export_recording(
                client,
                recording_id="20240615_123000_ABCD",
                disk_id="SD_DISK",
                output_path=output_path,
            )
            assert result["path"] == output_path
            assert result["size_bytes"] == len(fake_mkv)
            assert os.path.exists(output_path)
            with open(output_path, "rb") as f:
                assert f.read() == fake_mkv

    @pytest.mark.asyncio
    async def test_export_recording_with_clip(self, tmp_path):
        """Should pass start/stop time params for partial export."""
        output_path = str(tmp_path / "clip.mkv")
        fake_mkv = b"\x1a\x45\xdf\xa3" * 50

        client = VapixClient(_make_camera())
        with respx.mock:
            route = respx.get(f"{BASE_URL}/axis-cgi/record/export/exportrecording.cgi").mock(
                return_value=httpx.Response(
                    200,
                    content=fake_mkv,
                    headers={"content-type": "video/x-matroska"},
                )
            )
            result = await storage.export_recording(
                client,
                recording_id="rec1",
                disk_id="SD_DISK",
                output_path=output_path,
                start_time="2024-06-15T10:00:00Z",
                stop_time="2024-06-15T10:05:00Z",
            )
            request = route.calls[0].request
            assert "starttime=" in str(request.url)
            assert "stoptime=" in str(request.url)
            assert result["size_bytes"] == len(fake_mkv)

    @pytest.mark.asyncio
    async def test_export_recording_xml_error(self, tmp_path):
        """Should raise on XML error response."""
        output_path = str(tmp_path / "fail.mkv")
        error_xml = '<ExportResult><Error code="4001" message="Recording not found"/></ExportResult>'

        client = VapixClient(_make_camera())
        with respx.mock:
            respx.get(f"{BASE_URL}/axis-cgi/record/export/exportrecording.cgi").mock(
                return_value=httpx.Response(
                    200,
                    text=error_xml,
                    headers={"content-type": "text/xml"},
                )
            )
            with pytest.raises(Exception, match="Export error"):
                await storage.export_recording(
                    client,
                    recording_id="nonexistent",
                    disk_id="SD_DISK",
                    output_path=output_path,
                )


# ---------------------------------------------------------------------------
# Server tool dispatch tests (new tools)
# ---------------------------------------------------------------------------

class TestServerNewTools:
    """Test that server.py correctly dispatches the new tools."""

    @pytest.mark.asyncio
    async def test_tool_list_includes_new_tools(self):
        """All new tool names should be in the tools list."""
        from server import TOOLS
        tool_names = {t.name for t in TOOLS}
        new_tools = {
            "export_recording", "get_time_info", "set_timezone",
            "get_daynight_config", "set_daynight_config",
            "list_stream_profiles", "create_stream_profile", "remove_stream_profile",
            "get_geolocation", "set_geolocation",
            "get_audio_settings", "set_audio_settings",
            "poll_events",
        }
        for tool in new_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

    @pytest.mark.asyncio
    async def test_tool_count_is_correct(self):
        """Should have 65 tools total (61 previous + 4 new system tools)."""
        from server import TOOLS
        assert len(TOOLS) == 65, f"Expected 65 tools, got {len(TOOLS)}"
