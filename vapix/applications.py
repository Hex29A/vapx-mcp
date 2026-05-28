"""
VAPIX Application API — List and control ACAP applications.

Endpoint: /axis-cgi/applications/list.cgi    (list installed apps)
          /axis-cgi/applications/control.cgi  (start/stop/restart/remove)
Ref: https://developer.axis.com/vapix/applications/application-api/

list.cgi returns XML; control.cgi returns plain text "OK" or "Error: <code>".
"""

from typing import Any
from xml.etree import ElementTree as ET

from .client import VapixClient

_LIST_PATH = "/axis-cgi/applications/list.cgi"
_CONTROL_PATH = "/axis-cgi/applications/control.cgi"

_CONTROL_ERRORS = {
    "1": "Invalid application package or invalid manifest.",
    "4": "Application not found.",
    "6": "Application is already running.",
    "7": "Application not running (must be running to perform this action).",
    "9": "Too many applications running.",
    "10": "Unspecified error — check system log.",
    "15": "Operation timed out — check logs.",
}


async def list_applications(client: VapixClient) -> list[dict[str, Any]]:
    """
    List all installed ACAP applications and their status.

    Returns a list of dicts with: name, nice_name, vendor, version,
    status (Running/Stopped/Idle), license (Valid/None/Missing),
    signature (Signed/Unsigned), and resources.
    """
    resp = await client.post(_LIST_PATH)
    root = ET.fromstring(resp.text)
    if root.get("result") != "ok":
        raise ValueError("Application list returned error result")

    apps = []
    for app in root.findall("application"):
        resources = []
        for res in app.findall("Resources/Resource"):
            resources.append({
                "name": res.get("name"),
                "used": res.get("used"),
            })

        apps.append({
            "name": app.get("Name"),
            "nice_name": app.get("NiceName"),
            "vendor": app.get("Vendor"),
            "version": app.get("Version"),
            "status": app.get("Status"),
            "license": app.get("License"),
            "license_name": app.get("LicenseName"),
            "signature": app.get("SignatureStatus"),
            "config_page": app.get("ConfigurationPage"),
            "resources": resources,
        })
    return apps


async def control_application(
    client: VapixClient, action: str, package: str
) -> str:
    """
    Control an ACAP application: start, stop, restart, or remove.

    Args:
        action: One of "start", "stop", "restart", "remove"
        package: Application short name (e.g. "loitering_guard")

    Returns:
        "OK" on success.

    Raises:
        ValueError: If the camera returns an error code.
    """
    resp = await client._client.post(
        _CONTROL_PATH,
        params={"action": action, "package": package},
    )
    resp.raise_for_status()
    text = resp.text.strip()
    if text.startswith("Error:"):
        code = text.split(":")[-1].strip()
        msg = _CONTROL_ERRORS.get(code, f"Unknown error code {code}")
        raise ValueError(f"Application control failed: {msg}")
    return text
