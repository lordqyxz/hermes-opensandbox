"""OpenSandbox execution backend for Hermes Agent.

Usage:

    from hermes_opensandbox.environment import OpenSandboxEnvironment

    env = OpenSandboxEnvironment(
        domain="your-server:8080",
        api_key="sk-xxx",
        image="python:3.11",
        cwd="/workspace",
        timeout=300,
    )
    result = env.execute("echo hello")
    env.cleanup()
"""

from hermes_opensandbox.environment import OpenSandboxEnvironment

__version__ = "0.1.0"
__all__ = ["OpenSandboxEnvironment"]
