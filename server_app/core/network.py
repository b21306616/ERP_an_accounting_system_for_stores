"""Network helpers for API bind and port availability checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import errno
import socket


class PortCheckStatus(str, Enum):
    """Specific outcomes for API bind preflight checks."""

    AVAILABLE = "available"
    INVALID_PORT = "invalid_port"
    INVALID_HOST = "invalid_host"
    HOST_NOT_LOCAL = "host_not_local"
    IN_USE = "in_use"
    ACCESS_DENIED_OR_RESERVED = "access_denied_or_reserved"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PortCheckResult:
    """Structured result for an API host/port availability check."""

    host: str
    port: int
    bind_host: str
    status: PortCheckStatus
    message: str
    diagnostic: str = ""
    error: str = ""

    @property
    def available(self) -> bool:
        """Return whether the API should be able to bind this host and port."""

        return self.status == PortCheckStatus.AVAILABLE

    @property
    def is_port_problem(self) -> bool:
        """Return whether the failure is specifically about bind/port availability."""

        return self.status in {
            PortCheckStatus.IN_USE,
            PortCheckStatus.ACCESS_DENIED_OR_RESERVED,
        }

    @property
    def is_bind_problem(self) -> bool:
        """Return whether the failure is a known API host/port bind problem."""

        return self.status != PortCheckStatus.AVAILABLE and self.status != PortCheckStatus.UNKNOWN

    @property
    def full_message(self) -> str:
        """Return the message with the diagnostic command appended when useful."""

        return " ".join(part for part in (self.message, self.diagnostic) if part)


def normalize_bind_host(host: str) -> str:
    """Return the host address used when binding a TCP listener."""

    stripped = host.strip()
    if stripped in {"", "0.0.0.0"}:
        return ""
    return stripped


def _display_bind_host(host: str) -> str:
    """Return a stable user-facing host label."""

    return normalize_bind_host(host) or "0.0.0.0"


def _diagnostic(port: int) -> str:
    """Return a Windows diagnostic command for the checked port."""

    if not 1 <= port <= 65535:
        return ""
    return f"To diagnose: netstat -ano | findstr :{port}"


def _socket_family_for_host(bind_host: str) -> socket.AddressFamily:
    """Match uvicorn's host family choice for explicit IPv6 addresses."""

    if bind_host and ":" in bind_host:
        return socket.AF_INET6
    return socket.AF_INET


def _classify_socket_error(exc: OSError) -> PortCheckStatus:
    """Map OS bind errors to user-facing port check statuses."""

    code = getattr(exc, "winerror", None) or exc.errno
    if code in {errno.EADDRINUSE, 10048}:
        return PortCheckStatus.IN_USE
    if code in {errno.EADDRNOTAVAIL, 10049}:
        return PortCheckStatus.HOST_NOT_LOCAL
    if code in {errno.EACCES, 10013}:
        return PortCheckStatus.ACCESS_DENIED_OR_RESERVED
    return PortCheckStatus.UNKNOWN


def is_port_bind_error_message(message: str) -> bool:
    """Return whether a service/runtime error text clearly describes a bind failure."""

    text = message.lower()
    return any(
        marker in text
        for marker in (
            "error while attempting to bind",
            "address already in use",
            "only one usage of each socket address",
            "winerror 10048",
            "winerror 10013",
            "winerror 10049",
            "access is denied",
            "forbidden by its access permissions",
            "attempt was made to access a socket",
            "cannot assign requested address",
            "requested address is not valid in its context",
        )
    )


def _message_for_status(status: PortCheckStatus, host: str, port: int, error: str = "") -> str:
    """Build a precise message for a port check status."""

    display_host = _display_bind_host(host)
    if status == PortCheckStatus.AVAILABLE:
        return f"Port {port} is available on {display_host}."
    if status == PortCheckStatus.INVALID_PORT:
        return "API port must be between 1 and 65535."
    if status == PortCheckStatus.INVALID_HOST:
        return f"API bind host '{host}' is not a valid host name or IP address."
    if status == PortCheckStatus.HOST_NOT_LOCAL:
        return (
            f"Windows cannot bind the API to {display_host}:{port} because that address "
            "is not assigned to this PC. Use 0.0.0.0, 127.0.0.1, or a local network IP."
        )
    if status == PortCheckStatus.IN_USE:
        return (
            f"Port {port} is already in use on {display_host}. "
            "Close the other program or choose a different port, such as 5000 or 8080."
        )
    if status == PortCheckStatus.ACCESS_DENIED_OR_RESERVED:
        return (
            f"Windows denied access to port {port} on {display_host}. "
            "The port may be reserved by Windows, blocked by policy, or owned by a protected listener. "
            "Choose a different port, such as 5000 or 8080."
        )
    detail = f" Last error: {error}." if error else ""
    return (
        f"Windows could not verify port {port} on {display_host}.{detail} "
        "Choose a different port or check the host/IP value."
    )


def check_tcp_port(host: str, port: int) -> PortCheckResult:
    """Return a diagnostic result for binding the API to the requested host and port."""

    if not 1 <= port <= 65535:
        return PortCheckResult(
            host=host,
            port=port,
            bind_host=normalize_bind_host(host),
            status=PortCheckStatus.INVALID_PORT,
            message=_message_for_status(PortCheckStatus.INVALID_PORT, host, port),
        )

    bind_host = normalize_bind_host(host)
    family = _socket_family_for_host(bind_host)
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
    except OSError as exc:
        status = _classify_socket_error(exc)
        message = _message_for_status(status, host, port, str(exc))
        return PortCheckResult(
            host=host,
            port=port,
            bind_host=bind_host,
            status=status,
            message=message,
            error=str(exc),
        )

    try:
        sock.bind((bind_host, port))
    except socket.gaierror as exc:
        message = _message_for_status(PortCheckStatus.INVALID_HOST, host, port)
        return PortCheckResult(
            host=host,
            port=port,
            bind_host=bind_host,
            status=PortCheckStatus.INVALID_HOST,
            message=message,
            error=str(exc),
        )
    except OSError as exc:
        status = _classify_socket_error(exc)
        diagnostic = _diagnostic(port) if status in {
            PortCheckStatus.IN_USE,
            PortCheckStatus.ACCESS_DENIED_OR_RESERVED,
        } else ""
        message = _message_for_status(status, host, port, str(exc))
        return PortCheckResult(
            host=host,
            port=port,
            bind_host=bind_host,
            status=status,
            message=message,
            diagnostic=diagnostic,
            error=str(exc),
        )
    finally:
        sock.close()
    return PortCheckResult(
        host=host,
        port=port,
        bind_host=bind_host,
        status=PortCheckStatus.AVAILABLE,
        message=_message_for_status(PortCheckStatus.AVAILABLE, host, port),
    )


def is_tcp_port_available(host: str, port: int) -> bool:
    """Return whether the API can bind to the requested host and port."""

    return check_tcp_port(host, port).available


def format_port_unavailable_message(port: int, host: str) -> str:
    """Build a user-facing message when the API port cannot be used."""

    return check_tcp_port(host, port).full_message
