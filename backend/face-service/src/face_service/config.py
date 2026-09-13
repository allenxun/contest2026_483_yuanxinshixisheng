"""Environment-driven configuration with defaults and fail-fast validation.

All configuration is read from ``FACE_SVC_*`` environment variables.  Startup
validation refuses to start when a security-relevant key is missing or unsafe;
error messages name the *key* only and never echo its value (tokens must never
leak into logs).

Secrets are intentionally absent from defaults.  ``FACE_SVC_INTERNAL_TOKEN`` may
be supplied directly, but the recommended deployment path is a 0600 file pointed
to by ``FACE_SVC_INTERNAL_TOKEN_FILE``.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

# backend/face-service/src/face_service/config.py -> backend/face-service
SERVICE_ROOT = Path(__file__).resolve().parents[2]

ENV_PREFIX = "FACE_SVC_"


class ConfigError(RuntimeError):
    """Raised when configuration is missing or unsafe.  Names keys, not values."""


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(ENV_PREFIX + name, default)


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"{ENV_PREFIX}{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"{ENV_PREFIX}{name} must be a number") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """Resolved runtime settings.  Build with :meth:`from_env`."""

    host: str = "10.3.6.163"
    port: int = 8010

    data_dir: Path = field(default_factory=lambda: SERVICE_ROOT / "data")
    db_path: Path = field(default_factory=lambda: SERVICE_ROOT / "data" / "openvela_faces.sqlite3")

    model_root: Path = field(default_factory=lambda: Path.home() / ".insightface" / "models")
    model_name: str = "buffalo_l"
    model_version: str = "buffalo_l@insightface-0.7.3"
    model_providers: tuple[str, ...] = ("CUDAExecutionProvider", "CPUExecutionProvider")
    model_det_size: tuple[int, int] = (640, 640)

    # 1:1 cosine-similarity threshold applied to L2-normalised embeddings.
    # Default 0.40 is a conservative starting point for ArcFace/buffalo_l
    # embeddings; it is NOT calibrated against the project's own data yet and
    # MUST be recalibrated before production use (see README).
    verify_threshold: float = 0.40

    # Request limits / resource guards.
    max_body_bytes: int = 10 * 1024 * 1024
    inference_timeout_seconds: float = 30.0
    max_concurrency: int = 2

    # Optional internal bearer token.
    internal_token: str | None = None
    internal_token_file: Path | None = None
    auth_required: bool = False
    auth_header: str = "X-Internal-Token"

    # Register idempotency policy: "conflict" (409) or "overwrite" (replace).
    register_on_exists: str = "conflict"

    # Quality gating (off by default: quality is reported, not enforced).
    quality_enforce: bool = False
    quality_min_det_score: float = 0.50
    quality_min_blur: float = 30.0
    quality_min_bbox_ratio: float = 0.02

    request_id_header: str = "X-Request-Id"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_env("DATA_DIR") or (SERVICE_ROOT / "data"))
        db_path = Path(_env("DB_PATH") or (data_dir / "openvela_faces.sqlite3"))
        model_root = Path(_env("MODEL_ROOT") or (Path.home() / ".insightface" / "models"))
        token_file_raw = _env("INTERNAL_TOKEN_FILE")
        token_file = Path(token_file_raw) if token_file_raw else None

        settings = cls(
            host=_env("HOST") or "10.3.6.163",
            port=_env_int("PORT", 8010),
            data_dir=data_dir,
            db_path=db_path,
            model_root=model_root,
            model_name=_env("MODEL_NAME") or "buffalo_l",
            model_version=_env("MODEL_VERSION") or "buffalo_l@insightface-0.7.3",
            verify_threshold=_env_float("VERIFY_THRESHOLD", 0.40),
            max_body_bytes=_env_int("MAX_BODY_BYTES", 10 * 1024 * 1024),
            inference_timeout_seconds=_env_float("INFERENCE_TIMEOUT_SECONDS", 30.0),
            max_concurrency=_env_int("MAX_CONCURRENCY", 2),
            internal_token=_env("INTERNAL_TOKEN"),
            internal_token_file=token_file,
            auth_required=_env_bool("AUTH_REQUIRED", False),
            auth_header=_env("AUTH_HEADER") or "X-Internal-Token",
            register_on_exists=(_env("REGISTER_ON_EXISTS") or "conflict").strip().lower(),
            quality_enforce=_env_bool("QUALITY_ENFORCE", False),
            quality_min_det_score=_env_float("QUALITY_MIN_DET_SCORE", 0.50),
            quality_min_blur=_env_float("QUALITY_MIN_BLUR", 30.0),
            quality_min_bbox_ratio=_env_float("QUALITY_MIN_BBOX_RATIO", 0.02),
            request_id_header=_env("REQUEST_ID_HEADER") or "X-Request-Id",
            log_level=(_env("LOG_LEVEL") or "INFO").upper(),
        )
        settings.validate()
        return settings

    # -- validation -------------------------------------------------------
    def validate(self) -> None:
        problems: list[str] = []
        if not (1 <= self.port <= 65535):
            problems.append(f"{ENV_PREFIX}PORT must be within 1..65535")
        if self.max_body_bytes <= 0:
            problems.append(f"{ENV_PREFIX}MAX_BODY_BYTES must be > 0")
        if self.inference_timeout_seconds <= 0:
            problems.append(f"{ENV_PREFIX}INFERENCE_TIMEOUT_SECONDS must be > 0")
        if self.max_concurrency < 1:
            problems.append(f"{ENV_PREFIX}MAX_CONCURRENCY must be >= 1")
        if not (0.0 <= self.verify_threshold <= 1.0):
            problems.append(f"{ENV_PREFIX}VERIFY_THRESHOLD must be within 0..1")
        if self.register_on_exists not in {"conflict", "overwrite"}:
            problems.append(
                f"{ENV_PREFIX}REGISTER_ON_EXISTS must be 'conflict' or 'overwrite'"
            )

        if self.internal_token and self.internal_token_file:
            problems.append(
                "configure only one of FACE_SVC_INTERNAL_TOKEN or "
                "FACE_SVC_INTERNAL_TOKEN_FILE"
            )
        if self.auth_required and not (self.internal_token or self.internal_token_file):
            problems.append(
                "FACE_SVC_AUTH_REQUIRED is set but no token is configured: set "
                "FACE_SVC_INTERNAL_TOKEN_FILE (recommended) or FACE_SVC_INTERNAL_TOKEN"
            )
        if self.internal_token_file is not None:
            try:
                mode = stat.S_IMODE(self.internal_token_file.stat().st_mode)
            except OSError:
                problems.append(
                    f"{ENV_PREFIX}INTERNAL_TOKEN_FILE is not readable"
                )
                mode = None
            if mode is not None and (mode & 0o077) != 0:
                problems.append(
                    f"{ENV_PREFIX}INTERNAL_TOKEN_FILE must be 0600 (group/other "
                    "bits set)"
                )

        if problems:
            raise ConfigError("; ".join(problems))


__all__ = ["Settings", "ConfigError", "SERVICE_ROOT", "ENV_PREFIX"]
