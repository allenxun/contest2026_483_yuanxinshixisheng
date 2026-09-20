"""Shared fixtures.

Tests never import insightface/onnxruntime and never download models.  They use
synthetic PIL images plus an injected :class:`FakeModel`.
"""

from __future__ import annotations

import hashlib
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from face_service.app import create_app
from face_service.auth import TokenAuth
from face_service.model import FaceDetection, FakeModel
from face_service.store import FaceStore

EMBEDDING_DIM = 64


# --------------------------------------------------------------------------
# synthetic images + deterministic embeddings
# --------------------------------------------------------------------------
def make_image(seed: int = 1, width: int = 64, height: int = 64) -> bytes:
    """A synthetic, non-uniform image.  Distinct seeds -> distinct bytes."""
    xs = np.linspace(0, 255, width).astype(np.uint8)
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = xs[None, :]
    arr[:, :, 1] = (seed * 37) % 256
    arr[:, :, 2] = (seed * 91) % 256
    # A vertical edge so the Laplacian variance is non-zero.
    arr[height // 2 :, :, 1] = (seed * 37 + 128) % 256
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def make_blank_image(width: int = 64, height: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def synthetic_embedding(data: bytes, dim: int = EMBEDDING_DIM) -> tuple[float, ...]:
    """Deterministic near-orthogonal unit embedding: a one-hot basis vector.

    Same bytes -> identical embedding (similarity 1.0); different bytes ->
    (almost surely) orthogonal embeddings (similarity ~0.0).  This makes the
    1:1 semantics discriminative without any real model.
    """
    digest = hashlib.sha256(data).digest()
    index = int.from_bytes(digest[:4], "big") % dim
    vec = np.zeros(dim, dtype=np.float64)
    vec[index] = 1.0
    return tuple(float(v) for v in vec)


def default_detect_fn(image_bytes: bytes) -> list[FaceDetection]:
    """One face, unless the synthetic image is uniform (blank -> no face)."""
    arr = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    if int(arr.max()) == int(arr.min()):
        return []
    h, w = arr.shape[:2]
    return [
        FaceDetection(
            bbox=(0.0, 0.0, float(w), float(h)),
            det_score=0.99,
            embedding=synthetic_embedding(image_bytes),
        )
    ]


def make_fake_model(**kwargs) -> FakeModel:
    kwargs.setdefault("detect_fn", default_detect_fn)
    return FakeModel(**kwargs)


# --------------------------------------------------------------------------
# settings / app / client
# --------------------------------------------------------------------------
@pytest.fixture
def settings(tmp_path):
    from face_service.config import Settings

    return Settings(
        # Local-dev / isolated test client: loopback bind with auth explicitly
        # off.  Production defaults are fail-closed (auth_required=True and a
        # non-loopback host would refuse to start without a token).
        host="127.0.0.1",
        port=18099,
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "openvela_faces.sqlite3",
        verify_threshold=0.40,
        max_body_bytes=1024 * 1024,
        inference_timeout_seconds=5.0,
        max_concurrency=4,
        auth_required=False,
    )


@pytest.fixture
def make_client(settings):
    created: list[TestClient] = []

    def _make(*, model=None, settings_override=None, auth=None):
        s = settings_override or settings
        m = model if model is not None else make_fake_model()
        a = auth if auth is not None else TokenAuth(None)
        app = create_app(settings=s, model=m, store=FaceStore(s.db_path), auth=a)
        client = TestClient(app)
        created.append(client)
        return client

    return _make


@pytest.fixture
def client(make_client):
    return make_client()


# --------------------------------------------------------------------------
# request helpers
# --------------------------------------------------------------------------
@pytest.fixture
def register():
    def _register(client: TestClient, namespace: str, subject_id: str, image: bytes,
                  on_exists: str | None = None):
        data = {"subject_id": subject_id}
        if on_exists is not None:
            data["on_exists"] = on_exists
        return client.post(
            f"/v1/namespaces/{namespace}/subjects",
            files={"image": ("face.png", image, "image/png")},
            data=data,
        )

    return _register


@pytest.fixture
def extract():
    def _extract(client: TestClient, image: bytes, namespace: str | None = None):
        data = {}
        if namespace is not None:
            data["namespace"] = namespace
        return client.post(
            "/v1/extract",
            files={"image": ("face.png", image, "image/png")},
            data=data,
        )

    return _extract


@pytest.fixture
def verify():
    def _verify(client: TestClient, namespace: str, subject_id: str, image: bytes,
                threshold: float | None = None):
        data = {"namespace": namespace, "subject_id": subject_id}
        if threshold is not None:
            data["threshold"] = str(threshold)
        return client.post(
            "/v1/verify",
            files={"image": ("face.png", image, "image/png")},
            data=data,
        )

    return _verify


@pytest.fixture
def search():
    def _search(client: TestClient, namespace: str, image: bytes,
                top_k: int | str | None = None, **extra):
        data = {key: value for key, value in extra.items()}
        if top_k is not None:
            data["top_k"] = str(top_k)
        return client.post(
            f"/v1/namespaces/{namespace}/search",
            files={"image": ("face.png", image, "image/png")},
            data=data,
        )

    return _search
