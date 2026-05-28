"""
VAPIX User Management — List users and their group memberships.

Endpoint: GET /axis-cgi/admin/pwdgrp.cgi?action=get
Returns key=value lines: group="user1,user2,..."

Groups:
  admin    — full access
  operator — PTZ, stream, event config
  viewer   — live view only
  ptz      — PTZ control
  digusers — digest auth users

Ref: https://developer.axis.com/vapix/device-configuration/user-management-v2-api/
(Classic pwdgrp.cgi predates the v2 API and works on all firmware)
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/admin/pwdgrp.cgi"


async def get_users(client: VapixClient) -> dict[str, Any]:
    """
    List all users and their group memberships.

    Returns a dict with two keys:
      - groups: {group_name: [username, ...]} — who belongs to which group
      - users: {username: [group, ...]} — which groups each user has

    System service accounts (stsuser, AxisDeviceMgmt, pfagentvapix) are
    included but flagged with is_service=True.
    """
    _SERVICE_ACCOUNTS = {"stsuser", "AxisDeviceMgmt", "pfagentvapix"}

    resp = await client.get(_PATH, {"action": "get"})
    groups: dict[str, list[str]] = {}

    for line in resp.text.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        group, _, rest = line.partition("=")
        members = [u.strip() for u in rest.strip('"').split(",") if u.strip()]
        groups[group.strip()] = members

    # Build reverse index: user → groups
    user_groups: dict[str, list[str]] = {}
    for group, members in groups.items():
        for user in members:
            user_groups.setdefault(user, []).append(group)

    users = []
    for username, grps in sorted(user_groups.items()):
        users.append({
            "username": username,
            "groups": grps,
            "is_service_account": username in _SERVICE_ACCOUNTS,
        })

    return {
        "groups": groups,
        "users": users,
    }
