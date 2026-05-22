"""
VAPIX Stream Profiles — Manage video stream profiles (resolution, codec, FPS).

Endpoint: POST /axis-cgi/streamprofile.cgi
Docs: https://developer.axis.com/vapix/network-video/stream-profiles/

Stream profiles define presets for video streaming parameters.
Each profile has a name and URL-encoded parameter string.

Methods:
    list    — List all or specific stream profiles
    create  — Create a new profile with parameters
    remove  — Remove a profile by name
"""

from typing import Any

from .client import VapixClient

_PATH = "/axis-cgi/streamprofile.cgi"


async def list_profiles(
    client: VapixClient,
    name: str | None = None,
) -> dict[str, Any]:
    """
    List stream profiles.

    Args:
        name: Specific profile name to query. None = list all.

    Returns dict with:
        maxProfiles     — Maximum number of profiles supported
        streamProfile[] — List of profiles with name, description, parameters
    """
    profile_filter = []
    if name:
        profile_filter = [{"name": name}]

    payload = {
        "apiVersion": "1.0",
        "method": "list",
        "params": {"streamProfileName": profile_filter},
    }
    data = await client.post_json(_PATH, payload)
    return data["data"]


async def create_profile(
    client: VapixClient,
    name: str,
    parameters: str,
    description: str = "",
) -> None:
    """
    Create a new stream profile.

    Args:
        name: Unique profile name.
        parameters: URL-encoded parameter string
                    (e.g. "resolution=1920x1080&fps=30&videocodec=h264").
        description: Optional human-readable description.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "create",
        "params": {
            "streamProfile": [{
                "name": name,
                "description": description,
                "parameters": parameters,
            }],
        },
    }
    await client.post_json(_PATH, payload)


async def remove_profile(client: VapixClient, name: str) -> None:
    """
    Remove a stream profile by name.

    Args:
        name: Name of the profile to remove.
    """
    payload = {
        "apiVersion": "1.0",
        "method": "remove",
        "params": {
            "streamProfile": [{"name": name}],
        },
    }
    await client.post_json(_PATH, payload)
