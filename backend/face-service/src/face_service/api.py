"""FastAPI routes.

All routes return JSON.  Image input is accepted either as a
``multipart/form-data`` file field named ``image`` or as an
``application/json`` body with an ``image_base64`` string (optionally a
``data:image/...;base64,`` URL).  Any other Content-Type is rejected with
``UNSUPPORTED_MEDIA_TYPE``.

Read/write separation is a hard rule:
* ``/v1/extract`` and ``/v1/quality`` are **read-only** (revision is read, never
  written; no subject is ever looked up or inserted).
* ``/v1/verify`` reads exactly one subject and never falls back to a
  whole-library search.
* ``/v1/namespaces/{ns}/search`` is a separate, read-only, namespace-scoped
  1:N search.  It never writes and never returns a candidate list.
* ``/v1/namespaces/{ns}/subjects`` (POST/DELETE) are the only write paths.
* ``/live`` and ``/ready`` are public probes; ``/v1/health`` is unchanged.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextvars
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .auth import TokenAuth, make_auth_dependency
from .config import Settings
from .errors import ErrorCode, FaceServiceError
from .model import FaceModel, FaceDetection, cosine_similarity
from .quality import decode_rgb_image, evaluate_quality, liveness_block
from .store import FaceStore

logger = logging.getLogger("face_service.api")

_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

#: Version tag for the server-fixed 1:N decision policy.  Bump when the
#: decision rules or their interpretation change (clients record this to know
#: which policy produced a decision).
SEARCH_POLICY_VERSION = "search-v1"


@dataclass
class AppState:
    settings: Settings
    model: FaceModel
    store: FaceStore
    auth: TokenAuth
    started_at: float
    semaphore: asyncio.Semaphore


_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "face_service_request_id", default="unknown"
)


# --------------------------------------------------------------------------
# payload / param helpers
# --------------------------------------------------------------------------
async def _read_image_payload(request: Request, settings: Settings) -> tuple[bytes, dict[str, Any]]:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_body_bytes:
        raise FaceServiceError(
            ErrorCode.IMAGE_TOO_LARGE, details={"max_bytes": settings.max_body_bytes}
        )
    body = await request.body()
    if len(body) > settings.max_body_bytes:
        raise FaceServiceError(
            ErrorCode.IMAGE_TOO_LARGE, details={"max_bytes": settings.max_body_bytes}
        )
    if not body:
        raise FaceServiceError(ErrorCode.INVALID_REQUEST, "empty request body")

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "multipart/form-data":
        form = await request.form()
        upload = form.get("image")
        if upload is None:
            raise FaceServiceError(ErrorCode.INVALID_REQUEST, "missing 'image' form field")
        if isinstance(upload, str):
            raise FaceServiceError(
                ErrorCode.INVALID_REQUEST, "'image' must be a file upload"
            )
        image = await upload.read()
        params: dict[str, Any] = {
            key: value for key, value in form.items() if key != "image" and isinstance(value, str)
        }
        return image, params

    if content_type == "application/json":
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FaceServiceError(ErrorCode.INVALID_REQUEST, "invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise FaceServiceError(ErrorCode.INVALID_REQUEST, "JSON body must be an object")
        encoded = payload.get("image_base64")
        if not isinstance(encoded, str) or not encoded:
            raise FaceServiceError(
                ErrorCode.INVALID_REQUEST, "missing 'image_base64' string"
            )
        if encoded.strip().startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            image = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FaceServiceError(
                ErrorCode.IMAGE_DECODE_FAILED, "image_base64 is not valid base64"
            ) from exc
        params = {k: v for k, v in payload.items() if k != "image_base64"}
        return image, params

    raise FaceServiceError(ErrorCode.UNSUPPORTED_MEDIA_TYPE)


def _require_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise FaceServiceError(
            ErrorCode.INVALID_REQUEST,
            f"'{field_name}' must match [A-Za-z0-9._:-]{{1,128}}",
        )
    return value


def _optional_id(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return _require_id(value, field_name)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FaceServiceError(
            ErrorCode.INVALID_REQUEST, f"'{field_name}' must be a number"
        ) from exc


def _as_top_k(value: Any, default: int) -> int:
    """Parse the optional ``top_k`` integer within the fixed 2..10 domain.

    ``top_k`` only bounds the candidate window used by the margin/ambiguity
    rule (this endpoint never returns a candidate list and there is no vector
    index).  The lower bound is therefore **2**: with a single candidate there
    is no runner-up and the margin check would be structurally vacuous, so a
    near-tied library could report ``matched`` -- a caller-triggerable
    weakening of ambiguity protection.

    Non-integers (including booleans and fractional floats) and out-of-range
    values are rejected with the existing ``INVALID_REQUEST`` code -- no new
    synonym code is invented.
    """
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise FaceServiceError(ErrorCode.INVALID_REQUEST, "'top_k' must be an integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise FaceServiceError(ErrorCode.INVALID_REQUEST, "'top_k' must be an integer")
        parsed = int(value)
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise FaceServiceError(
                ErrorCode.INVALID_REQUEST, "'top_k' must be an integer"
            ) from exc
    else:
        raise FaceServiceError(ErrorCode.INVALID_REQUEST, "'top_k' must be an integer")
    if not (2 <= parsed <= 10):
        raise FaceServiceError(
            ErrorCode.INVALID_REQUEST, "'top_k' must be within 2..10"
        )
    return parsed


def _ensure_liveness_supported(params: dict[str, Any]) -> None:
    """Honest gate: any explicit liveness requirement is refused, not faked."""
    if _as_bool(params.get("require_liveness")):
        raise FaceServiceError(ErrorCode.LIVENESS_UNSUPPORTED)


async def _run_model(state: AppState, image_bytes: bytes) -> list[FaceDetection]:
    settings = state.settings
    semaphore = state.semaphore
    if semaphore.locked():
        raise FaceServiceError(ErrorCode.CONCURRENCY_LIMIT)
    await semaphore.acquire()
    try:
        loop = asyncio.get_running_loop()
        if not state.model.is_loaded:
            await asyncio.wait_for(
                loop.run_in_executor(None, state.model.load),
                timeout=settings.inference_timeout_seconds,
            )
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, state.model.detect_and_embed, image_bytes),
                timeout=settings.inference_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise FaceServiceError(ErrorCode.INFERENCE_TIMEOUT) from exc
        except FaceServiceError:
            raise
        except Exception as exc:  # pragma: no cover - real model failure path
            logger.error("inference failure request_id=%s", _request_id())
            raise FaceServiceError(ErrorCode.INTERNAL_ERROR) from exc
    finally:
        semaphore.release()


def _request_id() -> str:
    return _REQUEST_ID.get()


def set_request_id(value: str) -> contextvars.Token:
    return _REQUEST_ID.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _REQUEST_ID.reset(token)


def _largest_index(detections: list[FaceDetection]) -> int | None:
    if not detections:
        return None
    best = 0
    best_area = -1.0
    for idx, det in enumerate(detections):
        x1, y1, x2, y2 = det.bbox
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if area > best_area:
            best_area = area
            best = idx
    return best


def _quality_for(state: AppState, det: FaceDetection, image) -> dict[str, Any]:
    s = state.settings
    return evaluate_quality(
        bbox=det.bbox,
        det_score=det.det_score,
        image=image,
        min_det_score=s.quality_min_det_score,
        min_blur=s.quality_min_blur,
        min_bbox_ratio=s.quality_min_bbox_ratio,
        landmarks_available=det.landmarks is not None,
    )


def _analyze(
    state: AppState, image: Any, detections: list[FaceDetection]
) -> tuple[Any, list[dict[str, Any]], int | None]:
    largest = _largest_index(detections)
    faces: list[dict[str, Any]] = []
    for idx, det in enumerate(detections):
        faces.append({"detection": det, "quality": _quality_for(state, det, image)})
    return image, faces, largest


async def _decode_and_detect(
    state: AppState, image_bytes: bytes
) -> tuple[Any, list[FaceDetection]]:
    """Decode first (authoritative ``IMAGE_DECODE_FAILED``), then infer."""
    image = decode_rgb_image(image_bytes)
    detections = await _run_model(state, image_bytes)
    return image, detections


# --------------------------------------------------------------------------
# router
# --------------------------------------------------------------------------
def build_router(state: AppState) -> tuple[APIRouter, APIRouter]:
    """Return ``(public_router, protected_router)``."""
    settings = state.settings
    public = APIRouter()
    protected = APIRouter(
        dependencies=[Depends(make_auth_dependency(state.auth))]
    )

    def _rev() -> int:
        return state.store.revision()

    # ---- health (public, read-only) ------------------------------------
    @public.get("/v1/health")
    async def health() -> dict[str, Any]:
        loaded = state.model.is_loaded
        return {
            "status": "ok" if loaded else "degraded",
            "model_loaded": loaded,
            "model_version": state.model.version,
            "library_revision": _rev(),
            "uptime_seconds": round(time.monotonic() - state.started_at, 3),
            "liveness": liveness_block(),
        }

    # ---- /live and /ready (public probes; /v1/health is left untouched) --
    @public.get("/live")
    async def live() -> dict[str, Any]:
        """Process liveness only: no model, no SQLite, no auth.

        If this returns, the process is alive.  It deliberately proves nothing
        about readiness.
        """
        return {"status": "alive"}

    @public.get("/ready")
    async def ready() -> dict[str, Any]:
        """Readiness: model loaded AND the subject store reachable.

        Unlike ``/v1/health`` this must FAIL (non-2xx) when the service cannot
        serve identity decisions: "not ready" is a refusal, not a status string.
        """
        if not state.model.is_loaded:
            # Model is the more fundamental prerequisite; when both are down we
            # report this one.  The log may mention the store separately.
            logger.warning("readiness failed code=MODEL_NOT_LOADED request_id=%s", _request_id())
            raise FaceServiceError(ErrorCode.MODEL_NOT_LOADED)
        try:
            revision = state.store.revision()
        except Exception:  # exercised by the injected-store readiness test
            # Never log the path or the underlying message (may contain a path).
            logger.error("readiness failed code=STORE_UNAVAILABLE request_id=%s", _request_id())
            raise FaceServiceError(ErrorCode.STORE_UNAVAILABLE) from None
        return {
            "status": "ready",
            "model_loaded": True,
            "model_version": state.model.version,
            "library_revision": revision,
        }

    # ---- extract (read-only, zero writes) ------------------------------
    @protected.post("/v1/extract")
    async def extract(request: Request) -> dict[str, Any]:
        image_bytes, params = await _read_image_payload(request, settings)
        namespace = _optional_id(params.get("namespace"), "namespace")
        image, detections = await _decode_and_detect(state, image_bytes)
        if not detections:
            raise FaceServiceError(ErrorCode.NO_FACE)
        _, faces, largest = _analyze(state, image, detections)

        out_faces: list[dict[str, Any]] = []
        for idx, face in enumerate(faces):
            det: FaceDetection = face["detection"]
            out_faces.append(
                {
                    "bbox": [float(v) for v in det.bbox],
                    "det_score": float(det.det_score),
                    "embedding": [float(v) for v in det.embedding],
                    "dim": det.dim,
                    "quality": face["quality"],
                    "largest_face": idx == largest,
                }
            )
        return {
            "face_count": len(out_faces),
            "faces": out_faces,
            "largest_face_index": largest,
            "namespace": namespace,
            "model_version": state.model.version,
            "library_revision": _rev(),
            "liveness": liveness_block(),
            "request_id": _request_id(),
        }

    # ---- quality (read-only, zero writes) ------------------------------
    @protected.post("/v1/quality")
    async def quality(request: Request) -> dict[str, Any]:
        image_bytes, params = await _read_image_payload(request, settings)
        namespace = _optional_id(params.get("namespace"), "namespace")
        image, detections = await _decode_and_detect(state, image_bytes)
        if not detections:
            raise FaceServiceError(ErrorCode.NO_FACE)
        _, faces, largest = _analyze(state, image, detections)
        return {
            "face_count": len(faces),
            "faces": [
                {
                    "bbox": [float(v) for v in face["detection"].bbox],
                    "det_score": float(face["detection"].det_score),
                    "quality": face["quality"],
                    "largest_face": idx == largest,
                }
                for idx, face in enumerate(faces)
            ],
            "largest_face_index": largest,
            "namespace": namespace,
            "model_version": state.model.version,
            "library_revision": _rev(),
            "liveness": liveness_block(),
            "request_id": _request_id(),
        }

    # ---- verify (1:1, read-only) ---------------------------------------
    @protected.post("/v1/verify")
    async def verify(request: Request) -> dict[str, Any]:
        image_bytes, params = await _read_image_payload(request, settings)
        _ensure_liveness_supported(params)
        namespace = _require_id(params.get("namespace"), "namespace")
        subject_id = _require_id(params.get("subject_id"), "subject_id")
        threshold = settings.verify_threshold
        if params.get("threshold") not in (None, ""):
            threshold = _as_float(params.get("threshold"), "threshold")
            if not (0.0 <= threshold <= 1.0):
                raise FaceServiceError(
                    ErrorCode.INVALID_REQUEST, "'threshold' must be within 0..1"
                )

        if not state.store.namespace_exists(namespace):
            raise FaceServiceError(
                ErrorCode.NAMESPACE_NOT_FOUND, details={"namespace": namespace}
            )

        image, detections = await _decode_and_detect(state, image_bytes)
        if not detections:
            raise FaceServiceError(ErrorCode.NO_FACE)
        if len(detections) > 1:
            raise FaceServiceError(
                ErrorCode.MULTI_FACES_AMBIGUOUS, details={"face_count": len(detections)}
            )
        _, faces, _ = _analyze(state, image, detections)

        # 1:1 only: fetch exactly the requested subject; never search the library.
        record = state.store.get(namespace, subject_id)
        if record is None:
            raise FaceServiceError(
                ErrorCode.SUBJECT_NOT_FOUND,
                details={"namespace": namespace, "subject_id": subject_id},
            )

        similarity = cosine_similarity(detections[0].embedding, record.embedding)
        return {
            "matched": similarity >= threshold,
            "similarity": similarity,
            "threshold": threshold,
            "face_count": len(detections),
            "quality": faces[0]["quality"],
            "liveness": liveness_block(),
            "namespace": namespace,
            "subject_id": subject_id,
            "model_version": state.model.version,
            "library_revision": _rev(),
            "request_id": _request_id(),
        }

    # ---- register subject (write path) ---------------------------------
    @protected.post("/v1/namespaces/{namespace}/subjects")
    async def register(namespace: str, request: Request) -> JSONResponse:
        namespace = _require_id(namespace, "namespace")
        image_bytes, params = await _read_image_payload(request, settings)
        _ensure_liveness_supported(params)
        subject_id = _require_id(params.get("subject_id"), "subject_id")
        on_exists = str(params.get("on_exists") or settings.register_on_exists).strip().lower()
        if on_exists not in {"conflict", "overwrite"}:
            raise FaceServiceError(
                ErrorCode.INVALID_REQUEST, "'on_exists' must be 'conflict' or 'overwrite'"
            )

        image, detections = await _decode_and_detect(state, image_bytes)
        if not detections:
            raise FaceServiceError(ErrorCode.NO_FACE)
        if len(detections) > 1:
            raise FaceServiceError(
                ErrorCode.MULTI_FACES_AMBIGUOUS, details={"face_count": len(detections)}
            )
        _, faces, _ = _analyze(state, image, detections)
        quality = faces[0]["quality"]
        if settings.quality_enforce and not quality["min_acceptable"]:
            raise FaceServiceError(ErrorCode.QUALITY_INSUFFICIENT)

        result = state.store.register(
            namespace=namespace,
            subject_id=subject_id,
            embedding=detections[0].embedding,
            model_version=state.model.version,
            quality=quality,
            det_score=float(detections[0].det_score),
            bbox=[float(v) for v in detections[0].bbox],
            on_exists=on_exists,
        )
        record = result.record
        body = {
            "subject_id": record.subject_id,
            "namespace": record.namespace,
            "created": result.created,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "embedding_dim": record.embedding_dim,
            "model_version": record.model_version,
            "quality": record.quality,
            "library_revision": result.library_revision,
            "request_id": _request_id(),
        }
        return JSONResponse(status_code=201 if result.created else 200, content=body)

    # ---- get subject (read-only, no embedding) -------------------------
    @protected.get("/v1/namespaces/{namespace}/subjects/{subject_id}")
    async def get_subject(namespace: str, subject_id: str) -> dict[str, Any]:
        namespace = _require_id(namespace, "namespace")
        subject_id = _require_id(subject_id, "subject_id")
        if not state.store.namespace_exists(namespace):
            raise FaceServiceError(
                ErrorCode.NAMESPACE_NOT_FOUND, details={"namespace": namespace}
            )
        record = state.store.get(namespace, subject_id)
        if record is None:
            raise FaceServiceError(
                ErrorCode.SUBJECT_NOT_FOUND,
                details={"namespace": namespace, "subject_id": subject_id},
            )
        body = record.to_meta()
        body["library_revision"] = _rev()
        body["request_id"] = _request_id()
        return body

    # ---- delete subject (write path) -----------------------------------
    @protected.delete("/v1/namespaces/{namespace}/subjects/{subject_id}")
    async def delete_subject(namespace: str, subject_id: str) -> dict[str, Any]:
        namespace = _require_id(namespace, "namespace")
        subject_id = _require_id(subject_id, "subject_id")
        if not state.store.namespace_exists(namespace):
            raise FaceServiceError(
                ErrorCode.NAMESPACE_NOT_FOUND, details={"namespace": namespace}
            )
        deleted, revision = state.store.delete(namespace=namespace, subject_id=subject_id)
        if not deleted:
            raise FaceServiceError(
                ErrorCode.SUBJECT_NOT_FOUND,
                details={"namespace": namespace, "subject_id": subject_id},
            )
        return {
            "deleted": True,
            "subject_id": subject_id,
            "namespace": namespace,
            "library_revision": revision,
            "request_id": _request_id(),
        }

    # ---- namespace info (read-only) ------------------------------------
    @protected.get("/v1/namespaces/{namespace}/info")
    async def namespace_info(namespace: str) -> dict[str, Any]:
        namespace = _require_id(namespace, "namespace")
        if not state.store.namespace_exists(namespace):
            raise FaceServiceError(
                ErrorCode.NAMESPACE_NOT_FOUND, details={"namespace": namespace}
            )
        return {
            "namespace": namespace,
            "subject_count": state.store.count_subjects(namespace),
            "library_revision": _rev(),
            "model_version": state.model.version,
            "request_id": _request_id(),
        }

    # ---- 1:N search (read-only, namespace-scoped) ----------------------
    @protected.post("/v1/namespaces/{namespace}/search")
    async def search(namespace: str, request: Request) -> dict[str, Any]:
        """Internal 1:N search.  Read-only; never creates a subject.

        The result is a conservative three-state decision.  Matching thresholds
        are **server-fixed** (``policy_version``); no client threshold is parsed.
        The response never exposes the candidate list, embeddings, a non-matched
        ``subject_id`` or any similarity for a non-matched decision.
        """
        namespace = _require_id(namespace, "namespace")
        image_bytes, params = await _read_image_payload(request, settings)
        top_k = _as_top_k(params.get("top_k"), settings.search_top_k)

        if not state.store.namespace_exists(namespace):
            raise FaceServiceError(
                ErrorCode.NAMESPACE_NOT_FOUND, details={"namespace": namespace}
            )

        image, detections = await _decode_and_detect(state, image_bytes)
        if not detections:
            raise FaceServiceError(ErrorCode.NO_FACE)
        if len(detections) > 1:
            raise FaceServiceError(
                ErrorCode.MULTI_FACES_AMBIGUOUS, details={"face_count": len(detections)}
            )
        _, faces, _ = _analyze(state, image, detections)
        quality = faces[0]["quality"]
        query_embedding = detections[0].embedding

        snapshot = state.store.search_candidates(namespace)
        # Similarity-descending, subject_id-ascending tie-break so equal scores
        # are deterministic and reproducible.
        ranked = sorted(
            (
                (cosine_similarity(query_embedding, embedding), subject_id)
                for subject_id, embedding in snapshot.candidates
            ),
            key=lambda item: (-item[0], item[1]),
        )[:top_k]

        best: float | None = None
        reasons: list[str] = []
        if snapshot.subject_count == 0:
            # An empty library is an evidence-backed miss, but not proof of a
            # reliable new person (see README).
            decision = "no_match"
            ambiguous = False
            reasons.append("empty_library")
        else:
            best = ranked[0][0]
            second = ranked[1][0] if len(ranked) > 1 else None
            margin_ok = second is None or (best - second) >= settings.search_margin
            if best >= settings.search_match_threshold and margin_ok:
                decision, ambiguous = "matched", False
            elif best >= settings.search_match_threshold:
                decision, ambiguous = "uncertain", True
                reasons.append("ambiguous_top_candidates")
            elif best >= settings.search_match_threshold - settings.search_uncertain_band:
                decision, ambiguous = "uncertain", False
                reasons.append("similarity_in_uncertain_band")
            else:
                decision, ambiguous = "no_match", False
                reasons.append("no_candidates_above_threshold")
            if not quality["min_acceptable"]:
                # Fail-closed: a poor-quality probe may never yield "matched".
                reasons.append("quality_below_minimum")
                if decision == "matched":
                    decision, ambiguous = "uncertain", False

        body: dict[str, Any] = {
            "decision": decision,
            "ambiguous": ambiguous,
            "quality": quality,
            "subject_count": snapshot.subject_count,
            "top_k": top_k,
            "reasons": reasons,
            "policy_version": SEARCH_POLICY_VERSION,
            "model_version": state.model.version,
            "library_revision": snapshot.revision,
            "request_id": _request_id(),
        }
        if decision == "matched" and best is not None:
            body["subject_id"] = ranked[0][1]
            body["similarity"] = best
        return body

    return public, protected


__all__ = ["AppState", "build_router", "set_request_id", "reset_request_id"]
