"""Shared structured-data redaction for recordings and execution evidence."""
import re
from urllib.parse import quote, quote_plus


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


def _secret_patterns(secrets):
    variants = {}
    for secret in secrets:
        if not isinstance(secret, str) or not secret:
            continue
        variants[secret] = re.escape(secret)
        frontier = {secret}
        # Cover query/path quoting and one additional proxy-encoding layer.
        # Only percent-escape hex digits are case-insensitive, not token text.
        for _ in range(2):
            frontier = {encoded for item in frontier for encoded in
                        (quote(item, safe=""), quote(item, safe="/"), quote_plus(item))}
            for encoded in frontier - {secret}:
                variants[encoded] = re.sub(
                    r"%(?:25)?[0-9A-Fa-f]{2}",
                    lambda match: "%" + "".join(
                        f"[{char.lower()}{char.upper()}]" if char.isalpha() else char
                        for char in match.group()[1:]),
                    re.escape(encoded),
                )
    return tuple(re.compile(variants[item]) for item in
                 sorted(variants, key=len, reverse=True))


def mask_sensitive(value, *, secrets=()):
    secrets = tuple(secrets)
    return _mask(value, secrets, _secret_patterns(secrets))


def _mask(value, secrets, patterns):
    if isinstance(value, dict):
        return {key: MASK if is_sensitive_key(key) else _mask(item, secrets, patterns)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_mask(item, secrets, patterns) for item in value]
    # bool is an int subclass, but verdict flags must retain their type/value.
    if type(value) in (int, float) and str(value) in secrets:
        return MASK
    if isinstance(value, str):
        for pattern in patterns:
            value = pattern.sub(MASK, value)
    return value
