"""Face model abstraction.

``FaceModel`` is the seam the whole service is built on.  **``InsightFaceModel``
is the only place that touches ``insightface``/``onnxruntime`` and it imports
them lazily inside methods**, so the API, store, quality and error layers are
fully importable and testable on a machine where the CV stack is not installed.

Tests inject :class:`FakeModel`; production wires :class:`InsightFaceModel` via
:func:`build_model`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence, runtime_checkable

import numpy as np

from .config import Settings
from .errors import ErrorCode, FaceServiceError
from .quality import decode_rgb_image

BBox = tuple[float, float, float, float]
Landmarks = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class FaceDetection:
    """One detected face with an L2-normalised embedding."""

    bbox: BBox
    det_score: float
    embedding: tuple[float, ...]
    landmarks: Landmarks | None = None

    @property
    def dim(self) -> int:
        return len(self.embedding)


@runtime_checkable
class FaceModel(Protocol):
    """Detection + embedding contract."""

    @property
    def version(self) -> str: ...

    @property
    def is_loaded(self) -> bool: ...

    def load(self) -> None: ...

    def detect_and_embed(self, image_bytes: bytes) -> list[FaceDetection]: ...


def normalize_embedding(vector: np.ndarray) -> tuple[float, ...]:
    """L2-normalise an embedding so cosine similarity is a plain dot product."""
    arr = np.asarray(vector, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        raise FaceServiceError(
            ErrorCode.MODEL_UNAVAILABLE, "model produced a zero-norm embedding"
        )
    return tuple((arr / norm).tolist())


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for two already (or not) normalised vectors."""
    va = np.asarray(a, dtype=np.float64).reshape(-1)
    vb = np.asarray(b, dtype=np.float64).reshape(-1)
    if va.shape != vb.shape:
        raise FaceServiceError(
            ErrorCode.INTERNAL_ERROR,
            "embedding dimension mismatch",
        )
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


class InsightFaceModel:
    """Production model backed by ``insightface.app.FaceAnalysis``.

    The import is deliberately lazy: constructing this object never imports the
    CV stack, and :meth:`load` raises ``MODEL_UNAVAILABLE`` (retryable) instead
    of crashing when it is absent.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._app = None
        self._loaded = False

    @property
    def version(self) -> str:
        return self._settings.model_version

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:  # lazy: the only import of the CV stack in the codebase
                from insightface.app import FaceAnalysis  # type: ignore[import-not-found]
            except Exception as exc:  # pragma: no cover - exercised on real host
                raise FaceServiceError(
                    ErrorCode.MODEL_UNAVAILABLE,
                    "insightface is not installed",
                ) from exc
            try:
                # FaceAnalysis expects the insightface home; weights live in
                # <model_root>/<model_name>, so pass model_root.parent.
                app = FaceAnalysis(
                    name=self._settings.model_name,
                    root=str(self._settings.model_root.parent),
                    providers=list(self._settings.model_providers),
                )
                app.prepare(ctx_id=0, det_size=self._settings.model_det_size)
            except Exception as exc:  # pragma: no cover - exercised on real host
                raise FaceServiceError(
                    ErrorCode.MODEL_UNAVAILABLE,
                    "face model could not be initialised",
                ) from exc
            self._app = app
            self._loaded = True

    def detect_and_embed(self, image_bytes: bytes) -> list[FaceDetection]:
        if not self._loaded:
            self.load()
        rgb = decode_rgb_image(image_bytes)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        assert self._app is not None  # for type-checkers
        faces = self._app.get(bgr)
        detections: list[FaceDetection] = []
        for face in faces:
            bbox = tuple(float(v) for v in face.bbox)  # type: ignore[attr-defined]
            if len(bbox) != 4:  # pragma: no cover - defensive
                continue
            embedding = normalize_embedding(np.asarray(face.embedding))  # type: ignore[attr-defined]
            landmarks: Landmarks | None = None
            raw_kps = getattr(face, "kps", None)
            if raw_kps is not None:
                landmarks = tuple((float(p[0]), float(p[1])) for p in np.asarray(raw_kps))
            detections.append(
                FaceDetection(
                    bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                    det_score=float(getattr(face, "det_score", 0.0)),
                    embedding=embedding,
                    landmarks=landmarks,
                )
            )
        return detections


class FakeModel:
    """Deterministic, dependency-free model used by tests.

    Configure with either ``detections`` (returned for every input) or a
    ``detect_fn`` mapping raw image bytes to detections.  Never touches the
    network, real photos or the CV stack.
    """

    def __init__(
        self,
        *,
        detections: Sequence[FaceDetection] | None = None,
        detect_fn: Callable[[bytes], Sequence[FaceDetection]] | None = None,
        version: str = "fake-model@0",
        loaded: bool = True,
        load_error: bool = False,
    ) -> None:
        self._detections = list(detections) if detections is not None else None
        self._detect_fn = detect_fn
        self._version = version
        self._loaded = loaded
        self._load_error = load_error
        self.load_calls = 0

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self.load_calls += 1
        if self._load_error:
            raise FaceServiceError(ErrorCode.MODEL_UNAVAILABLE, "fake model load failure")
        self._loaded = True

    def detect_and_embed(self, image_bytes: bytes) -> list[FaceDetection]:
        if not self._loaded:
            raise FaceServiceError(ErrorCode.MODEL_NOT_LOADED, "fake model is not loaded")
        if self._detect_fn is not None:
            return list(self._detect_fn(image_bytes))
        if self._detections is not None:
            return list(self._detections)
        raise FaceServiceError(
            ErrorCode.MODEL_UNAVAILABLE, "FakeModel is not configured"
        )


def build_model(settings: Settings) -> FaceModel:
    """Factory used by the production entrypoint."""
    return InsightFaceModel(settings)


__all__ = [
    "BBox",
    "FaceDetection",
    "FaceModel",
    "FakeModel",
    "InsightFaceModel",
    "build_model",
    "cosine_similarity",
    "normalize_embedding",
]
