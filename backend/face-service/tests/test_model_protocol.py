"""Model seam: lazy insightface import, protocol conformance, math helpers."""

from __future__ import annotations

import importlib.util
import sys

import numpy as np
import pytest

from face_service.errors import ErrorCode, FaceServiceError
from face_service.model import (
    FaceDetection,
    FaceModel,
    FakeModel,
    InsightFaceModel,
    cosine_similarity,
    normalize_embedding,
)


def test_app_modules_import_without_insightface():
    """The whole service must be importable without the CV stack installed."""
    import face_service.api  # noqa: F401
    import face_service.app  # noqa: F401
    import face_service.quality  # noqa: F401
    import face_service.store  # noqa: F401

    assert "insightface" not in sys.modules
    assert "onnxruntime" not in sys.modules


def test_fake_model_satisfies_protocol():
    assert isinstance(FakeModel(), FaceModel)
    assert isinstance(InsightFaceModel.__new__(InsightFaceModel), FaceModel)


def test_constructing_insightface_model_does_not_import_cv_stack(settings):
    before = set(sys.modules)
    InsightFaceModel(settings)
    assert "insightface" not in (set(sys.modules) - before)


@pytest.mark.skipif(
    importlib.util.find_spec("insightface") is not None,
    reason="insightface is installed in this environment",
)
def test_insightface_model_load_reports_model_unavailable(settings):
    model = InsightFaceModel(settings)
    assert model.is_loaded is False
    with pytest.raises(FaceServiceError) as exc:
        model.load()
    assert exc.value.code is ErrorCode.MODEL_UNAVAILABLE
    assert exc.value.retryable is True


def test_fake_model_load_error_and_not_loaded():
    model = FakeModel(loaded=False, load_error=True)
    with pytest.raises(FaceServiceError) as exc:
        model.detect_and_embed(b"x")
    assert exc.value.code is ErrorCode.MODEL_NOT_LOADED


def test_normalize_embedding_unit_norm():
    vec = normalize_embedding(np.array([3.0, 4.0]))
    assert pytest.approx(np.linalg.norm(vec), rel=1e-9) == 1.0


def test_normalize_embedding_zero_norm_rejected():
    with pytest.raises(FaceServiceError):
        normalize_embedding(np.zeros(3))


def test_cosine_similarity_identical_and_orthogonal():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([2.0, 0.0], [5.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_dimension_mismatch():
    with pytest.raises(FaceServiceError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_face_detection_dim_property():
    det = FaceDetection(bbox=(0, 0, 1, 1), det_score=0.5, embedding=(1.0, 0.0))
    assert det.dim == 2
