"""Shared structured-data redaction for recordings and execution evidence."""
import re


MASK = "***"
SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "hashed-password", "token", "authorization",
    "cookie", "set-cookie", "secret", "secret-key", "api-key", "apikey",
    "x-api-key", "x-shadow-authorization", "phone", "mobile", "id-card", "idcard",
}


def is_sensitive_key(key) -> bool:
    normalized = str(key).lower().replace("_", "-")
    return normalized in SENSITIVE_KEYS or normalized.endswith(
        ("-token", "-password", "-secret", "-authorization")
    )


def is_sensitive_source(source) -> bool:
    return any(is_sensitive_key(field) for field in re.findall(r"[\w-]+", str(source or "")))


def sensitive_strings(value, *, sensitive=False):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from sensitive_strings(item, sensitive=sensitive or is_sensitive_key(key))
    elif isinstance(value, list):
        for item in value:
            yield from sensitive_strings(item, sensitive=sensitive)
    elif sensitive and isinstance(value, (str, int, float, bool)):
        rendered = str(value)
        if rendered:
            yield rendered


def mask_sensitive(value, *, secrets=()):
    if isinstance(value, dict):
        return {key: MASK if is_sensitive_key(key) else mask_sensitive(item, secrets=secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(item, secrets=secrets) for item in value]
    # bool is an int subclass, but verdict flags must retain their type/value.
    if type(value) in (int, float) and str(value) in secrets:
        return MASK
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, MASK)
    return value
