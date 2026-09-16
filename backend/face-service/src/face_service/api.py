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
* ``/v1/compare`` compares two **probe** images.  It reads no subject at all, so
  it cannot disclose library contents, and it never writes.
* ``/v1/namespaces/{ns}/search`` is a separate, read-only, namespace-scoped
  1:N search.  It never writes and never returns a candidate list.
* ``/v1/namespaces/{ns}/registrations/{correlation_id}`` is a read-only
  reconciliation lookup used after a lost register response.
* ``/v1/namespaces/{ns}/subjects`` (POST/DELETE) are the only write paths.
* ``/live`` and ``/ready`` are public probes; ``/v1/health`` is unchanged.

Decision vocabulary for search is ``matched`` / ``uncertain`` / ``reliable_new``
(``policy_version`` ``search-v2``) — the exact set the Worker ``FacePort``
contract consumes; see ``backend/handoffs/B-face-service-worker-contract.md``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextvars
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
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
#:
#: ``search-v2`` (2026-09-16): the decision vocabulary was aligned with the
#: Worker ``FacePort`` contract (``matched`` / ``uncertain`` / ``reliable_new``),
#: replacing the previous ``no_match``, and an **empty library now yields
#: ``uncertain``** instead of a miss.  Consumers record this tag for audit.
SEARCH_POLICY_VERSION = "search-v2"


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


