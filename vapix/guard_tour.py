"""
VAPIX Guard Tour — Manage automated PTZ patrol routes.

Endpoint: GET /axis-cgi/param.cgi (parameter-based API)
Docs: https://developer.axis.com/vapix/network-video/guard-tour-api/

Guard tours use the legacy param.cgi interface with GuardTour parameter groups.
This is a different API style from the JSON POST APIs — it uses query parameters
and returns plain text responses.

Requires a PTZ camera with preset positions configured.
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/param.cgi"


async def list_tours(client: VapixClient) -> list[dict[str, Any]]:
    """
    List all configured guard tours with their parameters.

    Returns list of tour dicts with keys:
        id, name, running, camera, random_enabled, time_between
    """
    response = await client.get(_PATH, {"action": "list", "group": "GuardTour"})
    text = response.text.strip()

    if not text or "Error" in text:
        return []

    tours: dict[str, dict[str, Any]] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue

        key, _, value = line.partition("=")
        # Parse: root.GuardTour.G0.Name=DayTour
        parts = key.split(".")
        if len(parts) < 4 or parts[1] != "GuardTour":
            continue

        tour_id = parts[2]  # e.g. "G0"
        if tour_id not in tours:
            tours[tour_id] = {"id": tour_id, "presets": []}

        if len(parts) == 4:
            # Tour-level parameter
            param = parts[3]
            if param == "Name":
                tours[tour_id]["name"] = value
            elif param == "Running":
                tours[tour_id]["running"] = value.lower() == "yes"
            elif param == "CamNbr":
                tours[tour_id]["camera"] = int(value)
            elif param == "RandomEnabled":
                tours[tour_id]["random_enabled"] = value.lower() == "yes"
            elif param == "TimeBetweenSequences":
                tours[tour_id]["time_between"] = int(value)

        elif len(parts) >= 5 and parts[3] == "Tour":
            # Tour preset parameter: GuardTour.G0.Tour.T0.PresetNbr
            preset_id = parts[4] if len(parts) > 4 else None
            if preset_id and len(parts) == 6:
                param = parts[5]
                # Find or create the preset entry
                preset = None
                for p in tours[tour_id]["presets"]:
                    if p["id"] == preset_id:
                        preset = p
                        break
                if preset is None:
                    preset = {"id": preset_id}
                    tours[tour_id]["presets"].append(preset)

                if param == "PresetNbr":
                    preset["preset_number"] = int(value)
                elif param == "MoveSpeed":
                    preset["move_speed"] = int(value)
                elif param == "WaitTime":
                    preset["wait_time"] = int(value)

    return list(tours.values())


async def start_tour(client: VapixClient, tour_id: str) -> None:
    """
    Start a guard tour.

    Args:
        tour_id: Tour identifier, e.g. "G0", "G1".
    """
    await client.get(_PATH, {
        "action": "update",
        f"GuardTour.{tour_id}.Running": "yes",
    })


async def stop_tour(client: VapixClient, tour_id: str) -> None:
    """
    Stop a running guard tour.

    Args:
        tour_id: Tour identifier, e.g. "G0", "G1".
    """
    await client.get(_PATH, {
        "action": "update",
        f"GuardTour.{tour_id}.Running": "no",
    })
