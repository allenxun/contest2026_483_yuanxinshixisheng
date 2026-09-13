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

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def create_app(
    *,
    settings: Settings | None = None,
    model: FaceModel | None = None,
    store: FaceStore | None = None,
    auth: TokenAuth | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
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


def _install_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # noqa: ANN001
        incoming = request.headers.get(settings.request_id_header)
        request_id = incoming if incoming and _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            # Reset the contextvar so it never leaks across requests/tasks.
            reset_request_id(token)
        response.headers[settings.request_id_header] = request_id
        return response


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
