"""Windows DPAPI helpers for protecting local secrets.

The server stores database passwords and JWT signing secrets on the same
Windows server where the application runs. DPAPI protects those values with the
current Windows user's profile, so no extra dependency is required.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os


class SecretProtectionError(RuntimeError):
    """Raised when a secret cannot be protected or unprotected."""


class DATA_BLOB(ctypes.Structure):
    """ctypes representation of the Windows ``DATA_BLOB`` structure."""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _require_windows() -> None:
    """Fail early when DPAPI is requested on a non-Windows platform."""

    if os.name != "nt":
        raise SecretProtectionError("Windows DPAPI is available only on Windows.")


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    """Create a DPAPI-compatible blob from Python bytes."""

    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    """Copy bytes out of a DPAPI ``DATA_BLOB`` returned by Windows."""

    return ctypes.string_at(blob.pbData, blob.cbData)


def protect_secret(plain_text: str) -> str:
    """Encrypt text with Windows DPAPI and return base64 text for JSON storage."""

    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    plain_bytes = plain_text.encode("utf-8")
    in_blob = _bytes_to_blob(plain_bytes)
    out_blob = DATA_BLOB()

    success = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not success:
        raise SecretProtectionError("Windows DPAPI failed to protect a secret.")

    try:
        protected_bytes = _blob_to_bytes(out_blob)
        return base64.b64encode(protected_bytes).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def unprotect_secret(protected_text: str) -> str:
    """Decrypt a base64 DPAPI value from config storage."""

    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    protected_bytes = base64.b64decode(protected_text.encode("ascii"))
    in_blob = _bytes_to_blob(protected_bytes)
    out_blob = DATA_BLOB()

    success = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not success:
        raise SecretProtectionError("Windows DPAPI failed to unprotect a secret.")

    try:
        return _blob_to_bytes(out_blob).decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)
