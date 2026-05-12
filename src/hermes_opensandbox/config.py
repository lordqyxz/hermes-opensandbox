"""Configuration value objects for the OpenSandbox backend."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_IMAGE = "nikolaik/python-nodejs:python3.11-nodejs20"
DEFAULT_DOMAIN = "localhost:8080"
DEFAULT_TIMEOUT = 300
DEFAULT_CPU = 1.0
DEFAULT_MEMORY_MB = 5120
DEFAULT_DISK_MB = 51200
DEFAULT_CWD = "/workspace"


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

    @classmethod
    def from_env(cls, **overrides: str | float | int | None) -> SandboxConfig:
        """Build config from environment variables, with *overrides* taking priority."""
        kwargs: dict[str, str | float | int] = {
            "image": os.getenv("OPENSANDBOX_IMAGE", DEFAULT_IMAGE),
            "domain": os.getenv("OPENSANDBOX_DOMAIN", DEFAULT_DOMAIN),
            "api_key": os.getenv("OPENSANDBOX_API_KEY", ""),
            "cwd": os.getenv("OPENSANDBOX_CWD", DEFAULT_CWD),
            "cpu": float(os.getenv("OPENSANDBOX_CPU", str(DEFAULT_CPU))),
            "memory": int(os.getenv("OPENSANDBOX_MEMORY", str(DEFAULT_MEMORY_MB))),
            "disk": int(os.getenv("OPENSANDBOX_DISK", str(DEFAULT_DISK_MB))),
            "task_id": os.getenv("OPENSANDBOX_TASK_ID", "default"),
        }
        for k, v in overrides.items():
            if v is not None:
                kwargs[k] = v
        return cls(**kwargs)  # type: ignore[arg-type]
