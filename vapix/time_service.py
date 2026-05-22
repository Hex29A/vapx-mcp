"""
VAPIX Time Service — Get and set camera date, time, and timezone.

Endpoint: POST /axis-cgi/time.cgi
Docs: https://developer.axis.com/vapix/network-video/time-api/

Methods:
    getDateTimeInfo  — Current date/time, timezone, DST status
    getAll           — Same as above + list of all supported timezones
    setTimeZone      — Set timezone by IANA name (e.g. "Europe/Stockholm")
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/time.cgi"


async def get_date_time_info(client: VapixClient) -> dict[str, Any]:
    """
    Get current date/time info from the camera.

    Returns dict with:
        dateTime          — UTC time (ISO 8601)
        localDateTime     — Local time (ISO 8601)
        timeZone          — IANA timezone (e.g. "Europe/Stockholm")
        posixTimeZone     — POSIX timezone string
        dstEnabled        — Whether DST is active
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getDateTimeInfo",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def get_all(client: VapixClient) -> dict[str, Any]:
    """
    Get date/time info plus all supported timezones.

    Returns dict with dateTime info and timeZones list.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "getAll",
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def set_timezone(client: VapixClient, timezone: str) -> None:
    """
    Set the camera's timezone.

    Args:
        timezone: IANA timezone name (e.g. "Europe/Stockholm", "America/New_York").
    """
    payload = {
        "apiVersion": "1.0",
        "method": "setTimeZone",
        "params": {"timeZone": timezone},
    }
    await client.post_json(_PATH, payload)
