"""
VAPIX Temperature Control — Read temperature sensor data.

Endpoint: POST /axis-cgi/temperaturecontrol.cgi
Docs: https://developer.axis.com/vapix/network-video/temperature-control/

Returns per-sensor readings (CPU, Main, Front, IR, Lens, etc.)
and heater status from Axis cameras running AXIS OS 12.x+.

Response format (legacy key=value):
    Sensor.S0.Name=CPU
    Sensor.S0.Celsius=30.24
    Sensor.S0.Fahrenheit=86.43
    Heater.H0.Status=Stopped
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/temperaturecontrol.cgi"


def _parse_sensor_response(text: str) -> dict[str, Any]:
    """Parse key=value response into structured sensor/heater data."""
    sensors: dict[int, dict[str, Any]] = {}
    heaters: dict[int, dict[str, Any]] = {}

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")

        if key.startswith("Sensor.S"):
            # e.g. Sensor.S0.Name=CPU  or  Sensor.S0.Celsius=30.24
            parts = key.split(".")
            if len(parts) < 3:
                continue
            idx = int(parts[1][1:])  # "S0" → 0
            field = parts[2]
            sensors.setdefault(idx, {})
            if field == "Celsius":
                celsius = float(value)
                sensors[idx]["celsius"] = round(celsius, 2)
                # Fallback conversion — only used if the camera does not send
                # its own Sensor.SX.Fahrenheit line (handled below).
                sensors[idx].setdefault(
                    "fahrenheit", round(celsius * 9 / 5 + 32, 2)
                )
            elif field == "Fahrenheit":
                # Some cameras report Fahrenheit directly. Parse it as a number
                # so both celsius and fahrenheit are always floats, never strings.
                sensors[idx]["fahrenheit"] = round(float(value), 2)
            else:
                sensors[idx][field.lower()] = value

        elif key.startswith("Heater.H"):
            # e.g. Heater.H0.Status=Stopped
            parts = key.split(".")
            if len(parts) < 3:
                continue
            idx = int(parts[1][1:])  # "H0" → 0
            field = parts[2]
            heaters.setdefault(idx, {})
            heaters[idx][field.lower()] = value

    return {
        "sensors": [sensors[k] for k in sorted(sensors)],
        "heaters": [heaters[k] for k in sorted(heaters)],
    }


async def get_sensor_list(client: VapixClient) -> dict[str, Any]:
    """
    Get all temperature sensors and heater statuses.

    Returns dict with:
        sensors — list of {name, celsius, fahrenheit}
        heaters — list of {status}
    """
    resp = await client.post(
        _PATH,
        data={"method": "getSensorList"},
    )
    return _parse_sensor_response(resp.text)
