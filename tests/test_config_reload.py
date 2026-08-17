"""
Tests for picking up cameras.yaml edits without restarting the server.

Cameras are added, renamed and removed with `vapx config …` while this server
is running. Before reloading existed, the file was read once at startup and
cached for the life of the process, so the server answered from a config that
no longer matched reality.
"""

import json

import pytest

import server as srv
from config import AppConfig, CameraConfig, load_config

CFG = """
cameras:
  west:
    host: "192.168.1.20"
    pass: "a"
  entren:
    host: "192.168.1.21"
    pass: "b"
"""


@pytest.fixture
def cfg_file(tmp_path):
    """A config file on disk, loaded into the server as if at startup."""
    path = tmp_path / "cameras.yaml"
    path.write_text(CFG)
    srv.config = load_config(path)
    srv._config_mtime = srv._mtime_of(srv.config.source)
    srv._clients.clear()
    yield path
    srv.config = None
    srv._config_mtime = None
    srv._clients.clear()


_TICK = [0]


def rewrite(path, text):
    """Write, and stamp a strictly newer mtime.

    Two writes in the same instant can land on the same timestamp, which is
    exactly what the reload check looks at — so the stamp is advanced by hand
    instead of being left to the clock.
    """
    import os
    import time

    path.write_text(text)
    _TICK[0] += 1
    stamp = time.time() + _TICK[0] * 10
    os.utime(path, (stamp, stamp))


async def camera_ids():
    result = await srv._dispatch_tool("list_cameras", {})
    return [c["id"] for c in json.loads(result[0].text)]


@pytest.mark.asyncio
async def test_removed_camera_disappears_without_restart(cfg_file):
    assert sorted(await camera_ids()) == ["entren", "west"]

    rewrite(cfg_file, """
cameras:
  west:
    host: "192.168.1.20"
    pass: "a"
""")

    assert await camera_ids() == ["west"]


@pytest.mark.asyncio
async def test_added_camera_appears_without_restart(cfg_file):
    rewrite(cfg_file, CFG + """  nykamera:
    host: "192.168.1.22"
    pass: "c"
""")

    assert "nykamera" in await camera_ids()


@pytest.mark.asyncio
async def test_untouched_file_is_not_reloaded(cfg_file):
    before = srv.config
    await srv._reload_config_if_changed()
    assert srv.config is before, "config was rebuilt even though the file did not change"


@pytest.mark.asyncio
async def test_unparsable_file_keeps_the_previous_config(cfg_file):
    """Someone saving a half-written file must not take the server down."""
    rewrite(cfg_file, "cameras: [[[ broken")

    await srv._reload_config_if_changed()

    assert sorted(c.id for c in srv.config.cameras) == ["entren", "west"]


@pytest.mark.asyncio
async def test_a_fixed_file_is_picked_up_after_a_bad_one(cfg_file):
    rewrite(cfg_file, "cameras: [[[ broken")
    await srv._reload_config_if_changed()

    rewrite(cfg_file, """
cameras:
  west:
    host: "192.168.1.20"
    pass: "a"
""")
    await srv._reload_config_if_changed()

    assert [c.id for c in srv.config.cameras] == ["west"]


@pytest.mark.asyncio
async def test_pooled_client_is_dropped_when_the_host_changes(cfg_file):
    """A cached client would keep talking to the old address."""
    camera = srv.config.get_camera("west")
    srv._clients["west"] = srv.VapixClient(camera)

    rewrite(cfg_file, """
cameras:
  west:
    host: "192.168.1.99"
    pass: "a"
  entren:
    host: "192.168.1.21"
    pass: "b"
""")
    await srv._reload_config_if_changed()

    assert "west" not in srv._clients
    assert srv.config.get_camera("west").host == "192.168.1.99"


@pytest.mark.asyncio
async def test_pooled_client_survives_an_unrelated_edit(cfg_file):
    camera = srv.config.get_camera("west")
    srv._clients["west"] = srv.VapixClient(camera)

    rewrite(cfg_file, CFG + """  nykamera:
    host: "192.168.1.22"
    pass: "c"
""")
    await srv._reload_config_if_changed()

    assert "west" in srv._clients, "unrelated camera lost its pooled connection"


@pytest.mark.asyncio
async def test_config_without_a_source_is_left_alone():
    """Configs built in memory (tests, embedding) have nothing to watch."""
    srv.config = AppConfig(
        cameras=[CameraConfig(id="c", name="C", host="10.0.0.1", password="p")]
    )
    srv._config_mtime = None

    await srv._reload_config_if_changed()  # must not raise

    assert srv.config.camera_ids() == ["c"]