async def _read_two_image_payload(
    request: Request, settings: Settings
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Read a two-image payload (``POST /v1/compare``).

    Mirrors :func:`_read_image_payload` on every rule that matters — the same
    ``max_body_bytes`` limit, the same ``IMAGE_TOO_LARGE`` / ``INVALID_REQUEST`` /
    ``IMAGE_DECODE_FAILED`` / ``UNSUPPORTED_MEDIA_TYPE`` mapping, and the same
    ``data:...,`` prefix handling — but takes two image fields
    (``image_a``/``image_b`` for multipart, ``image_a_base64``/``image_b_base64``
    for JSON) instead of one.

    ``_read_image_payload`` is deliberately left untouched so the existing
    single-image endpoints keep byte-identical behaviour.
    """
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
        images: list[bytes] = []
        for field in ("image_a", "image_b"):
            upload = form.get(field)
            if upload is None:
                raise FaceServiceError(
                    ErrorCode.INVALID_REQUEST, f"missing '{field}' form field"
                )
            if isinstance(upload, str):
                raise FaceServiceError(
                    ErrorCode.INVALID_REQUEST, f"'{field}' must be a file upload"
                )
            images.append(await upload.read())
        params: dict[str, Any] = {
            key: value
            for key, value in form.items()
            if key not in ("image_a", "image_b") and isinstance(value, str)
        }
        return images[0], images[1], params

    if content_type == "application/json":
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FaceServiceError(ErrorCode.INVALID_REQUEST, "invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise FaceServiceError(ErrorCode.INVALID_REQUEST, "JSON body must be an object")
        decoded: list[bytes] = []
        for field in ("image_a_base64", "image_b_base64"):
            encoded = payload.get(field)
            if not isinstance(encoded, str) or not encoded:
                raise FaceServiceError(
                    ErrorCode.INVALID_REQUEST, f"missing '{field}' string"
                )
            if encoded.strip().startswith("data:") and "," in encoded:
                encoded = encoded.split(",", 1)[1]
            try:
                decoded.append(base64.b64decode(encoded, validate=True))
            except (binascii.Error, ValueError) as exc:
                raise FaceServiceError(
                    ErrorCode.IMAGE_DECODE_FAILED, f"{field} is not valid base64"
                ) from exc
        params = {
            key: value
            for key, value in payload.items()
            if key not in ("image_a_base64", "image_b_base64")
        }
        return decoded[0], decoded[1], params

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


def _require_finite_embeddings(detections: list[FaceDetection]) -> None:
    """Refuse a numerically unusable embedding **before** any decision is formed.

    Guarding here (rather than only inside ``cosine_similarity``) is deliberate:
    the empty-library branch of search never computes a similarity at all, so a
    NaN probe would otherwise sail through and be reported as ``reliable_new`` —
    a numerical model fault turned into an identity classification.  Checking once
    at the model boundary covers every consumer (extract, quality, verify,
    compare, search) and cannot be forgotten by a new endpoint.

    Three shapes are refused, all of which are faults rather than answers:
    * **non-finite** (NaN/Inf) — every threshold comparison against NaN is False,
      so it used to fall through to ``reliable_new``;
    * **empty** — a zero-length vector carries no identity information, and the
      previous ``values.size and ...`` guard skipped it entirely;
    * **zero-norm** — cosine similarity is undefined for it (``cosine_similarity``
      returns 0.0 for compatibility, which on an empty library would again read
      as "no candidate matched").

    ``normalize_embedding`` already refuses non-finite and zero-norm values for
    the production model, but ``FakeModel`` returns ``detect_fn`` output verbatim
    and a stored row could be corrupted, so this is real defence in depth.
    """
    for detection in detections:
        values = np.asarray(detection.embedding, dtype=np.float64).reshape(-1)
        if values.size == 0:
            raise FaceServiceError(
                ErrorCode.MODEL_UNAVAILABLE, "model produced an empty embedding"
            )
        if not bool(np.isfinite(values).all()):
            raise FaceServiceError(
                ErrorCode.MODEL_UNAVAILABLE, "model produced a non-finite embedding"
            )
        norm = float(np.linalg.norm(values))
        if not math.isfinite(norm) or norm <= 0.0:
            raise FaceServiceError(
                ErrorCode.MODEL_UNAVAILABLE, "model produced a zero-norm embedding"
            )


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
            detections = await asyncio.wait_for(
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
        _require_finite_embeddings(detections)
        return detections
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

    # ---- compare two probe images (read-only, zero writes) --------------
    @protected.post("/v1/compare")
    async def compare(request: Request) -> dict[str, Any]:
        """Image-to-image 1:1 comparison.  Read-only; never touches the library.

        Supports ``FacePort.same_person`` (three-view "same person" confirmation).
        Unlike ``/v1/verify`` this compares two **probe** images, so it reads no
        subject and cannot disclose library contents.

        Deliberately does **not** accept ``require_liveness``: photo comparison has
        no anti-replay capability, and accepting the field would imply otherwise.
        Liveness is reported as ``supported=false`` and is never faked.

        ``threshold`` is **server-fixed** (``FACE_SVC_VERIFY_THRESHOLD``) and a
        client-supplied value is ignored — not merely validated.  A caller who
        could lower it would directly control the ``same_person`` verdict (0.0
        would declare any two images the same person); "this endpoint reads no
        library" does not make that safe, and ``FacePort.same_person(images)``
        takes no threshold, so no consumer needs one.  This also keeps compare
        consistent with search, which never accepted a client threshold.
        """
        image_a_bytes, image_b_bytes, params = await _read_two_image_payload(
            request, settings
        )
        threshold = settings.verify_threshold

        image_a, detections_a = await _decode_and_detect(state, image_a_bytes)
        image_b, detections_b = await _decode_and_detect(state, image_b_bytes)
        if not detections_a or not detections_b:
            raise FaceServiceError(ErrorCode.NO_FACE)
        if len(detections_a) > 1 or len(detections_b) > 1:
            # Never pick "the largest face" here: with two probes it would be
            # ambiguous which face was compared against which.
            raise FaceServiceError(
                ErrorCode.MULTI_FACES_AMBIGUOUS,
                details={
                    "face_count_a": len(detections_a),
                    "face_count_b": len(detections_b),
                },
            )

        _, faces_a, _ = _analyze(state, image_a, detections_a)
        _, faces_b, _ = _analyze(state, image_b, detections_b)
        quality_a = faces_a[0]["quality"]
        quality_b = faces_b[0]["quality"]

        similarity = cosine_similarity(
            detections_a[0].embedding, detections_b[0].embedding
        )
        reasons: list[str] = []
        matched = similarity >= threshold
        if not (quality_a["min_acceptable"] and quality_b["min_acceptable"]):
            # Fail-closed: a poor-quality probe may never confirm "same person".
            reasons.append("quality_below_minimum")
            matched = False

        return {
            "matched": matched,
            "similarity": similarity,
            "threshold": threshold,
            "face_count_a": len(detections_a),
            "face_count_b": len(detections_b),
            "quality_a": quality_a,
            "quality_b": quality_b,
            "liveness": liveness_block(),
            "reasons": reasons,
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
        # Reconciliation keys (contract §6.1).  Both optional so pre-existing
        # callers keep their exact behaviour; when ``correlation_id`` is present it
        # makes registration idempotent across retries.
        correlation_id = _optional_id(params.get("correlation_id"), "correlation_id")
        provider_request_id = _optional_id(
            params.get("provider_request_id"), "provider_request_id"
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
            correlation_id=correlation_id,
            provider_request_id=provider_request_id,
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
            # True only for an idempotent replay of the same correlation_id: the
            # stored subject is returned as-is (no overwrite, no revision bump).
            "replayed": result.replayed,
            "registered_at": record.registered_at,
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
    # ---- registration reconciliation (read-only, zero writes) -----------
    @protected.get("/v1/namespaces/{namespace}/registrations/{correlation_id}")
    async def get_registration(
        namespace: str, correlation_id: str, request: Request
    ) -> dict[str, Any]:
        """Look up a prior enrollment by ``correlation_id`` (contract §6.2).

        Read-only: creates no namespace, writes nothing and never bumps
        ``library_revision``.  Optional ``provider_request_id`` / ``entity_id``
        query params tighten the match; a disagreement is reported as
        ``not_found`` rather than returning a subject that does not correspond to
        the caller's own attempt.

        ``status`` is only ever ``registered`` or ``not_found``.  ``unknown`` is a
        **client-side** transport state and is deliberately never produced here —
        a service that fabricated it would mask real failures.

        Minimum disclosure: no embedding, no reference-image ref, no other
        correlation's registration, no library listing.
        """
        namespace = _require_id(namespace, "namespace")
        correlation_id = _require_id(correlation_id, "correlation_id")
        provider_request_id = _optional_id(
            request.query_params.get("provider_request_id"), "provider_request_id"
        )
        entity_id = _optional_id(request.query_params.get("entity_id"), "entity_id")

        if not state.store.namespace_exists(namespace):
            raise FaceServiceError(
                ErrorCode.NAMESPACE_NOT_FOUND, details={"namespace": namespace}
            )

        record = state.store.find_registration(
            namespace=namespace,
            correlation_id=correlation_id,
            provider_request_id=provider_request_id,
            entity_id=entity_id,
        )
        if record is None:
            return {"status": "not_found", "request_id": _request_id()}
        return {
            "status": "registered",
            "subject_id": record.subject_id,
            "correlation_id": record.correlation_id,
            "provider_request_id": record.provider_request_id,
            "registered_at": record.registered_at,
            "library_revision": record.library_revision,
            "request_id": _request_id(),
        }

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

        # A namespace that does not exist yet is treated as an **empty read-only
        # snapshot**, not as a 404.  Search never creates anything, so this stays
        # read-only; but refusing here would deadlock first enrollment: the Worker
        # only enqueues ``identity.enroll`` for ``reliable_new``
        # (``assessment_analyze.py:377-388``) and answers ``uncertain`` with a
        # re-capture (``:369-375``), and a re-capture cannot make an empty library
        # non-empty.  Every namespace starts empty, so 404/uncertain here would
        # mean no first member could ever be created through the business flow.
        # The gate against *automatic* enrollment belongs to the business layer
        # (``后端详细设计-V1-MVP.md:663`` PoC gate + the Worker's own PostgreSQL
        # reconciliation), not to this read-only algorithm endpoint.

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
        if snapshot.subject_count == 0 or not snapshot.candidates:
            # An empty (or not-yet-created) library holds no candidate, so nothing
            # can match.  This is reported as ``reliable_new`` **only when the probe
            # quality is acceptable**, because the Worker enqueues first enrollment
            # solely on ``reliable_new``; answering ``uncertain`` here would make
            # the first member of every namespace unreachable (a re-capture cannot
            # fill an empty library).  ``reasons`` always carries ``empty_library``
            # so consumers and audits can tell "no candidate reached the threshold
            # in a populated library" apart from "the library was empty".
            #
            # This does **not** license automatic enrollment: the PoC gate
            # (``后端详细设计-V1-MVP.md:663``) and the Worker's own PostgreSQL
            # reconciliation (``assessment_analyze.py:381-389``) remain the
            # authoritative controls, and they live in the business layer.
            if quality["min_acceptable"]:
                decision, ambiguous = "reliable_new", False
            else:
                # Fail-closed: a poor-quality probe may never open enrollment.
                decision, ambiguous = "uncertain", False
                reasons.append("quality_below_minimum")
            reasons.insert(0, "empty_library")
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
                # Clearly below the band, in a non-empty namespace, single face and
                # (subject to the quality gate below) acceptable quality.  This is
                # "no candidate in *this* namespace reached the threshold" — it is
                # **not** proof of a new human being, and the business layer must
                # still honour the PoC gate before auto-enrolling anyone.
                decision, ambiguous = "reliable_new", False
                reasons.append("no_candidates_above_threshold")
            if not quality["min_acceptable"]:
                # Fail-closed: a poor-quality probe may never yield "matched", and
                # may never be promoted to "reliable_new" either.
                reasons.append("quality_below_minimum")
                if decision in ("matched", "reliable_new"):
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
