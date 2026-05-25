"""
Tests for config.py — Configuration loading and validation.

Tests cover:
    - Loading valid YAML config
    - Environment variable substitution in passwords
    - Validation errors (missing fields, bad host format)
    - Config file search order
    - Camera lookup by ID
"""

import os
from unittest.mock import patch

import pytest

from config import AppConfig, CameraConfig, _substitute_env_vars, load_config

# ---------------------------------------------------------------------------
# Environment variable substitution
# ---------------------------------------------------------------------------

class TestEnvVarSubstitution:
    def test_substitutes_single_var(self):
        with patch.dict(os.environ, {"MY_PASS": "secret123"}):
            assert _substitute_env_vars("${MY_PASS}") == "secret123"

    def test_substitutes_multiple_vars(self):
        with patch.dict(os.environ, {"USER": "admin", "PASS": "s3cret"}):
            result = _substitute_env_vars("${USER}:${PASS}")
            assert result == "admin:s3cret"

    def test_no_substitution_needed(self):
        assert _substitute_env_vars("plaintext") == "plaintext"

    def test_missing_env_var_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove the var if it exists
            os.environ.pop("NONEXISTENT_VAR_12345", None)
            with pytest.raises(ValueError, match="NONEXISTENT_VAR_12345"):
                _substitute_env_vars("${NONEXISTENT_VAR_12345}")


# ---------------------------------------------------------------------------
# CameraConfig validation
# ---------------------------------------------------------------------------

class TestCameraConfig:
    def test_valid_camera(self):
        cam = CameraConfig(
            id="test-cam",
            name="Test Camera",
            host="192.168.1.100",
            password="mypassword",
        )
        assert cam.id == "test-cam"
        assert cam.port == 443  # default
        assert cam.https is True  # default
        assert cam.verify_ssl is False  # default
        assert cam.username == "root"  # default
        assert cam.base_url == "https://192.168.1.100:443"
        assert "snapshot" in cam.capabilities  # default

    def test_http_camera(self):
        cam = CameraConfig(
            id="http-cam",
            name="HTTP Camera",
            host="10.0.0.1",
            port=80,
            https=False,
            password="pass",
        )
        assert cam.base_url == "http://10.0.0.1:80"

    def test_password_env_var_substitution(self):
        with patch.dict(os.environ, {"CAM_PASS": "env_password"}):
            cam = CameraConfig(
                id="env-cam",
                name="Env Camera",
                host="1.2.3.4",
                password="${CAM_PASS}",
            )
            assert cam.password == "env_password"

    def test_host_rejects_protocol_prefix(self):
        with pytest.raises(ValueError, match="should not include protocol"):
            CameraConfig(
                id="bad",
                name="Bad",
                host="https://192.168.1.1",
                password="x",
            )

    def test_host_strips_trailing_slash(self):
        cam = CameraConfig(
            id="slash",
            name="Slash",
            host="192.168.1.1/",
            password="x",
        )
        assert cam.host == "192.168.1.1"

    def test_custom_capabilities(self):
        cam = CameraConfig(
            id="ptz-cam",
            name="PTZ",
            host="10.0.0.1",
            password="x",
            capabilities=["snapshot", "ptz", "light"],
        )
        assert cam.capabilities == ["snapshot", "ptz", "light"]


# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------

class TestAppConfig:
    def _make_config(self, cameras=None):
        if cameras is None:
            cameras = [
                CameraConfig(id="cam-1", name="Cam 1", host="1.1.1.1", password="p1"),
                CameraConfig(id="cam-2", name="Cam 2", host="2.2.2.2", password="p2"),
            ]
        return AppConfig(cameras=cameras)

    def test_get_camera_found(self):
        cfg = self._make_config()
        cam = cfg.get_camera("cam-1")
        assert cam is not None
        assert cam.name == "Cam 1"

    def test_get_camera_not_found(self):
        cfg = self._make_config()
        assert cfg.get_camera("nonexistent") is None

    def test_camera_ids(self):
        cfg = self._make_config()
        assert cfg.camera_ids() == ["cam-1", "cam-2"]

    def test_empty_cameras_rejected(self):
        with pytest.raises(ValueError):
            AppConfig(cameras=[])


