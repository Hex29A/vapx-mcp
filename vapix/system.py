"""
VAPIX System utilities — reboot, system log, audit log, systemready.

APIs used:
  - Firmware management API (firmwaremanagement.cgi) — reboot
    Ref: https://developer.axis.com/vapix/network-video/firmware-management-api/
  - System log (admin/systemlog.cgi) — plain-text log
  - Audit log (auditlog.cgi) — plain-text security audit log
    Ref: https://developer.axis.com/vapix/network-video/audit-log/
  - Systemready API (systemready.cgi) — readiness probe
    Ref: https://developer.axis.com/vapix/network-video/systemready-api/
"""

from typing import Any

from .client import VapixClient

_FWMGR_PATH = "/axis-cgi/firmwaremanagement.cgi"
_SYSLOG_PATH = "/axis-cgi/admin/systemlog.cgi"
_AUDITLOG_PATH = "/axis-cgi/auditlog.cgi"
_SYSTEMREADY_PATH = "/axis-cgi/systemready.cgi"


async def reboot(client: VapixClient) -> dict[str, Any]:
    """
    Reboot the camera using firmwaremanagement.cgi (fw 7.40+).
    Falls back to legacy restart.cgi on older firmware.

    Returns a dict with "status" and "method" keys.
    Camera will be unreachable for ~30-60 seconds after this call.
    """
    try:
        result = await client.post_json(
            _FWMGR_PATH,
            {
                "apiVersion": "1.0",
                "context": "vapx-mcp",
                "method": "reboot",
            },
        )
        return {"status": "rebooting", "method": "firmwaremanagement"}
    except Exception:
        # Legacy fallback: restart.cgi (pre-fw 7.40)
        await client.post("/axis-cgi/restart.cgi")
        return {"status": "rebooting", "method": "restart.cgi (legacy)"}


async def get_system_log(client: VapixClient, lines: int | None = None) -> str:
    """
    Retrieve the system log from admin/systemlog.cgi.

    Args:
        lines: If set, return only the last N lines. Default: full log.

    Returns:
        Log content as a plain-text string.
    """
    resp = await client.get(_SYSLOG_PATH)
    text = resp.text
    if lines is not None and lines > 0:
        all_lines = text.splitlines()
        text = "\n".join(all_lines[-lines:])
    return text


async def get_audit_log(client: VapixClient, lines: int | None = None) -> str:
    """
    Retrieve the audit log from auditlog.cgi.

    Args:
        lines: If set, return only the last N lines. Default: full log.

    Returns security audit events (logins, config changes) as plain text.
    """
    resp = await client.get(_AUDITLOG_PATH)
    text = resp.text
    if lines is not None and lines > 0:
        all_lines = text.splitlines()
        text = "\n".join(all_lines[-lines:])
    return text


async def check_systemready(client: VapixClient, timeout: int = 10) -> dict[str, Any]:
    """
    Check if the device is ready to handle requests via systemready.cgi.

    Args:
        timeout: Max seconds to wait for readiness (default 10).

    Returns:
        Dict with systemready (yes/no), needsetup (yes/no), uptime (seconds),
        and bootid.
    """
    result = await client.post_json(
        _SYSTEMREADY_PATH,
        {
            "apiVersion": "1.1",
            "context": "vapx-mcp",
            "method": "systemready",
            "params": {"timeout": timeout},
        },
    )
    return result.get("data", result)
