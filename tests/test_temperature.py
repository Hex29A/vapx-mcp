"""
Tests for the temperature sensor VAPIX module.

Uses respx to mock HTTP responses — no real cameras needed.
"""

import httpx
import pytest
import respx

from config import CameraConfig
from vapix import temperature
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
        capabilities=["snapshot", "temperature"],
    )
    defaults.update(overrides)
    return CameraConfig(**defaults)


BASE_URL = "https://192.168.1.100:443"


class TestTemperatureAPI:
    @pytest.mark.asyncio
    async def test_get_sensor_list_multiple_sensors(self):
        """Should parse multiple sensors with both C and F."""
        mock_response = (
            "Sensor.S0.Name=CPU\n"
            "Sensor.S0.Celsius=42.50\n"
            "Sensor.S1.Name=Main\n"
            "Sensor.S1.Celsius=35.00\n"
            "Heater.H0.Status=Stopped\n"
        )
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/temperaturecontrol.cgi").mock(
                return_value=httpx.Response(200, text=mock_response)
            )
            async with VapixClient(cam) as client:
                result = await temperature.get_sensor_list(client)

        assert len(result["sensors"]) == 2
        assert result["sensors"][0]["name"] == "CPU"
        assert result["sensors"][0]["celsius"] == 42.50
        assert result["sensors"][0]["fahrenheit"] == 108.50
        assert result["sensors"][1]["name"] == "Main"
        assert result["sensors"][1]["celsius"] == 35.00
        assert result["sensors"][1]["fahrenheit"] == 95.00

        assert len(result["heaters"]) == 1
        assert result["heaters"][0]["status"] == "Stopped"

    @pytest.mark.asyncio
    async def test_get_sensor_list_single_sensor_no_heater(self):
        """Should handle single sensor with no heater."""
        mock_response = "Sensor.S0.Name=ImageSensor\nSensor.S0.Celsius=28.75\n"
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/temperaturecontrol.cgi").mock(
                return_value=httpx.Response(200, text=mock_response)
            )
            async with VapixClient(cam) as client:
                result = await temperature.get_sensor_list(client)

        assert len(result["sensors"]) == 1
        assert result["sensors"][0]["name"] == "ImageSensor"
        assert result["sensors"][0]["celsius"] == 28.75
        assert result["sensors"][0]["fahrenheit"] == 83.75
        assert result["heaters"] == []

    @pytest.mark.asyncio
    async def test_get_sensor_list_multiple_heaters(self):
        """Should parse multiple heaters."""
        mock_response = (
            "Sensor.S0.Name=Front\n"
            "Sensor.S0.Celsius=10.00\n"
            "Heater.H0.Status=Running\n"
            "Heater.H1.Status=Stopped\n"
        )
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/temperaturecontrol.cgi").mock(
                return_value=httpx.Response(200, text=mock_response)
            )
            async with VapixClient(cam) as client:
                result = await temperature.get_sensor_list(client)

        assert len(result["heaters"]) == 2
        assert result["heaters"][0]["status"] == "Running"
        assert result["heaters"][1]["status"] == "Stopped"

    @pytest.mark.asyncio
    async def test_fahrenheit_conversion_freezing(self):
        """0°C should equal 32°F."""
        mock_response = "Sensor.S0.Name=Test\nSensor.S0.Celsius=0.00\n"
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/temperaturecontrol.cgi").mock(
                return_value=httpx.Response(200, text=mock_response)
            )
            async with VapixClient(cam) as client:
                result = await temperature.get_sensor_list(client)

        assert result["sensors"][0]["celsius"] == 0.00
        assert result["sensors"][0]["fahrenheit"] == 32.00

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Empty response should return empty lists."""
        cam = _make_camera()
        with respx.mock:
            respx.post(f"{BASE_URL}/axis-cgi/temperaturecontrol.cgi").mock(
                return_value=httpx.Response(200, text="")
            )
            async with VapixClient(cam) as client:
                result = await temperature.get_sensor_list(client)

        assert result["sensors"] == []
        assert result["heaters"] == []


class TestParseResponse:
    """Unit tests for the parser function directly."""

    def test_negative_celsius(self):
        text = "Sensor.S0.Name=Lens\nSensor.S0.Celsius=-5.50\n"
        result = temperature._parse_sensor_response(text)
        assert result["sensors"][0]["celsius"] == -5.50
        assert result["sensors"][0]["fahrenheit"] == 22.10

    def test_ignores_malformed_lines(self):
        text = "garbage line\nno-equals-here\nSensor.S0.Name=CPU\nSensor.S0.Celsius=40.00\n"
        result = temperature._parse_sensor_response(text)
        assert len(result["sensors"]) == 1
        assert result["sensors"][0]["name"] == "CPU"
