"""Console / ``python -m face_service`` entrypoint."""

from __future__ import annotations

import logging
import sys
from typing import Any

from .app import create_app
from .config import ConfigError, Settings


def uvicorn_run_kwargs(settings: Settings) -> dict[str, Any]:
    """uvicorn.run kwargs.

    Raw uvicorn access logs would print the *expanded* request path, which
    contains identity references (namespace / subject_id) for subject routes.
    They are therefore disabled; :mod:`face_service.app` emits its own
    sanitized access log that only records the route template.
    """
    return {
        "host": settings.host,
        "port": settings.port,
        "log_level": settings.log_level.lower(),
        "access_log": False,
    }


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        # Message contains key names only (never values/secrets).
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = create_app(settings=settings)
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        print("uvicorn is not installed", file=sys.stderr)
        raise SystemExit(3) from exc

    uvicorn.run(app, **uvicorn_run_kwargs(settings))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
