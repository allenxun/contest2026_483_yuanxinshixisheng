"""1:N search: namespace-scoped, read-only, conservative three-state decision.

All inputs are synthetic; no real photos, no network, no CV stack.
"""

from __future__ import annotations

import base64
import math

import numpy as np

from conftest import EMBEDDING_DIM, make_blank_image, make_image, synthetic_embedding

from face_service.model import FaceDetection, FakeModel
from face_service.store import FaceStore

NS = "ns-search"


# --------------------------------------------------------------------------
# helpers: controlled embeddings so similarities are exact and testable
# --------------------------------------------------------------------------
def _vec(**components: float) -> tuple[float, ...]:
    arr = np.zeros(EMBEDDING_DIM, dtype=np.float64)
    for idx, value in components.items():
        arr[int(idx)] = float(value)
    return tuple((arr / np.linalg.norm(arr)).tolist())


def _detect_fn(mapping: dict[bytes, tuple[float, ...]]):
    def _fn(image_bytes: bytes) -> list[FaceDetection]:
        return [
            FaceDetection(
                bbox=(0.0, 0.0, 64.0, 64.0),
                det_score=0.99,
                embedding=mapping[image_bytes],
            )
        ]

    return _fn


def _ambiguous_embeddings() -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Return ``(alice, bob, probe)`` with sim(probe,alice)=0.70, sim(probe,bob)=0.69."""
    alice = _vec(**{"0": 1.0})
    probe = _vec(**{"0": 0.70, "1": math.sqrt(1.0 - 0.70**2)})
    c = 0.69 / 0.70
    bob = _vec(**{"0": c, "2": math.sqrt(1.0 - c**2)})
    assert abs(sum(a * b for a, b in zip(probe, alice)) - 0.70) < 1e-9
    assert abs(sum(a * b for a, b in zip(probe, bob)) - 0.69) < 1e-9
    return alice, bob, probe


def _ambiguous_setup(make_client):
    """Register ``alice`` (sim 0.70) and ``bob`` (sim 0.69) for one probe.

    With the default match threshold 0.60 and margin 0.05 the top two are too
    close, so the decision must be ``uncertain``/``ambiguous``.
    """
    alice_img = make_image(seed=210)
    bob_img = make_image(seed=211)
    probe_img = make_image(seed=212)
    alice_emb, bob_emb, probe_emb = _ambiguous_embeddings()

    client = make_client(model=FakeModel(detect_fn=_detect_fn(
        {alice_img: alice_emb, bob_img: bob_emb, probe_img: probe_emb}
    )))
    for subject_id, image in (("alice", alice_img), ("bob", bob_img)):
        resp = client.post(
            "/v1/namespaces/ns-amb/subjects",
            files={"image": ("f.png", image, "image/png")},
            data={"subject_id": subject_id},
        )
        assert resp.status_code == 201, resp.text
    return client, probe_img


# --------------------------------------------------------------------------
# 1. namespace isolation
# --------------------------------------------------------------------------
def test_search_namespace_isolation(client, register, search):
    alice_img = make_image(seed=200)
    bob_img = make_image(seed=201)
    assert register(client, "ns-iso-a", "shared-id", alice_img).status_code == 201
    assert register(client, "ns-iso-b", "shared-id", bob_img).status_code == 201

    # ns-a contains only Alice's embedding: Bob's image must NOT hit.  The
    # namespace is non-empty, so a clearly-below-threshold probe is reported as
    # "reliable_new" (contract search-v2 vocabulary) — the isolation guarantee is
    # the absence of subject_id/similarity, asserted below and unchanged.
    other = search(client, "ns-iso-a", bob_img)
    assert other.status_code == 200
    assert other.json()["decision"] == "reliable_new"
    assert "subject_id" not in other.json()
    assert "similarity" not in other.json()

    # Each namespace resolves its own subject.
    own_b = search(client, "ns-iso-b", bob_img).json()
    assert own_b["decision"] == "matched"
    assert own_b["subject_id"] == "shared-id"
    own_a = search(client, "ns-iso-a", alice_img).json()
    assert own_a["decision"] == "matched"
    assert own_a["subject_id"] == "shared-id"


def test_search_unknown_namespace_not_found_and_not_created(client, search, settings):
    before = FaceStore(settings.db_path).revision()
    resp = search(client, "ghost-search-ns", make_image(seed=202))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NAMESPACE_NOT_FOUND"
    # The read must not have created the namespace.
    info = client.get("/v1/namespaces/ghost-search-ns/info")
    assert info.status_code == 404
    assert info.json()["error"]["code"] == "NAMESPACE_NOT_FOUND"
    assert FaceStore(settings.db_path).revision() == before


# --------------------------------------------------------------------------
# 2. same-person hit
# --------------------------------------------------------------------------
def test_search_same_person_matched(client, register, search):
    image = make_image(seed=203)
    assert register(client, NS, "alice", image).status_code == 201
    resp = search(client, NS, image)
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "matched"
    assert body["ambiguous"] is False
    assert body["subject_id"] == "alice"
    assert body["similarity"] > 0.99
    assert body["subject_count"] == 1
    assert body["top_k"] == 5
    assert body["policy_version"] == "search-v2"
    assert body["model_version"] == "fake-model@0"
    assert body["reasons"] == []
    assert body["library_revision"] >= 1
    assert "request_id" in body


# --------------------------------------------------------------------------
# 3. different sample: reliable_new, and the subject key must be ABSENT
# --------------------------------------------------------------------------
def test_search_different_sample_reliable_new_without_subject_key(client, register, search):
    assert register(client, NS, "alice", make_image(seed=204)).status_code == 201
    resp = search(client, NS, make_image(seed=205))
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "reliable_new"
    assert body["ambiguous"] is False
    assert "subject_id" not in body
    assert "similarity" not in body
    # Candidate minimum disclosure: no list, no embedding anywhere.
    assert "candidates" not in body
    assert "embedding" not in resp.text


# --------------------------------------------------------------------------
# 4. top-k
# --------------------------------------------------------------------------
def test_search_top_k_default_boundaries_and_non_integer(client, register, search):
    assert register(client, NS, "alice", make_image(seed=206)).status_code == 201
    image = make_image(seed=206)

    assert search(client, NS, image).json()["top_k"] == 5  # config default
    # Lower bound is 2 (not 1): see the margin-window rationale.
    assert search(client, NS, image, top_k=2).json()["top_k"] == 2
    assert search(client, NS, image, top_k=10).json()["top_k"] == 10

    for bad in (0, 1, 11, -1, "abc", 1.5, True):
        resp = search(client, NS, image, top_k=bad)
        assert resp.status_code == 400, bad
        assert resp.json()["error"]["code"] == "INVALID_REQUEST", bad


def test_search_json_body_reuses_decode_path(client, register):
    """JSON body + top_k: the same decode path as extract/verify is reused."""
    image = make_image(seed=270)
    assert register(client, NS, "alice", image).status_code == 201
    resp = client.post(
        f"/v1/namespaces/{NS}/search",
        json={
            "image_base64": base64.b64encode(image).decode("ascii"),
            "top_k": 3,
            "media_type": "image/jpeg",  # accepted; actual decode is authoritative
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["top_k"] == 3
    assert body["decision"] == "matched"
    assert body["subject_id"] == "alice"


def test_search_top_k_changes_margin_participation(make_client):
    """``top_k`` bounds the *margin window*; the minimum legal value is 2.

    Previously ``top_k=1`` silently disabled the margin rule (no runner-up ->
    vacuous margin -> ``matched`` on a near-tied library).  That value is now
    rejected at the boundary, and every legal window (2/5/10) still contains the
    runner-up, so the ambiguity decision is stable across all legal ``top_k``.
    """
    client, probe_img = _ambiguous_setup(make_client)

    # The value that used to bypass ambiguity protection is no longer accepted.
    rejected = client.post(
        "/v1/namespaces/ns-amb/search",
        files={"image": ("f.png", probe_img, "image/png")},
        data={"top_k": "1"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "INVALID_REQUEST"

    for tk in ("2", "5", "10"):
        body = client.post(
            "/v1/namespaces/ns-amb/search",
            files={"image": ("f.png", probe_img, "image/png")},
            data={"top_k": tk},
        ).json()
        assert body["top_k"] == int(tk)
        assert body["decision"] == "uncertain", tk
        assert body["ambiguous"] is True, tk


def test_search_minimum_legal_top_k_keeps_ambiguity_protection(make_client):
    """Discriminative: with the minimum legal ``top_k=2`` ambiguity still fires.

    Two near-tied subjects (similarity 0.70 vs 0.69, gap 0.01 < margin 0.05)
    must stay ``uncertain``/``ambiguous`` and must not disclose a ``subject_id``.
    If the lower bound were 1, this minimum window would collapse to a single
    candidate and the same probe would report ``matched``.
    """
    client, probe_img = _ambiguous_setup(make_client)
    resp = client.post(
        "/v1/namespaces/ns-amb/search",
        files={"image": ("f.png", probe_img, "image/png")},
        data={"top_k": "2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "uncertain"
    assert body["ambiguous"] is True
    assert body["subject_count"] == 2
    assert "ambiguous_top_candidates" in body["reasons"]
    # A non-matched decision discloses neither the winner nor any score.
    assert "subject_id" not in body
    assert "similarity" not in body


# --------------------------------------------------------------------------
# 5. threshold / margin (server-fixed)
# --------------------------------------------------------------------------
def test_search_ambiguous_two_close_subjects(make_client):
    client, probe_img = _ambiguous_setup(make_client)
    resp = client.post(
        "/v1/namespaces/ns-amb/search",
        files={"image": ("f.png", probe_img, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "uncertain"
    assert body["ambiguous"] is True
    assert body["subject_count"] == 2
    assert "subject_id" not in body
    assert "similarity" not in body
    assert "ambiguous_top_candidates" in body["reasons"]


def test_search_margin_zero_flips_ambiguous_to_matched(make_client, settings):
    """Discriminative: the margin rule, not the threshold, decides this case.

    Same near-tied library; with ``search_margin=0`` the 0.01 gap is accepted
    and the decision becomes ``matched``.
    """
    from dataclasses import replace

    alice_img = make_image(seed=210)
    bob_img = make_image(seed=211)
    probe_img = make_image(seed=212)
    alice_emb, bob_emb, probe_emb = _ambiguous_embeddings()
    model = FakeModel(
        detect_fn=_detect_fn(
            {alice_img: alice_emb, bob_img: bob_emb, probe_img: probe_emb}
        )
    )
    zero_margin = replace(settings, search_margin=0.0)
    client = make_client(model=model, settings_override=zero_margin)
    for subject_id, image in (("alice", alice_img), ("bob", bob_img)):
        assert (
            client.post(
                "/v1/namespaces/ns-amb/subjects",
                files={"image": ("f.png", image, "image/png")},
                data={"subject_id": subject_id},
            ).status_code
            == 201
        )

    body = client.post(
        "/v1/namespaces/ns-amb/search",
        files={"image": ("f.png", probe_img, "image/png")},
    ).json()
    assert body["decision"] == "matched"
    assert body["subject_id"] == "alice"
    assert 0.69 < body["similarity"] < 0.71
    # The margin threshold itself is never disclosed (only policy_version).
    assert "search_margin" not in body
    assert "threshold" not in body


def test_search_client_threshold_fields_are_ignored(make_client):
    """No client-supplied threshold may influence the server-fixed decision.

    If any of these were parsed, ``threshold=0.99`` would turn the 0.70 match
    into ``reliable_new``; the decision must stay ``uncertain`` (ambiguous).
    """
    client, probe_img = _ambiguous_setup(make_client)
    body = client.post(
        "/v1/namespaces/ns-amb/search",
        files={"image": ("f.png", probe_img, "image/png")},
        data={"threshold": "0.99", "match_threshold": "0.99", "margin": "0.99"},
    ).json()
    assert body["decision"] == "uncertain"
    assert body["ambiguous"] is True


def test_search_below_match_threshold_is_reliable_new(client, register, search):
    # Orthogonal synthetic embeddings give similarity ~0.0 -> reliable_new (clearly
    # below the band in a NON-EMPTY namespace), not a "close" uncertain.
    assert register(client, NS, "alice", make_image(seed=207)).status_code == 201
    body = search(client, NS, make_image(seed=208)).json()
    assert body["decision"] == "reliable_new"
    assert "no_candidates_above_threshold" in body["reasons"]
    assert body["subject_count"] == 1
    assert "subject_id" not in body


# --------------------------------------------------------------------------
# 6. quality: insufficient quality can only cap the decision at uncertain
# --------------------------------------------------------------------------
def test_search_low_quality_caps_matched_to_uncertain(make_client, register):
    image = make_image(seed=220)
    good = make_client()
    assert register(good, "ns-qsearch", "alice", image).status_code == 201

    # Same embedding (similarity 1.0) but a 1x1 bbox -> min_acceptable False.
    tiny = FaceDetection(
        bbox=(0.0, 0.0, 1.0, 1.0), det_score=0.99,
        embedding=synthetic_embedding(image),
    )
    bad = make_client(model=FakeModel(detections=[tiny]))
    body = bad.post(
        "/v1/namespaces/ns-qsearch/search",
        files={"image": ("f.png", image, "image/png")},
    ).json()
    assert body["decision"] == "uncertain"  # NOT matched despite sim 1.0
    assert body["quality"]["min_acceptable"] is False
    assert "quality_below_minimum" in body["reasons"]
    assert "subject_id" not in body


# --------------------------------------------------------------------------
# 7. precondition errors win over any decision
# --------------------------------------------------------------------------
def test_search_blank_image_is_no_face_not_reliable_new(client, register, search):
    assert register(client, NS, "alice", make_image(seed=230)).status_code == 201
    resp = search(client, NS, make_blank_image())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_FACE"


def test_search_multi_face_ambiguous(client, register, make_client):
    image = make_image(seed=231)
    assert register(client, "ns-multi", "alice", image).status_code == 201

    img = make_image(seed=232)
    detections = [
        FaceDetection(bbox=(0.0, 0.0, 10.0, 10.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"a")),
        FaceDetection(bbox=(0.0, 0.0, 20.0, 20.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"b")),
    ]
    client2 = make_client(model=FakeModel(detections=detections))
    resp = client2.post(
        "/v1/namespaces/ns-multi/search",
        files={"image": ("f.png", img, "image/png")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MULTI_FACES_AMBIGUOUS"


def test_search_bad_image_decode_failed(client, register, search):
    assert register(client, NS, "alice", make_image(seed=233)).status_code == 201
    resp = search(client, NS, b"definitely-not-an-image")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


# --------------------------------------------------------------------------
# 8. zero writes
# --------------------------------------------------------------------------
def test_search_is_zero_write(client, register, search, settings):
    image = make_image(seed=240)
    assert register(client, "ns-zw", "alice", image).status_code == 201
    before = FaceStore(settings.db_path).revision()
    count_before = client.get("/v1/namespaces/ns-zw/info").json()["subject_count"]

    first = search(client, "ns-zw", image)
    second = search(client, "ns-zw", image)
    assert first.status_code == second.status_code == 200
    assert first.json()["library_revision"] == before
    assert first.json()["subject_count"] == count_before

    assert FaceStore(settings.db_path).revision() == before
    assert client.get("/v1/namespaces/ns-zw/info").json()["subject_count"] == count_before


# --------------------------------------------------------------------------
# 9. delete removes the hit and advances the revision
# --------------------------------------------------------------------------
def test_search_after_delete_no_longer_matches(client, register, search, settings):
    image = make_image(seed=250)
    assert register(client, "ns-del", "alice", image).status_code == 201
    assert search(client, "ns-del", image).json()["decision"] == "matched"

    rev_before_delete = FaceStore(settings.db_path).revision()
    assert client.delete("/v1/namespaces/ns-del/subjects/alice").status_code == 200
    rev_after_delete = FaceStore(settings.db_path).revision()
    assert rev_after_delete == rev_before_delete + 1

    # Deleting the only subject leaves the namespace EMPTY.  An empty library is
    # deliberately NOT reported as reliable_new: it more likely means the library
    # was never populated (or was cleared), and answering "new person" would
    # mass-enroll everybody.  Contract §4.2 => uncertain + empty_library.
    body = search(client, "ns-del", image).json()
    assert body["decision"] == "uncertain"
    assert body["ambiguous"] is False
    assert body["subject_count"] == 0
    assert body["library_revision"] == rev_after_delete
    assert body["reasons"] == ["empty_library"]
    assert "subject_id" not in body
    assert "similarity" not in body


# --------------------------------------------------------------------------
# 10. auth
# --------------------------------------------------------------------------
def test_search_requires_token(make_client):
    from conftest import make_image as _img

    from face_service.auth import TokenAuth

    token = "search-token-do-not-log-0123456789abcdef"
    client = make_client(auth=TokenAuth(token, "X-Internal-Token"))
    # /v1/health, /live and /ready stay public.
    assert client.get("/v1/health").status_code == 200
    assert client.get("/live").status_code == 200
    assert client.get("/ready").status_code == 200

    unauth = client.post(
        "/v1/namespaces/ns/search",
        files={"image": ("f.png", _img(seed=260), "image/png")},
    )
    assert unauth.status_code == 401
    assert unauth.json()["error"]["code"] == "UNAUTHORIZED"
    assert token not in unauth.text

    wrong = client.post(
        "/v1/namespaces/ns/search",
        files={"image": ("f.png", _img(seed=260), "image/png")},
        headers={"X-Internal-Token": "wrong"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "UNAUTHORIZED"
    assert token not in wrong.text