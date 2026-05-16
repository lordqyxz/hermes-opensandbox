"""OpenSandbox session — pure SDK wrapper with zero Hermes Agent dependencies.

Usage:

    from hermes_opensandbox import OpenSandboxSession, SandboxConfig

    config = SandboxConfig.from_env(domain="api.example.com:8080", api_key="sk-xxx")
    with OpenSandboxSession(config) as session:
        session.create()
        output, exit_code = session.execute("echo hello")
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from hermes_opensandbox.config import SandboxConfig

logger = logging.getLogger(__name__)


class SandboxError(RuntimeError):
    """Base for all sandbox-related errors."""


class SandboxNotCreatedError(SandboxError):
    """Raised when trying to use a session before :meth:`create` was called."""


class SandboxCreationError(SandboxError):
    """Raised when the sandbox fails to create (image, network, or config issue)."""


class SandboxImageError(SandboxCreationError):
    """Raised when the sandbox image is unavailable or incompatible."""


class SandboxNetworkError(SandboxCreationError):
    """Raised when the sandbox API endpoint is unreachable."""


class SandboxAuthError(SandboxCreationError):
    """Raised when API authentication fails."""


class OpenSandboxSession:
    """Manages the lifecycle of a single OpenSandbox container.

    Each instance wraps one remote sandbox.  Call :meth:`create` first,
    then :meth:`execute` as many times as needed, and finally :meth:`kill`
    followed by :meth:`close` (or use the context manager for ``close``).

    This class has **no dependency on Hermes Agent internals** — it only
    talks to the ``opensandbox`` SDK.
    """

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
        self._sandbox: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def sandbox_id(self) -> str | None:
        """The remote sandbox ID, or ``None`` if not yet created."""
        sb = self._sandbox
        return sb.id if sb is not None else None

    def create(self) -> None:
        """Create the remote sandbox and wait for it to become ready.

        Imports the OpenSandbox SDK lazily — no import cost until this
        backend is actually used.

        :raises SandboxImageError: image not found, pull failed, or incompatible
        :raises SandboxNetworkError: API endpoint unreachable
        :raises SandboxAuthError: invalid or missing API key
        :raises SandboxCreationError: other creation failures
        """
        if self._sandbox is not None:
            return

        from opensandbox.sync.sandbox import (  # type: ignore[import-untyped]  # noqa: PLC0415
            SandboxSync,
        )
        from opensandbox.config.connection_sync import (  # type: ignore[import-untyped]  # noqa: PLC0415
            ConnectionConfigSync,
        )
        from opensandbox.exceptions import (  # noqa: PLC0415
            SandboxReadyTimeoutException,
            SandboxApiException,
            SandboxInternalException,
        )
        import httpx

        conn = ConnectionConfigSync(
            domain=self._config.domain,
            api_key=self._config.api_key,
            request_timeout=timedelta(seconds=60),
        )

        resource: dict[str, str] = {}
        if self._config.cpu > 0:
            resource["cpu"] = str(self._config.cpu)
        if self._config.memory > 0:
            resource["memory"] = f"{self._config.memory}Mi"

        volumes: list[Any] = []
        mounts = self._config.mounts or {}
        for host_path, mount_path in mounts.items():
            try:
                from opensandbox.models.sandboxes import (  # noqa: PLC0415
                    Host,
                    Volume,
                )

                volumes.append(
                    Volume(
                        name=f"host-{len(volumes)}",
                        host=Host(path=host_path),
                        mountPath=mount_path,
                    )
                )
            except ImportError:
                pass
        for vol_spec in self._config.volumes or []:
            try:
                from opensandbox.models.sandboxes import (  # noqa: PLC0415
                    Host,
                    OSSFS,
                    PVC,
                    Volume,
                )

                backend_kwargs: dict[str, Any] = {}
                if "host" in vol_spec:
                    backend_kwargs["host"] = Host(**vol_spec["host"])
                if "pvc" in vol_spec:
                    backend_kwargs["pvc"] = PVC(**vol_spec["pvc"])
                if "ossfs" in vol_spec:
                    backend_kwargs["ossfs"] = OSSFS(**vol_spec["ossfs"])
                volumes.append(
                    Volume(
                        name=vol_spec["name"],
                        mountPath=vol_spec["mountPath"],
                        readOnly=vol_spec.get("readOnly", False),
                        subPath=vol_spec.get("subPath"),
                        **backend_kwargs,
                    )
                )
            except ImportError:
                pass
        if volumes:
            logger.info(
                "Mounts: %s",
                {
                    v.name: {
                        **({"host": v.host.path} if v.host else {}),
                        **({"pvc": v.pvc.claim_name} if v.pvc else {}),
                        **({"ossfs": v.ossfs.bucket} if v.ossfs else {}),
                        "mountPath": v.mount_path,
                        **({"subPath": v.sub_path} if v.sub_path else {}),
                    }
                    for v in volumes
                },
            )

        logger.info(
            "Creating OpenSandbox: image=%s domain=%s resource=%s",
            self._config.image,
            self._config.domain,
            resource or "default",
        )

        try:
            sb = SandboxSync.create(
                image=self._config.image,
                timeout=timedelta(seconds=self._config.timeout),
                connection_config=conn,
                resource=resource,
                volumes=volumes or None,
            )
        except SandboxReadyTimeoutException as e:
            raise SandboxImageError(
                f"Sandbox image '{self._config.image}' failed to become ready within "
                f"{self._config.timeout}s. The image may be incompatible with the "
                f"OpenSandbox runtime (requires execd sidecar support). "
                f"Check that the image exists and includes a working shell."
            ) from e
        except SandboxApiException as e:
            status = getattr(e, "status_code", None)
            if status in (401, 403):
                raise SandboxAuthError(
                    f"Authentication failed for OpenSandbox API at "
                    f"'{self._config.domain}'. Check OPENSANDBOX_API_KEY."
                ) from e
            raise SandboxCreationError(
                f"OpenSandbox API error (status={status}): {e}"
            ) from e
        except httpx.ConnectError as e:
            raise SandboxNetworkError(
                f"Cannot reach OpenSandbox API at '{self._config.domain}'. "
                f"Check OPENSANDBOX_DOMAIN and network connectivity."
            ) from e
        except SandboxInternalException as e:
            raise SandboxNetworkError(
                f"Cannot reach OpenSandbox API at '{self._config.domain}'. "
                f"Check OPENSANDBOX_DOMAIN and network connectivity. "
                f"Details: {e}"
            ) from e
        except Exception as e:
            raise SandboxCreationError(
                f"Failed to create sandbox with image '{self._config.image}': {e}"
            ) from e

        self._sandbox = sb
        logger.info("Sandbox %s ready", sb.id)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, command: str) -> tuple[str, int]:
        """Run *command* inside the sandbox.

        Returns ``(output, exit_code)``.  Raises :exc:`SandboxNotCreatedError`
        if :meth:`create` hasn't been called.
        """
        sb = self._sandbox
        if sb is None:
            raise SandboxNotCreatedError("Call create() before execute()")

        logger.debug("Running in sandbox %s: %.200s", sb.id, command)

        result = sb.commands.run(command)
        stdout_text = [entry.text for entry in result.logs.stdout]
        stderr_text = [entry.text for entry in result.logs.stderr]

        output = "".join(stdout_text)
        if stderr_text:
            output += "".join(stderr_text)

        exit_code = int(getattr(result, "exit_code", 0))
        return output, exit_code

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def renew(self) -> None:
        """Extend the sandbox expiration to prevent auto-termination.

        Uses the OpenSandbox renewal API to bump the expiration time
        by :attr:`SandboxConfig.timeout` seconds from now.
        """
        sb = self._sandbox
        if sb is None:
            return
        try:
            sb.renew(timedelta(seconds=self._config.timeout))
            logger.debug("Renewed sandbox %s", sb.id)
        except Exception:
            logger.debug("renew() raised (ignored)", exc_info=True)

    def is_alive(self) -> bool:
        """Return ``True`` if the sandbox exists and has not been killed."""
        return self._sandbox is not None

    def kill(self) -> None:
        """Terminate the remote sandbox (irreversible).

        In debug mode the sandbox is kept alive for inspection.
        """
        sb = self._sandbox
        if sb is None:
            return
        if self._config.debug:
            logger.info("Debug mode: keeping sandbox %s alive (skip kill)", sb.id)
            return
        logger.info("Killing sandbox %s", sb.id)
        try:
            sb.kill()
        except Exception:
            logger.debug("kill() raised (ignored)", exc_info=True)

    def close(self) -> None:
        """Release local HTTP resources. Safe to call multiple times.

        In debug mode the sandbox is kept alive for inspection.
        """
        sb = self._sandbox
        if sb is None:
            return
        if self._config.debug:
            logger.info("Debug mode: keeping sandbox %s alive (skip close)", sb.id)
            self._sandbox = None
            return
        try:
            sb.close()
        except Exception:
            logger.debug("close() raised (ignored)", exc_info=True)
        self._sandbox = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> OpenSandboxSession:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
