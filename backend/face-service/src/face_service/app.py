"""Application assembly: state, middleware, exception handling."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import AppState, build_router, reset_request_id, set_request_id
from .auth import TokenAuth
from .config import Settings
from .errors import ErrorCode, FaceServiceError, error_body
from .model import FaceModel, build_model
from .store import FaceStore

logger = logging.getLogger("face_service.app")
# Dedicated logger for the sanitized request log (route template only).
access_logger = logging.getLogger("face_service.access")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def create_app(
    *,
    settings: Settings | None = None,
    model: FaceModel | None = None,
    store: FaceStore | None = None,
    auth: TokenAuth | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    # Defense in depth: never serve a configuration that would have failed
    # startup validation (e.g. a programmatic non-loopback bind with auth off).
    settings.validate()
    model = model or build_model(settings)
    store = store or FaceStore(settings.db_path)
    auth = auth or TokenAuth.from_settings(settings)

    store.initialize()
    _best_effort_load(model)

    state = AppState(
        settings=settings,
        model=model,
        store=store,
        auth=auth,
        started_at=time.monotonic(),
        semaphore=asyncio.Semaphore(settings.max_concurrency),
    )

    app = FastAPI(
        title="InsightFace-for-openvela",
        version="0.1.0",
        description=(
            "Project-dedicated, isolated face service. Extract/quality are "
            "read-only; verify is 1:1; liveness is NOT supported."
        ),
        # Internal-protocol service: the interactive docs surfaces are not used
        # by the Java adapter and must not expose the schema without a token.
        # FastAPI registers /docs, /redoc and /openapi.json by default; disabling
        # all three makes them 404.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.face = state

    public_router, protected_router = build_router(state)
    app.include_router(public_router)
    app.include_router(protected_router)

    _install_middleware(app, settings)
    _install_exception_handlers(app)
    return app


def _best_effort_load(model: FaceModel) -> None:
    if model.is_loaded:
        return
    try:
        model.load()
        logger.info("face model loaded version=%s", model.version)
    except FaceServiceError as exc:
        # Service still starts; inference will report MODEL_NOT_LOADED/UNAVAILABLE
        # and /v1/health reports model_loaded=false.  Never log secret material.
        logger.error("face model unavailable code=%s", exc.code.value)
    except Exception:  # pragma: no cover - defensive
        logger.error("face model unavailable (unexpected error)")


def sanitized_route(request: Request) -> str:
    """Return a route *template* that never contains real identity values.

    Prefers the matched Starlette route's ``path_format`` (e.g.
    ``/v1/namespaces/{namespace}/subjects/{subject_id}``).  When no route was
    matched (404) it falls back to a sanitized path that keeps only the first
    two segments, so raw namespace/subject values are never logged.
    """
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None)
    if isinstance(path_format, str) and path_format:
        return path_format
    parts = [segment for segment in request.url.path.split("/") if segment]
    if not parts:
        return "/"
    head = "/" + "/".join(parts[:2])
    return head + ("/..." if len(parts) > 2 else "")


def _install_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # noqa: ANN001
        incoming = request.headers.get(settings.request_id_header)
        request_id = incoming if incoming and _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.monotonic()
        response = None
        try:
            response = await call_next(request)
            response.headers[settings.request_id_header] = request_id
            return response
        finally:
            # Reset the contextvar so it never leaks across requests/tasks.
            reset_request_id(token)
            duration_ms = (time.monotonic() - started) * 1000.0
            status = response.status_code if response is not None else 500
            # Sanitized access log: template + method + status + request_id +
            # duration only.  Never the expanded path, namespace, subject_id,
            # image bytes, embedding or token.
            access_logger.info(
                "access method=%s route=%s status=%s duration_ms=%.2f request_id=%s",
                request.method,
                sanitized_route(request),
                status,
                duration_ms,
                request_id,
            )


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(FaceServiceError)
    async def _face_error_handler(request: Request, exc: FaceServiceError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        logger.info(
            "request failed code=%s request_id=%s", exc.code.value, request_id
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_body(request_id))

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        error = FaceServiceError(ErrorCode.INVALID_REQUEST)
        return JSONResponse(status_code=error.http_status, content=error.to_body(request_id))

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        code = ErrorCode.INVALID_REQUEST if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
        return JSONResponse(status_code=exc.status_code, content=error_body(code, None, request_id))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        logger.exception("unhandled error request_id=%s", request_id)
        return JSONResponse(
            status_code=500, content=error_body(ErrorCode.INTERNAL_ERROR, None, request_id)
        )


__all__ = ["create_app"]
