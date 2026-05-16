import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import get_settings


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), f"{salt}${expected}")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(subject: str, role: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": int(time.time()) + settings.access_token_minutes * 60,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(settings.app_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def decode_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(settings.app_secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
