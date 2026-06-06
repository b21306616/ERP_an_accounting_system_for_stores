"""Password hashing and JWT-compatible token helpers."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from typing import Any

from server_app.core.constants import ACCESS_TOKEN_EXPIRE_MINUTES, TOKEN_ALGORITHM


class TokenError(ValueError):
    """Raised when a bearer token cannot be decoded or verified."""


def _base64url_encode(raw: bytes) -> str:
    """Return base64url text without padding, as used by JWT."""

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(encoded: str) -> bytes:
    """Decode base64url text that may omit padding."""

    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))


def generate_secret_key() -> str:
    """Create a random signing secret suitable for HS256 tokens."""

    return base64.urlsafe_b64encode(os.urandom(48)).decode("ascii")


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt."""

    salt = os.urandom(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_text = base64.b64encode(salt).decode("ascii")
    digest_text = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt_text}${digest_text}"


def verify_password(password: str, password_hash: str) -> bool:
    """Return ``True`` when a password matches a stored PBKDF2 hash."""

    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected_digest = base64.b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(
    subject: str,
    secret_key: str,
    role: str,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    """Create a compact HS256 JWT-compatible bearer token."""

    now = datetime.now(timezone.utc)
    header = {"alg": TOKEN_ALGORITHM, "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }

    header_text = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_text = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_text}.{payload_text}".encode("ascii")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()

    return f"{header_text}.{payload_text}.{_base64url_encode(signature)}"


def decode_access_token(token: str, secret_key: str) -> dict[str, Any]:
    """Verify and decode a compact HS256 JWT-compatible bearer token."""

    try:
        header_text, payload_text, signature_text = token.split(".", 2)
    except ValueError as exc:
        raise TokenError("Token must contain three JWT parts.") from exc

    signing_input = f"{header_text}.{payload_text}".encode("ascii")
    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = _base64url_decode(signature_text)

    if not hmac.compare_digest(actual_signature, expected_signature):
        raise TokenError("Token signature is invalid.")

    try:
        header = json.loads(_base64url_decode(header_text).decode("utf-8"))
        payload = json.loads(_base64url_decode(payload_text).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("Token payload is not valid JSON.") from exc

    if header.get("alg") != TOKEN_ALGORITHM:
        raise TokenError("Token algorithm is not supported.")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise TokenError("Token does not contain an expiration timestamp.")

    if datetime.now(timezone.utc).timestamp() >= expires_at:
        raise TokenError("Token has expired.")

    return payload
