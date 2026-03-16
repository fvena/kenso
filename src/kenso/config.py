"""Configuration via KENSO_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["KensoConfig"]


def _resolve_db_url(
    db_override: str | None = None,
    create_if_missing: bool = False,
) -> tuple[str, str]:
    """Resolve database path with local-first cascade.

    Returns (db_url, source) where source describes why this path was chosen.
    Cascade order:
    1. --db CLI flag — highest priority override
    2. KENSO_DATABASE_URL env var — explicit override
    3. .kenso/docs.db in cwd — project-local (exists)
    4. .kenso/docs.db in cwd — project-local (created, when create_if_missing)
    5. ~/.local/share/kenso/docs.db — global fallback
    6. .kenso/docs.db in cwd — default for new projects
    """
    if db_override:
        return str(Path(db_override).resolve()), "--db flag"

    env_url = os.environ.get("KENSO_DATABASE_URL")
    if env_url:
        return env_url, "KENSO_DATABASE_URL"

    local_dir = Path(os.getcwd()) / ".kenso"
    if local_dir.is_dir():
        return str(local_dir / "docs.db"), "project database"

    if create_if_missing:
        local_dir.mkdir(exist_ok=True)
        return str(local_dir / "docs.db"), "project database, created"

    global_path = Path.home() / ".local" / "share" / "kenso" / "docs.db"
    if global_path.is_file():
        return str(global_path), "global fallback"

    return str(local_dir / "docs.db"), "project database"


@dataclass(frozen=True)
class KensoConfig:
    """Immutable server configuration."""

    database_url: str | None = None
    database_source: str = ""
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: str = "8000"

    # Tuning
    content_preview_chars: int = 200
    chunk_size: int = 4000
    chunk_overlap: int = 0
    search_limit_max: int = 20

    # Logging
    log_level: str = "WARNING"

    @classmethod
    def from_env(
        cls,
        *,
        db_override: str | None = None,
        create_if_missing: bool = False,
    ) -> KensoConfig:
        """Load config from KENSO_* environment variables."""
        db_url, db_source = _resolve_db_url(db_override, create_if_missing)
        transport = os.environ.get("KENSO_TRANSPORT", "stdio")
        host = os.environ.get("KENSO_HOST", "127.0.0.1")
        port = os.environ.get("KENSO_PORT", "8000")
        preview = int(os.environ.get("KENSO_CONTENT_PREVIEW_CHARS", "200"))
        chunk_size = int(os.environ.get("KENSO_CHUNK_SIZE", "4000"))
        chunk_overlap = int(os.environ.get("KENSO_CHUNK_OVERLAP", "0"))
        limit_max = int(os.environ.get("KENSO_SEARCH_LIMIT_MAX", "20"))
        log_level = os.environ.get("KENSO_LOG_LEVEL", "WARNING").upper()

        if transport not in ("stdio", "sse", "streamable-http"):
            raise ValueError(f"Invalid transport: {transport!r}")

        return cls(
            database_url=db_url,
            database_source=db_source,
            transport=transport,
            host=host,
            port=port,
            content_preview_chars=preview,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            search_limit_max=limit_max,
            log_level=log_level,
        )
