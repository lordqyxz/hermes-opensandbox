"""Configuration value objects for the OpenSandbox backend."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "nikolaik/python-nodejs:python3.11-nodejs20"
DEFAULT_DOMAIN = "localhost:8080"
DEFAULT_TIMEOUT = 86400
DEFAULT_CPU = 0.5
DEFAULT_MEMORY_MB = 512
DEFAULT_DISK_MB = 5000
DEFAULT_RENEW_INTERVAL = 600
DEFAULT_CWD = "/workspace"

_DEFAULT_CONFIG_PATH = Path.home() / ".hermes" / "opensandbox.yaml"


def _resolve_config_path() -> Path | None:
    """Return the config file path to use, or *None* if none exists.

    Resolution order:

    1. ``OPENSANDBOX_CONFIG`` environment variable (explicit path)
    2. ``~/.hermes/opensandbox.yaml`` (default, next to Hermes config)
    """
    env_path = os.getenv("OPENSANDBOX_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        logger.warning("OPENSANDBOX_CONFIG=%s does not exist, ignoring", env_path)
        return None
    if _DEFAULT_CONFIG_PATH.is_file():
        return _DEFAULT_CONFIG_PATH
    return None


def _parse_mounts(raw: str) -> dict[str, str]:
    """Parse a comma-separated ``host:mount`` string into a dict."""
    result: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            host, mount = part.split(":", 1)
            result[host.strip()] = mount.strip()
        else:
            result[part] = part
    return result


def _parse_volumes(raw: str) -> list[dict[str, Any]]:
    """Parse a JSON array of volume specifications.

    Each element is a dict matching the OpenSandbox SDK ``Volume`` model:

    .. code-block:: json

        [
          {
            "name": "models-vol",
            "pvc": {"claimName": "juicefs-models", "storageClass": "juicefs-sc"},
            "mountPath": "/mnt/models",
            "subPath": "v2/checkpoints",
            "readOnly": true
          }
        ]

    Supports three mutually-exclusive backends: ``host``, ``pvc``, ``ossfs``.
    """
    parsed: list[dict[str, Any]] = json.loads(raw)
    return parsed


def _load_yaml_config(path: Path) -> dict[str, Any]:
    """Load a YAML config file and return its contents as a dict."""
    with path.open("r", encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        logger.warning("Config file %s is not a mapping, ignoring", path)
        return {}
    return cast(dict[str, Any], data)


@dataclass
class SandboxConfig:
    """Configuration for an OpenSandbox session."""

    image: str = DEFAULT_IMAGE
    domain: str = DEFAULT_DOMAIN
    api_key: str = ""
    cwd: str = DEFAULT_CWD
    timeout: int = DEFAULT_TIMEOUT
    cpu: float = DEFAULT_CPU
    memory: int = DEFAULT_MEMORY_MB
    disk: int = DEFAULT_DISK_MB
    task_id: str = "default"
    mounts: dict[str, str] | None = None
    volumes: list[dict[str, Any]] | None = None
    debug: bool = False

    @classmethod
    def from_file(cls, path: Path | None = None) -> dict[str, Any]:
        """Load config values from a YAML file.

        Returns a dict of field values (only keys present in the file are
        included).  Returns an empty dict if no file is found or the file
        is empty.
        """
        if path is None:
            resolved = _resolve_config_path()
            if resolved is None:
                return {}
            path = resolved
        if not path.is_file():
            return {}
        logger.info("Loading sandbox config from %s", path)
        raw = _load_yaml_config(path)
        result: dict[str, Any] = {}
        _FIELD_MAP: dict[str, type] = {
            "image": str,
            "domain": str,
            "api_key": str,
            "cwd": str,
            "timeout": int,
            "cpu": float,
            "memory": int,
            "disk": int,
            "task_id": str,
            "debug": bool,
        }
        for key, expected_type in _FIELD_MAP.items():
            if key in raw and raw[key] is not None:
                result[key] = expected_type(raw[key])
        if "mounts" in raw and raw["mounts"] is not None:
            m: Any = raw["mounts"]
            if isinstance(m, dict):
                m_typed = cast(dict[str, Any], m)
                result["mounts"] = {str(k): str(v) for k, v in m_typed.items()}
            elif isinstance(m, str):
                result["mounts"] = _parse_mounts(m)
        if "volumes" in raw and raw["volumes"] is not None:
            v = raw["volumes"]
            if isinstance(v, list):
                result["volumes"] = v
            elif isinstance(v, str):
                result["volumes"] = _parse_volumes(v)
        return result

    @classmethod
    def from_env(cls, **overrides: str | float | int | None) -> SandboxConfig:
        """Build config from config file + environment variables.

        Priority (highest → lowest):
            *overrides* > ``OPENSANDBOX_*`` env vars > config file > code defaults
        """
        file_values = cls.from_file()

        mounts_raw = os.getenv("OPENSANDBOX_MOUNTS", "")
        mounts = _parse_mounts(mounts_raw) if mounts_raw else None
        volumes_raw = os.getenv("OPENSANDBOX_VOLUMES", "")
        volumes = _parse_volumes(volumes_raw) if volumes_raw else None

        env_values: dict[str, Any] = {
            "image": os.getenv("OPENSANDBOX_IMAGE"),
            "domain": os.getenv("OPENSANDBOX_DOMAIN"),
            "api_key": os.getenv("OPENSANDBOX_API_KEY"),
            "cwd": os.getenv("OPENSANDBOX_CWD"),
            "cpu": os.getenv("OPENSANDBOX_CPU"),
            "memory": os.getenv("OPENSANDBOX_MEMORY"),
            "disk": os.getenv("OPENSANDBOX_DISK"),
            "timeout": os.getenv("OPENSANDBOX_TIMEOUT"),
            "task_id": os.getenv("OPENSANDBOX_TASK_ID"),
            "mounts": mounts,
            "volumes": volumes,
            "debug": os.getenv("OPENSANDBOX_DEBUG"),
        }

        env_typed: dict[str, Any] = {}
        _TYPE_MAP: dict[str, type] = {
            "cpu": float,
            "memory": int,
            "disk": int,
            "timeout": int,
        }
        for k, v in env_values.items():
            if v is None or v == "":
                continue
            if k == "debug":
                env_typed[k] = v in ("1", "true", "yes")
            elif k in _TYPE_MAP:
                env_typed[k] = _TYPE_MAP[k](v)
            else:
                env_typed[k] = v

        kwargs: dict[str, Any] = file_values.copy()
        kwargs.update(env_typed)
        for k, v in overrides.items():
            if v is not None:
                kwargs[k] = v
        return cls(**kwargs)  # type: ignore[arg-type]
