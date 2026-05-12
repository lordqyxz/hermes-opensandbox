"""OpenSandbox execution backend for Hermes Agent.

Usage:

    from hermes_opensandbox import OpenSandboxSession, SandboxConfig

    config = SandboxConfig.from_env(
        domain="your-server:8080",
        api_key="sk-xxx",
    )
    with OpenSandboxSession(config) as session:
        session.create()
        output, exit_code = session.execute("echo hello")
        session.kill()
"""

from hermes_opensandbox.config import SandboxConfig
from hermes_opensandbox.session import (
    OpenSandboxSession,
    SandboxNotCreatedError,
    SandboxCreationError,
    SandboxImageError,
    SandboxNetworkError,
    SandboxAuthError,
)

__version__ = "0.1.0"
__all__ = [
    "OpenSandboxSession",
    "SandboxConfig",
    "SandboxNotCreatedError",
    "SandboxCreationError",
    "SandboxImageError",
    "SandboxNetworkError",
    "SandboxAuthError",
]