# ---------------------------------------------------------------------------
# load_config from YAML file
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path):
        yaml_content = """
cameras:
  - id: test-cam
    name: "Test"
    host: "192.168.1.1"
    port: 443
    https: true
    verify_ssl: false
    username: root
    password: "testpass"
    capabilities:
      - snapshot
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert len(cfg.cameras) == 1
        assert cfg.cameras[0].id == "test-cam"
        assert cfg.cameras[0].password == "testpass"

    def test_load_with_env_vars(self, tmp_path):
        yaml_content = """
cameras:
  - id: env-cam
    name: "Env"
    host: "10.0.0.1"
    password: "${TEST_CAM_PASSWORD}"
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        with patch.dict(os.environ, {"TEST_CAM_PASSWORD": "from_env"}):
            cfg = load_config(config_file)
            assert cfg.cameras[0].password == "from_env"

    def test_missing_config_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VAPIX_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)  # empty dir — no cameras.yaml here
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/cameras.yaml")

    def test_invalid_yaml_structure(self, tmp_path):
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text("not_cameras: []")

        with pytest.raises(ValueError, match="expected a 'cameras' key"):
            load_config(config_file)


# ---------------------------------------------------------------------------
# vapx config format support
# ---------------------------------------------------------------------------

class TestVapxConfigFormat:
    def test_vapx_map_format_basic(self, tmp_path):
        """vapx-style dict cameras should be converted to list format."""
        yaml_content = """
cameras:
  west:
    host: "192.168.1.10"
    port: 8011
    pass: "secret123"
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert len(cfg.cameras) == 1
        cam = cfg.cameras[0]
        assert cam.id == "west"
        assert cam.name == "west"
        assert cam.host == "192.168.1.10"
        assert cam.port == 8011
        assert cam.password == "secret123"

    def test_vapx_defaults_applied(self, tmp_path):
        """defaults section should apply to all cameras."""
        yaml_content = """
defaults:
  user: admin
  https: false
  verify_ssl: false

cameras:
  cam1:
    host: "10.0.0.1"
    pass: "pass1"
  cam2:
    host: "10.0.0.2"
    pass: "pass2"
    user: "operator"
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert len(cfg.cameras) == 2

        cam1 = cfg.get_camera("cam1")
        assert cam1.username == "admin"
        assert cam1.https is False

        cam2 = cfg.get_camera("cam2")
        assert cam2.username == "operator"  # camera-level overrides default

    def test_vapx_format_with_capabilities(self, tmp_path):
        """vapx format should pass through capabilities if specified."""
        yaml_content = """
cameras:
  mycam:
    host: "192.168.1.1"
    pass: "x"
    capabilities:
      - snapshot
      - ptz
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert cfg.cameras[0].capabilities == ["snapshot", "ptz"]

    def test_vapx_no_capabilities_gets_default(self, tmp_path):
        """vapx format without capabilities should get default ['snapshot']."""
        yaml_content = """
cameras:
  nocaps:
    host: "192.168.1.1"
    pass: "x"
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert cfg.cameras[0].capabilities == ["snapshot"]

    def test_original_list_format_still_works(self, tmp_path):
        """Original vpx-mcp list format should still work."""
        yaml_content = """
cameras:
  - id: front
    name: "Front Door"
    host: "192.168.1.100"
    password: "pass"
    capabilities:
      - snapshot
      - ptz
"""
        config_file = tmp_path / "cameras.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert cfg.cameras[0].id == "front"
        assert cfg.cameras[0].capabilities == ["snapshot", "ptz"]
