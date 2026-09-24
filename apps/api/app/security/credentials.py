"""Credential encryption using Fernet (AES-128-CBC + HMAC-SHA256)."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    key_bytes = settings.app_encryption_key.encode()
    # Derive a proper 32-byte key then base64url-encode for Fernet
    derived = hashlib.sha256(key_bytes).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def encrypt_credential(plain_text: str) -> str:
    """Encrypt a credential string. Returns a base64url-encoded token."""
    f = _get_fernet()
    return f.encrypt(plain_text.encode()).decode()


def decrypt_credential(token: str) -> str:
    """Decrypt a credential token. Raises ValueError on tampered input."""
    f = _get_fernet()
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid or tampered credential token") from exc


def sanitize_identifier(name: str, max_length: int = 63) -> str:
    """
    Sanitize a PostgreSQL identifier.
    Replaces non-alphanumeric characters with underscores and truncates.
    """
    import re
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()
    # Ensure it doesn't start with a digit
    if sanitized and sanitized[0].isdigit():
        sanitized = f"t_{sanitized}"
    return sanitized[:max_length]
