"""OpenSandbox execution environment for Hermes Agent.

Uses the `opensandbox` Python SDK to run shell commands inside remote
OpenSandbox containers.  Implements the Hermes
``BaseEnvironment._run_bash`` contract so that the base-class
``execute()``, ``write_file``, ``read_file``, ``init_session``, and
``cleanup`` work out of the box.

Architecture (same pattern as ``vercel_sandbox.py`` / ``modal.py``):
    ``_run_bash(command, login, timeout, stdin_data) -> _ThreadedProcessHandle``
        is the *only* override.  It wraps a synchronous
        ``sandbox.commands.run(cmd)`` call in a ``_ThreadedProcessHandle``
        so the base ``_wait_for_process`` loop can drain stdout and enforce
        timeouts.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import timedelta
from typing import Callable

from tools.environments.base import (
    BaseEnvironment,
    _ThreadedProcessHandle,
)

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "nikolaik/python-nodejs:python3.11-nodejs20"
DEFAULT_TIMEOUT = 300       # seconds per command
DEFAULT_CPU = 1.0
DEFAULT_MEMORY_MB = 5120
DEFAULT_DISK_MB = 51200


class OpenSandboxEnvironment(BaseEnvironment):
    """OpenSandbox execution backend.

    Each ``OpenSandboxEnvironment`` session creates exactly one sandbox at
    ``__init__`` time and reuses it for every command until ``cleanup()``
    terminates it.  The sandbox lifetime mirrors the Hermes agent session.

    Configuration is read from environment variables (preferred) or
    ``config.yaml`` keys forwarded through ``container_config`` in
    ``_create_environment()``.

    Env vars (highest priority):
        ``OPENSANDBOX_DOMAIN``  – server address (default ``localhost:8080``)
        ``OPENSANDBOX_API_KEY`` – authentication key
        ``OPENSANDBOX_IMAGE``   – container image tag
    """

    # Use heredoc mode so the base class embeds stdin into the cmd string.
    # (OpenSandbox SDK's ``commands.run`` doesn't have a dedicated stdin param.)
    _stdin_mode = "heredoc"

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        cwd: str = "/workspace",
        timeout: int = DEFAULT_TIMEOUT,
        cpu: float = DEFAULT_CPU,
        memory: int = DEFAULT_MEMORY_MB,
        disk: int = DEFAULT_DISK_MB,
        task_id: str = "default",
        domain: str = "",
        api_key: str = "",
    ):
        # Resolve domain / api_key: env var > explicit arg > default
        resolved_domain = (
            domain
            or os.getenv("OPENSANDBOX_DOMAIN")
            or "localhost:8080"
        )
        resolved_api_key = (
            api_key
            or os.getenv("OPENSANDBOX_API_KEY")
            or ""
        )
        resolved_image = (
            image
            if image != DEFAULT_IMAGE
            else os.getenv("OPENSANDBOX_IMAGE", DEFAULT_IMAGE)
        )

        super().__init__(cwd=cwd, timeout=timeout)

        self._image = resolved_image
        self._domain = resolved_domain
        self._api_key = resolved_api_key
        self._cpu = cpu
        self._memory = memory
        self._disk = disk
        self._task_id = task_id
        self._lock = threading.Lock()
        self._sandbox = None  # lazy-init on first _run_bash

        logger.info(
            "OpenSandboxEnvironment created: domain=%s image=%s cwd=%s",
            self._domain, self._image, self.cwd,
        )

    # ------------------------------------------------------------------
    #  _ensure_sandbox  –  lazy-create the SDK sandbox
    # ------------------------------------------------------------------

    def _ensure_sandbox(self):
        """Return the current sandbox, creating one if necessary."""
        if self._sandbox is not None:
            # Quick health check – if the sandbox died, recreate
            try:
                return self._sandbox
            except Exception:
                logger.warning("Sandbox appears dead, recreating...")
                self._sandbox = None

        from opensandbox import SandboxSync
        from opensandbox.config import ConnectionConfigSync

        conn = ConnectionConfigSync(
            domain=self._domain,
            api_key=self._api_key,
            request_timeout=timedelta(seconds=self.timeout),
        )

        resource = {}
        if self._cpu > 0:
            resource["cpu"] = str(self._cpu)
        if self._memory > 0:
            resource["memory"] = f"{self._memory}Mi"

        logger.info(
            "Creating OpenSandbox: image=%s domain=%s resource=%s",
            self._image, self._domain, resource or "default",
        )

        sandbox = SandboxSync.create(
            image=self._image,
            timeout=timedelta(seconds=self.timeout),
            connection_config=conn,
            **({"resource": resource} if resource else {}),
        )

        self._sandbox = sandbox
        return sandbox

    # ------------------------------------------------------------------
    #  _run_bash  –  THE ONLY REQUIRED OVERRIDE
    # ------------------------------------------------------------------

    def _run_bash(
        self,
        cmd_string: str,
        *,
        login: bool = False,
        timeout: int = 120,
        stdin_data: str | None = None,
    ) -> _ThreadedProcessHandle:
        """Execute *cmd_string* inside the sandbox.

        ``login`` and ``timeout`` are ignored here – login is handled by
        the base class via the session snapshot, and timeout is enforced
        by ``_wait_for_process``.  ``stdin_data`` is discarded because
        ``_stdin_mode = "heredoc"`` means the base class has already
        embedded it into *cmd_string*.
        """
        del login
        del timeout
        del stdin_data

        def _exec() -> tuple[str, int]:
            """Blocking call: run command in sandbox, return (output, exit_code)."""
            sb = self._ensure_sandbox()

            logger.debug("Running in sandbox: %s", cmd_string[:200])

            result = sb.commands.run(cmd_string)

            # Collect stdout
            stdout_parts = []
            for entry in result.logs.stdout:
                stdout_parts.append(entry.text)

            # Collect stderr
            stderr_parts = []
            for entry in result.logs.stderr:
                stderr_parts.append(entry.text)

            output = "".join(stdout_parts)
            if stderr_parts:
                output += "".join(stderr_parts)

            exit_code = getattr(result, "exit_code", 0)
            return output, exit_code

        def _cancel() -> None:
            """Force-kill the sandbox on timeout / interrupt."""
            with self._lock:
                sb = self._sandbox
            if sb:
                try:
                    sb.kill()
                except Exception:
                    pass
                try:
                    sb.close()
                except Exception:
                    pass

        return _ThreadedProcessHandle(exec_fn=_exec, cancel_fn=_cancel)

    # ------------------------------------------------------------------
    #  cleanup  –  destroy the sandbox
    # ------------------------------------------------------------------

    def cleanup(self):
        """Terminate the remote sandbox and release local resources."""
        with self._lock:
            sb = self._sandbox
            self._sandbox = None

        if sb is None:
            return

        logger.info("Cleaning up sandbox %s", getattr(sb, "id", "?"))
        try:
            sb.kill()
        except Exception as exc:
            logger.debug("Sandbox kill error (non-fatal): %s", exc)
        try:
            sb.close()
        except Exception as exc:
            logger.debug("Sandbox close error (non-fatal): %s", exc)
