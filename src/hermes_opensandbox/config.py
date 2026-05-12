"""Configuration value objects for the OpenSandbox backend."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_IMAGE = "nikolaik/python-nodejs:python3.11-nodejs20"
DEFAULT_DOMAIN = "localhost:8080"
DEFAULT_TIMEOUT = 86400  # 24h sandbox lifetime before auto-close
DEFAULT_CPU = 1.0
DEFAULT_MEMORY_MB = 5120
DEFAULT_DISK_MB = 51200
DEFAULT_CWD = "/workspace"

# Default host paths to mount into the sandbox (host_path → mount_path).
# The mount_path mirrors the host_path so absolute paths work transparently.
DEFAULT_MOUNTS: dict[str, str] = {
    os.path.expanduser("~"): os.path.expanduser("~"),
}

# Additional commonly needed paths on macOS.
_macos_common = [
    "/tmp",
    "/var/folders",
]
for _p in _macos_common:
    if os.path.exists(_p):
        DEFAULT_MOUNTS[_p] = _p


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
    debug: bool = False

    @classmethod
    def from_env(cls, **overrides: str | float | int | None) -> SandboxConfig:
        """Build config from environment variables, with *overrides* taking priority."""
        mounts_raw = os.getenv("OPENSANDBOX_MOUNTS", "")
        mounts = _parse_mounts(mounts_raw) if mounts_raw else dict(DEFAULT_MOUNTS)
        kwargs: dict[str, str | float | int | object] = {
            "image": os.getenv("OPENSANDBOX_IMAGE", DEFAULT_IMAGE),
            "domain": os.getenv("OPENSANDBOX_DOMAIN", DEFAULT_DOMAIN),
            "api_key": os.getenv("OPENSANDBOX_API_KEY", ""),
            "cwd": os.getenv("OPENSANDBOX_CWD", DEFAULT_CWD),
            "cpu": float(os.getenv("OPENSANDBOX_CPU", str(DEFAULT_CPU))),
            "memory": int(os.getenv("OPENSANDBOX_MEMORY", str(DEFAULT_MEMORY_MB))),
            "disk": int(os.getenv("OPENSANDBOX_DISK", str(DEFAULT_DISK_MB))),
            "task_id": os.getenv("OPENSANDBOX_TASK_ID", "default"),
            "mounts": mounts,
            "debug": os.getenv("OPENSANDBOX_DEBUG", "") in ("1", "true", "yes"),
        }
        for k, v in overrides.items():
            if v is not None:
                kwargs[k] = v
        return cls(**kwargs)  # type: ignore[arg-type]
