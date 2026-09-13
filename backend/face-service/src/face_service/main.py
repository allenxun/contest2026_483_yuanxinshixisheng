"""Console / ``python -m face_service`` entrypoint."""

from __future__ import annotations

import logging
import sys

from .app import create_app
from .config import ConfigError, Settings


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

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
