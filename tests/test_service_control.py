"""Tests for mocked Windows service control behavior."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import URLError

from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.network import PortCheckResult, PortCheckStatus
from server_app.service_control import (
    SERVICE_CLASS,
    SERVICE_NAME,
    ServiceControlError,
    ServiceRunState,
    ServiceStartType,
    WindowsServiceController,
    _project_root,
    service_health_url,
    wait_for_service_health,
)


class _MissingServiceError(Exception):
    """pywin32-like service missing error for tests."""

    winerror = 1060
    strerror = "The specified service does not exist."


def _fake_modules(installed: bool = True, run_state: int = 1, start_type: int = 2) -> SimpleNamespace:
    """Build pywin32-like test doubles backed by shared mutable state."""

    state = {
        "installed": installed,
        "run_state": run_state,
        "start_type": start_type,
        "sid_type": None,
        "installed_class": None,
        "changed_start_types": [],
        "started": False,
        "stopped": False,
        "registered_path": None,
    }

    win32service = SimpleNamespace(
        SERVICE_AUTO_START=2,
        SERVICE_DISABLED=4,
        SERVICE_DEMAND_START=3,
        SERVICE_RUNNING=4,
        SERVICE_STOPPED=1,
        SERVICE_START_PENDING=2,
        SERVICE_STOP_PENDING=3,
        SERVICE_PAUSED=7,
        SC_MANAGER_CONNECT=1,
        SERVICE_QUERY_CONFIG=1,
        SERVICE_CHANGE_CONFIG=2,
        SERVICE_CONFIG_SERVICE_SID_INFO=5,
        SERVICE_SID_TYPE_UNRESTRICTED=1,
        OpenSCManager=lambda *_args: "scm",
        OpenService=lambda *_args: "service",
        QueryServiceConfig=lambda _service: (None, state["start_type"]),
        ChangeServiceConfig2=lambda _service, _info_level, sid_type: state.__setitem__("sid_type", sid_type),
        CloseServiceHandle=lambda _handle: None,
    )

    def query_service_status(_service_name: str) -> tuple[None, int]:
        if not state["installed"]:
            raise _MissingServiceError()
        return (None, state["run_state"])

    def install_service(python_class: str, service_name: str, _display_name: str, **kwargs: object) -> None:
        state["installed"] = True
        state["installed_class"] = python_class
        state["start_type"] = int(kwargs["startType"])
        assert service_name == SERVICE_NAME

    def change_service_config(python_class: str, service_name: str, **kwargs: object) -> None:
        state["installed_class"] = python_class
        state["start_type"] = int(kwargs["startType"])
        state["changed_start_types"].append(state["start_type"])
        assert service_name == SERVICE_NAME

    def start_service(_service_name: str) -> None:
        state["started"] = True
        state["run_state"] = win32service.SERVICE_RUNNING

    def stop_service_with_deps(_service_name: str, waitSecs: int = 30) -> None:
        state["stopped"] = True
        state["run_state"] = win32service.SERVICE_STOPPED
        assert waitSecs == 30

    win32serviceutil = SimpleNamespace(
        QueryServiceStatus=query_service_status,
        InstallService=install_service,
        ChangeServiceConfig=change_service_config,
        StartService=start_service,
        StopServiceWithDeps=stop_service_with_deps,
    )
    regutil = SimpleNamespace(
        RegisterNamedPath=lambda name, path: state.__setitem__("registered_path", (name, path))
    )
    modules = SimpleNamespace(
        win32service=win32service,
        win32serviceutil=win32serviceutil,
        regutil=regutil,
        state=state,
    )
    return modules


def _make_config() -> AppConfig:
    """Return a minimal service config for health polling tests."""

    return AppConfig(
        database=DatabaseConfig(server="localhost", database="ERPAccounting"),
        api=ApiConfig(host="127.0.0.1", port=8123),
        jwt_secret="jwt-secret",
    )


def _make_port_result(status: PortCheckStatus, message: str) -> PortCheckResult:
    """Return a representative port check result."""

    return PortCheckResult(
        host="127.0.0.1",
        port=8123,
        bind_host="127.0.0.1",
        status=status,
        message=message,
    )


class ServiceControlTests(unittest.TestCase):
    """Validate service controller decisions without touching Windows SCM."""

    def repair_checks_current(self) -> tuple[object, object]:
        """Patch registry repair probes to represent a healthy registration."""

        return (
            patch("server_app.service_control._read_registered_service_class", return_value=SERVICE_CLASS),
            patch("server_app.service_control._read_registered_project_python_path", return_value=str(_project_root())),
        )

    def test_status_maps_running_automatic_service(self) -> None:
        """Running Automatic services should map to GUI status enums."""

        modules = _fake_modules(run_state=4, start_type=2)
        controller = WindowsServiceController(modules)

        with self.repair_checks_current()[0], self.repair_checks_current()[1]:
            status = controller.get_status()

        self.assertTrue(status.installed)
        self.assertEqual(status.run_state, ServiceRunState.RUNNING)
        self.assertEqual(status.start_type, ServiceStartType.AUTO)
        self.assertFalse(status.needs_repair)

    def test_missing_service_installs_with_python_class_and_python_path(self) -> None:
        """Missing services should be installed and project import path registered."""

        modules = _fake_modules(installed=False)
        controller = WindowsServiceController(modules)

        with patch("server_app.service_control.is_user_admin", return_value=True):
            controller.ensure_installed()

        self.assertTrue(modules.state["installed"])
        self.assertEqual(modules.state["installed_class"], SERVICE_CLASS)
        self.assertEqual(modules.state["start_type"], modules.win32service.SERVICE_AUTO_START)
        self.assertEqual(modules.state["sid_type"], modules.win32service.SERVICE_SID_TYPE_UNRESTRICTED)
        self.assertIsNotNone(modules.state["registered_path"])

    def test_existing_service_is_repaired_in_place(self) -> None:
        """Existing services should be reconfigured instead of duplicated."""

        modules = _fake_modules(installed=True)
        controller = WindowsServiceController(modules)

        with patch("server_app.service_control.is_user_admin", return_value=True):
            controller.ensure_installed()

        self.assertEqual(modules.state["installed_class"], SERVICE_CLASS)
        self.assertEqual(
            modules.state["changed_start_types"],
            [modules.win32service.SERVICE_AUTO_START],
        )
        self.assertEqual(modules.state["sid_type"], modules.win32service.SERVICE_SID_TYPE_UNRESTRICTED)

    def test_start_service_enables_autostart_and_waits_for_running(self) -> None:
        """Start should enable Automatic startup and transition to running."""

        modules = _fake_modules(run_state=1, start_type=4)
        controller = WindowsServiceController(modules)

        with (
            patch("server_app.service_control.is_user_admin", return_value=True),
            self.repair_checks_current()[0],
            self.repair_checks_current()[1],
        ):
            controller.start_service()

        self.assertTrue(modules.state["started"])
        self.assertEqual(modules.state["run_state"], modules.win32service.SERVICE_RUNNING)
        self.assertEqual(modules.state["start_type"], modules.win32service.SERVICE_AUTO_START)

    def test_stop_and_disable_stops_service_and_disables_autostart(self) -> None:
        """Stop Connection should stop the service and disable reboot startup."""

        modules = _fake_modules(run_state=4, start_type=2)
        controller = WindowsServiceController(modules)

        with (
            patch("server_app.service_control.is_user_admin", return_value=True),
            self.repair_checks_current()[0],
            self.repair_checks_current()[1],
        ):
            controller.stop_and_disable()

        self.assertTrue(modules.state["stopped"])
        self.assertEqual(modules.state["run_state"], modules.win32service.SERVICE_STOPPED)
        self.assertEqual(modules.state["start_type"], modules.win32service.SERVICE_DISABLED)

    def test_status_flags_repair_when_python_path_is_missing(self) -> None:
        """A missing service PythonPath should be treated as a repair condition."""

        modules = _fake_modules(run_state=1, start_type=2)
        controller = WindowsServiceController(modules)

        with (
            patch("server_app.service_control._read_registered_service_class", return_value=SERVICE_CLASS),
            patch("server_app.service_control._read_registered_project_python_path", return_value=None),
        ):
            status = controller.get_status()

        self.assertTrue(status.needs_repair)

    def test_start_running_disabled_service_only_enables_autostart(self) -> None:
        """Start should repair startup mode even when the service is already running."""

        modules = _fake_modules(run_state=4, start_type=4)
        controller = WindowsServiceController(modules)

        with (
            patch("server_app.service_control.is_user_admin", return_value=True),
            self.repair_checks_current()[0],
            self.repair_checks_current()[1],
        ):
            controller.start_service()

        self.assertFalse(modules.state["started"])
        self.assertEqual(modules.state["start_type"], modules.win32service.SERVICE_AUTO_START)

    def test_start_pending_service_waits_without_duplicate_start(self) -> None:
        """Start should wait for a pending service instead of issuing StartService again."""

        modules = _fake_modules(run_state=2, start_type=2)
        controller = WindowsServiceController(modules)

        with (
            patch("server_app.service_control.is_user_admin", return_value=True),
            self.repair_checks_current()[0],
            self.repair_checks_current()[1],
            patch.object(controller, "wait_for_run_state") as wait_for_run_state,
        ):
            controller.start_service()

        self.assertFalse(modules.state["started"])
        wait_for_run_state.assert_called_once_with(ServiceRunState.RUNNING, timeout_seconds=30)

    def test_stop_pending_service_waits_without_duplicate_stop(self) -> None:
        """Stop should wait for a pending stop instead of sending another stop control."""

        modules = _fake_modules(run_state=3, start_type=2)
        controller = WindowsServiceController(modules)

        with (
            patch("server_app.service_control.is_user_admin", return_value=True),
            self.repair_checks_current()[0],
            self.repair_checks_current()[1],
            patch.object(controller, "wait_for_run_state") as wait_for_run_state,
        ):
            controller.stop_service()

        self.assertFalse(modules.state["stopped"])
        wait_for_run_state.assert_called_once_with(ServiceRunState.STOPPED, timeout_seconds=30)

    def test_service_health_url_formats_wildcard_and_ipv6_hosts(self) -> None:
        """Health polling should use reachable local URLs for wildcard and IPv6 binds."""

        config = _make_config()
        config.api.host = "0.0.0.0"
        self.assertEqual(service_health_url(config), "http://127.0.0.1:8123/health")

        config.api.host = "::"
        self.assertEqual(service_health_url(config), "http://[::1]:8123/health")

        config.api.host = "2001:db8::1"
        self.assertEqual(service_health_url(config), "http://[2001:db8::1]:8123/health")

    def test_health_timeout_does_not_guess_port_conflict_when_port_check_passes(self) -> None:
        """Plain health timeouts should not claim another program is using the port."""

        available = _make_port_result(
            PortCheckStatus.AVAILABLE,
            "Port 8123 is available on 127.0.0.1.",
        )

        with (
            patch("server_app.service_control.urlopen", side_effect=URLError("timed out")),
            patch("server_app.service_control.time.monotonic", side_effect=[0.0, 0.0, 2.0]),
            patch("server_app.service_control.time.sleep"),
            patch("server_app.service_control.read_service_error_log", return_value=None),
            patch("server_app.service_control.check_tcp_port", return_value=available),
        ):
            with self.assertRaises(ServiceControlError) as context:
                wait_for_service_health(_make_config(), timeout_seconds=1.0)

        message = str(context.exception)
        self.assertIn("does not look like a port conflict", message)
        self.assertNotIn("Another program may be using", message)

    def test_health_timeout_reports_service_bind_failure_from_error_log(self) -> None:
        """A service bind error log should produce a host/port bind hint."""

        available = _make_port_result(
            PortCheckStatus.AVAILABLE,
            "Port 8123 is available on 127.0.0.1.",
        )
        service_error = "error while attempting to bind on address ('127.0.0.1', 8123): [WinError 10048]"

        with (
            patch("server_app.service_control.urlopen", side_effect=URLError("refused")),
            patch("server_app.service_control.time.monotonic", side_effect=[0.0, 0.0, 2.0]),
            patch("server_app.service_control.time.sleep"),
            patch("server_app.service_control.read_service_error_log", return_value=service_error),
            patch("server_app.service_control.check_tcp_port", return_value=available),
        ):
            with self.assertRaises(ServiceControlError) as context:
                wait_for_service_health(_make_config(), timeout_seconds=1.0)

        message = str(context.exception)
        self.assertIn("Service startup error", message)
        self.assertIn("reported an API host/port bind failure", message)


if __name__ == "__main__":
    unittest.main()
