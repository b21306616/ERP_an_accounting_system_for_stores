"""Windows service installation and control helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ctypes
import os
from pathlib import Path
import site
import sys
import time
from types import ModuleType, SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from server_app.core.config import AppConfig
from server_app.core.constants import APP_NAME
from server_app.core.network import check_tcp_port, is_port_bind_error_message
from server_app.core.paths import get_config_dir

try:
    import winreg
except ImportError:  # pragma: no cover - this project targets Windows for service control.
    winreg = None


SERVICE_NAME = "ERPAccountingServer"
SERVICE_DISPLAY_NAME = APP_NAME
SERVICE_DESCRIPTION = "Background LAN API service for ERP Accounting Server."
SERVICE_CLASS = "server_app.windows_service.ERPAccountingWindowsService"
PYTHONPATH_REGISTRY_NAME = SERVICE_NAME
SERVICE_SQL_LOGIN_NAME = rf"NT SERVICE\{SERVICE_NAME}"
ERROR_SERVICE_DOES_NOT_EXIST = 1060
SERVICE_ERROR_LOG_FILE_NAME = "service-error.log"


class ServiceControlError(RuntimeError):
    """Raised when Windows service control fails."""


class AdminRequiredError(ServiceControlError):
    """Raised when service control needs an elevated process."""


class ServiceRunState(str, Enum):
    """Known Windows service runtime states used by the GUI."""

    NOT_INSTALLED = "not_installed"
    STOPPED = "stopped"
    START_PENDING = "start_pending"
    STOP_PENDING = "stop_pending"
    RUNNING = "running"
    PAUSED = "paused"
    UNKNOWN = "unknown"


class ServiceStartType(str, Enum):
    """Windows service startup modes relevant to this app."""

    AUTO = "automatic"
    MANUAL = "manual"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ServiceStatus:
    """Current service installation, runtime, and startup-type state."""

    installed: bool
    run_state: ServiceRunState
    start_type: ServiceStartType
    needs_repair: bool = False


@dataclass(frozen=True)
class _PyWin32Modules:
    """Small dependency bundle to make service control easy to mock."""

    win32service: ModuleType
    win32serviceutil: ModuleType
    regutil: ModuleType


def _load_pywin32() -> _PyWin32Modules:
    """Import pywin32 modules lazily so tests can mock the controller."""

    try:
        import win32service
        import win32serviceutil
        from win32.lib import regutil
    except ImportError as exc:
        raise ServiceControlError("pywin32 is required for Windows service control.") from exc

    return _PyWin32Modules(
        win32service=win32service,
        win32serviceutil=win32serviceutil,
        regutil=regutil,
    )


def is_user_admin() -> bool:
    """Return whether the current Windows process is elevated."""

    if os.name != "nt":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _project_root() -> Path:
    """Return the import root that must be visible to pythonservice.exe."""

    return Path(__file__).resolve().parents[1]


def _dedupe_existing_paths(paths: list[str | Path]) -> list[str]:
    """Return existing paths once, preserving order and original spelling."""

    unique_paths: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        normalized = _normalize_registry_path(path)
        if normalized in seen:
            continue
        unique_paths.append(str(path))
        seen.add(normalized)
    return unique_paths


def _service_python_path_entries() -> list[str]:
    """Return import paths needed by pythonservice.exe for this source checkout."""

    candidates: list[str | Path] = [_project_root()]

    try:
        candidates.extend(site.getsitepackages())
    except AttributeError:
        pass

    try:
        candidates.append(site.getusersitepackages())
    except AttributeError:
        pass

    for path in sys.path:
        if not path:
            continue
        path_parts = {part.lower() for part in Path(path).parts}
        path_name = Path(path).name.lower()
        if "site-packages" in path_parts or path_name in {"win32", "pythonwin"}:
            candidates.append(path)

    return _dedupe_existing_paths(candidates)


def _service_python_path_value() -> str:
    """Return the registry value used to extend pythonservice.exe imports."""

    return os.pathsep.join(_service_python_path_entries())


def _is_missing_service_error(exc: BaseException) -> bool:
    """Return whether a pywin32 error means the service is not installed."""

    return getattr(exc, "winerror", None) == ERROR_SERVICE_DOES_NOT_EXIST


def _status_error_message(action: str, exc: BaseException) -> str:
    """Build a readable service-control error message."""

    message = getattr(exc, "strerror", None) or str(exc)
    return f"Could not {action} Windows service '{SERVICE_DISPLAY_NAME}': {message}"


def service_error_log_path() -> Path:
    """Return the service startup error log path."""

    return get_config_dir() / SERVICE_ERROR_LOG_FILE_NAME


def clear_service_error_log() -> None:
    """Remove any old service startup error message."""

    try:
        service_error_log_path().unlink(missing_ok=True)
    except OSError:
        pass


def write_service_error_log(message: str) -> None:
    """Persist a service startup error for the GUI controller to display."""

    try:
        path = service_error_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(message, encoding="utf-8")
    except OSError:
        pass


def read_service_error_log() -> str | None:
    """Read the latest service startup error message when available."""

    try:
        text = service_error_log_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _read_registered_service_class() -> str | None:
    """Read the pywin32 PythonClass registered for this service."""

    if winreg is None:
        return None

    key_path = rf"SYSTEM\CurrentControlSet\Services\{SERVICE_NAME}\PythonClass"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            return winreg.QueryValue(key, None)
    except OSError:
        return None


def _python_path_registry_key() -> str:
    """Return the machine-wide PythonPath key used by pythonservice.exe."""

    return rf"Software\Python\PythonCore\{sys.winver}\PythonPath\{PYTHONPATH_REGISTRY_NAME}"


def _read_registered_project_python_path() -> str | None:
    """Read the machine-wide PythonPath entry for this service."""

    if winreg is None:
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _python_path_registry_key()) as key:
            return winreg.QueryValue(key, None)
    except OSError:
        return None


def _write_registered_project_python_path(path: str) -> None:
    """Write the service import path to the machine-wide PythonPath registry."""

    if winreg is None:
        raise ServiceControlError("Windows registry access is required to register the service Python path.")

    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, _python_path_registry_key(), 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValue(key, None, winreg.REG_SZ, path)


def _normalize_registry_path(path: str | Path) -> str:
    """Normalize a path for stable service registry comparisons."""

    return os.path.normcase(os.path.abspath(str(path)))


def _registered_python_path_is_current(value: str | None) -> bool:
    """Return whether the registered PythonPath includes required service imports."""

    if not value:
        return False

    registered_paths = {
        _normalize_registry_path(path_part)
        for path_part in value.split(os.pathsep)
        if path_part.strip()
    }
    return all(
        _normalize_registry_path(path_part) in registered_paths
        for path_part in _service_python_path_entries()
    )


def service_health_url(config: AppConfig) -> str:
    """Return a local health URL that can be polled after service startup."""

    if config.api.host == "0.0.0.0":
        host = "127.0.0.1"
    elif config.api.host == "::":
        host = "[::1]"
    elif ":" in config.api.host and not config.api.host.startswith("["):
        host = f"[{config.api.host}]"
    else:
        host = config.api.host
    return f"http://{host}:{config.api.port}/health"


def _connection_failure_hint(
    config: AppConfig,
    last_error: Exception | None,
    service_error: str | None,
) -> str:
    """Return an actionable hint when the health endpoint cannot be reached."""

    port_result = check_tcp_port(config.api.host, config.api.port)
    if not port_result.available:
        return f"Port check failed: {port_result.full_message}"

    if service_error and is_port_bind_error_message(service_error):
        return (
            "The service reported an API host/port bind failure. "
            "Choose a different local host/IP or port and try again."
        )

    if last_error is not None:
        return "The port check passed, so this does not look like a port conflict."
    return ""


def wait_for_service_health(config: AppConfig, timeout_seconds: float = 60.0) -> None:
    """Wait until the API service answers its health endpoint."""

    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    url = service_health_url(config)

    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except HTTPError as exc:
            last_error = ServiceControlError(f"Health endpoint returned HTTP {exc.code}.")
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.5)

    parts = [f"Windows service started, but the API did not answer {url}."]
    if last_error is not None:
        parts.append(f"Last error: {last_error}.")

    service_error = read_service_error_log()
    if service_error:
        parts.append(f"Service startup error: {service_error}")
    parts.append(_connection_failure_hint(config, last_error, service_error).strip())

    raise ServiceControlError(" ".join(part for part in parts if part))


class WindowsServiceController:
    """Install, repair, start, stop, and query the ERP Windows service."""

    def __init__(self, modules: _PyWin32Modules | SimpleNamespace | None = None) -> None:
        self.modules = modules or _load_pywin32()

    @property
    def win32service(self) -> ModuleType:
        """Return the win32service module or test double."""

        return self.modules.win32service

    @property
    def win32serviceutil(self) -> ModuleType:
        """Return the win32serviceutil module or test double."""

        return self.modules.win32serviceutil

    @property
    def regutil(self) -> ModuleType:
        """Return the regutil module or test double."""

        return self.modules.regutil

    def require_admin(self) -> None:
        """Require an elevated app process before mutating service state."""

        if not is_user_admin():
            raise AdminRequiredError(
                "Please restart ERP Accounting Server as Administrator to install, start, stop, or disable "
                "the Windows service."
            )

    def get_status(self) -> ServiceStatus:
        """Return the current Windows service status without changing it."""

        try:
            raw_status = self.win32serviceutil.QueryServiceStatus(SERVICE_NAME)
            raw_start_type = self._query_start_type()
        except Exception as exc:
            if _is_missing_service_error(exc):
                return ServiceStatus(
                    installed=False,
                    run_state=ServiceRunState.NOT_INSTALLED,
                    start_type=ServiceStartType.UNKNOWN,
                    needs_repair=False,
                )
            raise ServiceControlError(_status_error_message("query", exc)) from exc

        return ServiceStatus(
            installed=True,
            run_state=self._map_run_state(raw_status[1]),
            start_type=self._map_start_type(raw_start_type),
            needs_repair=self.service_needs_repair(),
        )

    def ensure_installed(self) -> None:
        """Install or repair the service registration and project import path."""

        self.require_admin()
        self._register_project_python_path()

        try:
            self.win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        except Exception as exc:
            if not _is_missing_service_error(exc):
                raise ServiceControlError(_status_error_message("query", exc)) from exc
            self._install_service()
            self._configure_service_sid()
            return

        self._repair_service()
        self._configure_service_sid()

    def enable_autostart(self) -> None:
        """Set the service startup mode to Automatic."""

        self.require_admin()
        self._change_service_config(self.win32service.SERVICE_AUTO_START)

    def disable_autostart(self) -> None:
        """Disable the service so it does not restart after reboot."""

        self.require_admin()
        self._change_service_config(self.win32service.SERVICE_DISABLED)

    def start_service(self) -> None:
        """Start the Windows service if needed and ensure autostart is enabled."""

        self.require_admin()
        status = self.get_status()
        if not status.installed or status.needs_repair:
            self.ensure_installed()
            status = self.get_status()
        else:
            self.enable_autostart()
            status = self.get_status()

        clear_service_error_log()

        if status.run_state == ServiceRunState.RUNNING:
            return
        if status.run_state == ServiceRunState.START_PENDING:
            self.wait_for_run_state(ServiceRunState.RUNNING, timeout_seconds=30)
            return
        if status.run_state == ServiceRunState.STOP_PENDING:
            self.wait_for_run_state(ServiceRunState.STOPPED, timeout_seconds=30)
            status = self.get_status()

        if status.run_state != ServiceRunState.STOPPED:
            raise ServiceControlError(
                f"Windows service '{SERVICE_DISPLAY_NAME}' cannot be started from state "
                f"{status.run_state.value}."
            )

        try:
            self.win32serviceutil.StartService(SERVICE_NAME)
        except Exception as exc:
            raise ServiceControlError(_status_error_message("start", exc)) from exc

        self.wait_for_run_state(ServiceRunState.RUNNING, timeout_seconds=30)

    def stop_service(self) -> None:
        """Stop the Windows service if it is running or starting."""

        self.require_admin()
        status = self.get_status()
        if status.run_state in {ServiceRunState.STOPPED, ServiceRunState.NOT_INSTALLED}:
            return
        if status.run_state == ServiceRunState.STOP_PENDING:
            self.wait_for_run_state(ServiceRunState.STOPPED, timeout_seconds=30)
            return

        try:
            self.win32serviceutil.StopServiceWithDeps(SERVICE_NAME, waitSecs=30)
        except Exception as exc:
            raise ServiceControlError(_status_error_message("stop", exc)) from exc

        self.wait_for_run_state(ServiceRunState.STOPPED, timeout_seconds=30)

    def stop_and_disable(self) -> None:
        """Stop the service and disable future automatic startup."""

        if not self.get_status().installed:
            return
        self.stop_service()
        self.disable_autostart()

    def start_and_wait_for_health(self, config: AppConfig) -> None:
        """Start the service and wait until the API is reachable."""

        self.start_service()
        wait_for_service_health(config)

    def service_needs_repair(self) -> bool:
        """Return whether the service registration is missing critical pywin32 details."""

        return (
            _read_registered_service_class() != SERVICE_CLASS
            or not _registered_python_path_is_current(_read_registered_project_python_path())
        )

    def wait_for_run_state(
        self,
        target_state: ServiceRunState,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Wait until the service reaches a specific runtime state."""

        deadline = time.monotonic() + timeout_seconds
        last_status: ServiceStatus | None = None

        while time.monotonic() < deadline:
            last_status = self.get_status()
            if last_status.run_state == target_state:
                return
            if target_state == ServiceRunState.RUNNING and last_status.run_state == ServiceRunState.STOPPED:
                service_error = read_service_error_log()
                detail = f" {service_error}" if service_error else " Check Windows Event Viewer for details."
                raise ServiceControlError(
                    f"Windows service '{SERVICE_DISPLAY_NAME}' stopped during startup.{detail}"
                )
            time.sleep(0.5)

        raise ServiceControlError(
            f"Timed out waiting for Windows service '{SERVICE_DISPLAY_NAME}' to become "
            f"{target_state.value}. Last state: {last_status.run_state.value if last_status else 'unknown'}."
        )

    def _install_service(self) -> None:
        """Install the service as LocalSystem with Automatic startup."""

        try:
            self.win32serviceutil.InstallService(
                SERVICE_CLASS,
                SERVICE_NAME,
                SERVICE_DISPLAY_NAME,
                startType=self.win32service.SERVICE_AUTO_START,
                description=SERVICE_DESCRIPTION,
            )
        except Exception as exc:
            raise ServiceControlError(_status_error_message("install", exc)) from exc

    def _repair_service(self) -> None:
        """Repair an existing service registration in place."""

        self._change_service_config(self.win32service.SERVICE_AUTO_START)

    def _configure_service_sid(self) -> None:
        """Enable the per-service Windows SID used for SQL Server access."""

        hscm = self.win32service.OpenSCManager(None, None, self.win32service.SC_MANAGER_CONNECT)
        try:
            hs = self.win32service.OpenService(
                hscm,
                SERVICE_NAME,
                self.win32service.SERVICE_CHANGE_CONFIG,
            )
            try:
                self.win32service.ChangeServiceConfig2(
                    hs,
                    self.win32service.SERVICE_CONFIG_SERVICE_SID_INFO,
                    self.win32service.SERVICE_SID_TYPE_UNRESTRICTED,
                )
            finally:
                self.win32service.CloseServiceHandle(hs)
        except Exception as exc:
            raise ServiceControlError(_status_error_message("configure service SID for", exc)) from exc
        finally:
            self.win32service.CloseServiceHandle(hscm)

    def _change_service_config(self, start_type: int) -> None:
        """Change service config while preserving the pywin32 class registration."""

        try:
            self.win32serviceutil.ChangeServiceConfig(
                SERVICE_CLASS,
                SERVICE_NAME,
                startType=start_type,
                displayName=SERVICE_DISPLAY_NAME,
                description=SERVICE_DESCRIPTION,
            )
        except Exception as exc:
            raise ServiceControlError(_status_error_message("configure", exc)) from exc

    def _register_project_python_path(self) -> None:
        """Register this checkout so pythonservice.exe can import server_app."""

        try:
            service_python_path = _service_python_path_value()
            if isinstance(self.modules, _PyWin32Modules):
                _write_registered_project_python_path(service_python_path)
            else:
                self.regutil.RegisterNamedPath(PYTHONPATH_REGISTRY_NAME, service_python_path)
        except Exception as exc:
            raise ServiceControlError(_status_error_message("register Python path for", exc)) from exc

    def _query_start_type(self) -> int:
        """Read the Windows service start type from SCM."""

        hscm = self.win32service.OpenSCManager(None, None, self.win32service.SC_MANAGER_CONNECT)
        try:
            hs = self.win32service.OpenService(
                hscm,
                SERVICE_NAME,
                self.win32service.SERVICE_QUERY_CONFIG,
            )
            try:
                return self.win32service.QueryServiceConfig(hs)[1]
            finally:
                self.win32service.CloseServiceHandle(hs)
        finally:
            self.win32service.CloseServiceHandle(hscm)

    def _map_run_state(self, raw_state: int) -> ServiceRunState:
        """Map pywin32 runtime state constants into GUI-friendly values."""

        mapping = {
            self.win32service.SERVICE_STOPPED: ServiceRunState.STOPPED,
            self.win32service.SERVICE_START_PENDING: ServiceRunState.START_PENDING,
            self.win32service.SERVICE_STOP_PENDING: ServiceRunState.STOP_PENDING,
            self.win32service.SERVICE_RUNNING: ServiceRunState.RUNNING,
            getattr(self.win32service, "SERVICE_PAUSED", None): ServiceRunState.PAUSED,
        }
        return mapping.get(raw_state, ServiceRunState.UNKNOWN)

    def _map_start_type(self, raw_start_type: int) -> ServiceStartType:
        """Map pywin32 start-type constants into GUI-friendly values."""

        mapping = {
            self.win32service.SERVICE_AUTO_START: ServiceStartType.AUTO,
            self.win32service.SERVICE_DEMAND_START: ServiceStartType.MANUAL,
            self.win32service.SERVICE_DISABLED: ServiceStartType.DISABLED,
        }
        return mapping.get(raw_start_type, ServiceStartType.UNKNOWN)
