"""Shared exclusions for recording, ingestion, and historical record access."""
RECORD_SKIP_PREFIXES = ("/traffic", "/metrics", "/docs", "/openapi.json", "/static",
                        "/health", "/auth", "/projects", "/teams")


def is_recordable_path(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in RECORD_SKIP_PREFIXES)
