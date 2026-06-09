"""pywin32 Windows service entry point for the ERP Accounting API."""

from __future__ import annotations

import servicemanager
import win32event
import win32service
import win32serviceutil

from server_app.server_runtime import ApiServiceRuntime
from server_app.service_control import (
    SERVICE_CLASS,
    SERVICE_DESCRIPTION,
    SERVICE_DISPLAY_NAME,
    SERVICE_NAME,
    clear_service_error_log,
    write_service_error_log,
)


class ERPAccountingWindowsService(win32serviceutil.ServiceFramework):
    """Windows service wrapper that runs the FastAPI server in the background."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args: list[str]) -> None:
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.runtime = ApiServiceRuntime()

    def SvcStop(self) -> None:
        """Handle Stop from Services, Task Manager, or the GUI controller."""

        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.runtime.stop()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:
        """Prepare and run the API until Windows stops the service."""

        servicemanager.LogInfoMsg(f"{SERVICE_DISPLAY_NAME} service is starting with class {SERVICE_CLASS}.")
        try:
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING, waitHint=60000)
            self.runtime.prepare()
            clear_service_error_log()
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self.runtime.run()
            servicemanager.LogInfoMsg(f"{SERVICE_DISPLAY_NAME} service stopped.")
        except Exception as exc:
            write_service_error_log(str(exc))
            servicemanager.LogErrorMsg(f"{SERVICE_DISPLAY_NAME} service failed: {exc}")
            raise
        finally:
            self.runtime.close()


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(ERPAccountingWindowsService)
