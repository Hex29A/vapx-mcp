"""
VAPX MCP Server — Configuration loading and validation.

Loads camera definitions from cameras.yaml, substitutes environment variables
in password fields (${ENV_VAR} syntax), and validates with Pydantic.
"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


def _substitute_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(
                f"Environment variable '{var_name}' is not set "
                f"(referenced in cameras.yaml)"
            )
        return env_val

    return re.sub(r"\$\{(\w+)\}", replacer, value)


class CameraConfig(BaseModel):
    """Configuration for a single Axis camera."""

    id: str = Field(..., description="Unique identifier used in tool calls")
    name: str = Field(..., description="Human-readable name")
    host: str = Field(..., description="IP or hostname (no protocol prefix)")
    port: Optional[int] = Field(default=None, description="HTTP(S) port. Defaults to 443 (HTTPS) or 80 (HTTP).")
    https: bool = Field(default=True, description="Use HTTPS")
    verify_ssl: bool = Field(
        default=False, description="Verify SSL certificate (false for self-signed)"
    )
    username: str = Field(default="root")
    password: str = Field(..., description="Password or ${ENV_VAR} reference")
    capabilities: list[str] = Field(
        default_factory=lambda: ["snapshot"],
        description="List of supported capabilities: snapshot, ptz, events, io, light",
    )

    @model_validator(mode="after")
    def set_default_port(self) -> "CameraConfig":
        if self.port is None:
            self.port = 443 if self.https else 80
        return self

    @field_validator("password", mode="before")
    @classmethod
    def resolve_password(cls, v: str) -> str:
        if "${" in v:
            return _substitute_env_vars(v)
        return v

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v.startswith(("http://", "https://")):
            raise ValueError("host should not include protocol (http:// or https://)")
        return v.rstrip("/")

    @property
    def base_url(self) -> str:
        scheme = "https" if self.https else "http"
        return f"{scheme}://{self.host}:{self.port}"


class AppConfig(BaseModel):
    """Top-level application configuration."""

    cameras: list[CameraConfig] = Field(
        ..., min_length=1, description="List of camera configurations"
    )

    def get_camera(self, camera_id: str) -> Optional[CameraConfig]:
        """Look up a camera by its id. Returns None if not found."""
        for cam in self.cameras:
            if cam.id == camera_id:
                return cam
        return None

    def camera_ids(self) -> list[str]:
        """Return all configured camera IDs."""
        return [cam.id for cam in self.cameras]


def _convert_vapx_format(raw: dict) -> dict:
    """Convert vapx map-style config to vapx-mcp list-style config.

    vapx format:
        defaults:
          user: root
          https: false
        cameras:
          west:
            host: "192.168.1.10"
            pass: "secret"

    Becomes:
        cameras:
          - id: west
            host: "192.168.1.10"
            password: "secret"
            username: "root"
            https: false
    """
    defaults = raw.get("defaults", {})
    cameras_dict = raw["cameras"]
    cameras_list = []

    for cam_id, cam_data in cameras_dict.items():
        if not isinstance(cam_data, dict):
            continue
        entry: dict = {"id": cam_id}

        # Apply defaults first, then camera-specific values override
        for key, val in defaults.items():
            if key == "user":
                entry.setdefault("username", val)
            elif key == "pass":
                entry.setdefault("password", val)
            else:
                entry.setdefault(key, val)

        for key, val in cam_data.items():
            if key == "pass":
                entry["password"] = val
            elif key == "user":
                entry["username"] = val
            else:
                entry[key] = val

        # Default name from id if not specified
        entry.setdefault("name", cam_id)

        cameras_list.append(entry)

    return {"cameras": cameras_list}


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """
    Load and validate camera configuration from a YAML file.

    Looks for config in this order:
    1. Explicit path argument
    2. VAPIX_CONFIG environment variable
    3. cameras.yaml in the current working directory
    4. /app/cameras.yaml (Docker default)

    Raises:
        FileNotFoundError: If no config file is found.
        ValueError: If config is invalid or env vars are missing.
    """
    search_paths = [
        config_path,
        os.environ.get("VAPIX_CONFIG"),
        Path("cameras.yaml"),
        Path("/app/cameras.yaml"),
    ]

    resolved_path = None
    for p in search_paths:
        if p is not None:
            p = Path(p)
            if p.is_file():
                resolved_path = p
                break

    if resolved_path is None:
        raise FileNotFoundError(
            "No cameras.yaml found. Searched: "
            + ", ".join(str(p) for p in search_paths if p)
        )

    with open(resolved_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict) or "cameras" not in raw:
        raise ValueError(
            f"Invalid config format in {resolved_path}: "
            "expected a 'cameras' key at the top level"
        )

    # Support vapx map format: cameras is a dict keyed by camera id
    cameras_raw = raw["cameras"]
    if isinstance(cameras_raw, dict):
        raw = _convert_vapx_format(raw)

    return AppConfig(**raw)
