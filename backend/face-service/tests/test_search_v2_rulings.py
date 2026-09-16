"""The two conservative rulings introduced with ``search-v2`` (contract §4.2).

These are separate from :mod:`test_search` because each locks a *ruling* rather
than a mechanism, and both are deliberately fail-closed:

1. **An empty library is ``uncertain``, not ``reliable_new``.**  An empty
   namespace more likely means "never populated" (or "cleared by mistake") than
   "this person is new"; answering ``reliable_new`` would mass-enroll everybody.
2. **Poor quality caps the decision at ``uncertain``** — it may never yield
   ``matched`` *and* may never be promoted to ``reliable_new`` either.

Both tests are discriminative: each asserts a value that a plausible but wrong
implementation would get wrong, and each is paired with a positive control in the
same namespace proving the setup can produce the other decision.
"""

from __future__ import annotations

from dataclasses import replace

from conftest import make_image
from face_service.model import FaceDetection, FakeModel, cosine_similarity
from face_service.store import FaceStore


def _register(client, namespace: str, subject_id: str, image: bytes):
    return client.post(
        f"/v1/namespaces/{namespace}/subjects",
        files={"image": ("f.png", image, "image/png")},
        data={"subject_id": subject_id},
    )


def _search(client, namespace: str, image: bytes, **data):
    return client.post(
        f"/v1/namespaces/{namespace}/search",
        files={"image": ("f.png", image, "image/png")},
        data={k: str(v) for k, v in data.items()},
    )


# --------------------------------------------------------------------------
# 1. empty library -> uncertain (never reliable_new)
# --------------------------------------------------------------------------
def test_empty_namespace_is_uncertain_not_reliable_new(client, register, settings):
    ns = "ns-empty-ruling"
    image = make_image(seed=600)
    # Create the namespace, then remove its only subject so it exists but is empty.
    assert register(client, ns, "tmp", image).status_code == 201
    assert client.delete(f"/v1/namespaces/{ns}/subjects/tmp").status_code == 200
    assert FaceStore(settings.db_path).namespace_exists(ns) is True
    assert FaceStore(settings.db_path).count_subjects(ns) == 0

    body = _search(client, ns, image).json()
    assert body["decision"] == "uncertain"
    assert body["decision"] != "reliable_new"
    assert body["reasons"] == ["empty_library"]
    assert body["subject_count"] == 0
    assert body["ambiguous"] is False
    assert body["policy_version"] == "search-v2"
    # No identity may be disclosed for a non-match.
    assert "subject_id" not in body
    assert "similarity" not in body


def test_non_empty_namespace_with_the_same_probe_yields_reliable_new(client, register):
    """Positive control: the ruling is about *emptiness*, not about the probe.

    Same image, same endpoint — the only difference is that the namespace holds a
    non-matching subject.  If the implementation returned ``uncertain`` for every
    miss, this test would fail, so the empty-library ruling is not a blanket
    downgrade that hides real misses.
    """
    ns = "ns-nonempty-ruling"
    assert register(client, ns, "alice", make_image(seed=601)).status_code == 201
    body = _search(client, ns, make_image(seed=602)).json()
    assert body["decision"] == "reliable_new"
    assert body["reasons"] == ["no_candidates_above_threshold"]
    assert body["subject_count"] == 1
    assert "subject_id" not in body
    assert "similarity" not in body


def test_empty_library_ruling_survives_a_top_k_override(client, register):
    ns = "ns-empty-topk"
    image = make_image(seed=603)
    assert register(client, ns, "tmp", image).status_code == 201
    assert client.delete(f"/v1/namespaces/{ns}/subjects/tmp").status_code == 200
    for top_k in (2, 5, 10):
        body = _search(client, ns, image, top_k=top_k).json()
        assert body["decision"] == "uncertain", top_k
        assert body["reasons"] == ["empty_library"], top_k
        assert body["top_k"] == top_k


# --------------------------------------------------------------------------
# 2. poor quality caps at uncertain (never matched, never reliable_new)
# --------------------------------------------------------------------------
def test_low_quality_caps_reliable_new_to_uncertain(make_client, settings):
    """A below-floor probe may not be promoted to ``reliable_new``.

    Discriminative by construction: the library holds one subject whose embedding
    is **orthogonal** to the probe (similarity ~0.0), so without the quality gate
    the decision would be ``reliable_new``.  With the gate it must be
    ``uncertain`` + ``quality_below_minimum``.
    """
    from conftest import synthetic_embedding

    probe = make_image(seed=610)
    stored = make_image(seed=611)
    probe_emb = synthetic_embedding(probe)
    stored_emb = synthetic_embedding(stored)
    assert cosine_similarity(probe_emb, stored_emb) < 0.01  # premise: clearly below

    model = FakeModel(detect_fn=lambda data: [
        FaceDetection(
            bbox=(0.0, 0.0, 64.0, 64.0),
            det_score=0.99,
            embedding=synthetic_embedding(data),
        )
    ])
    client = make_client(model=model)
    assert _register(client, "ns-quality", "alice", stored).status_code == 201

    # Positive control first: with the default floor the probe is reliable_new.
    ok = _search(client, "ns-quality", probe).json()
    assert ok["decision"] == "reliable_new"
    assert ok["quality"]["min_acceptable"] is True

    # Now raise the det-score floor above the model's 0.99 so quality fails.
    strict = make_client(
        model=model,
        settings_override=replace(settings, quality_min_det_score=0.9999),
    )
    assert _register(strict, "ns-quality2", "alice", stored).status_code == 201
    body = _search(strict, "ns-quality2", probe).json()
    assert body["quality"]["min_acceptable"] is False
    assert body["decision"] == "uncertain"
    assert body["decision"] != "reliable_new"
    assert "quality_below_minimum" in body["reasons"]
    assert "no_candidates_above_threshold" in body["reasons"]
    assert "subject_id" not in body


def test_low_quality_still_caps_matched_to_uncertain(make_client, settings):
    """The pre-existing rule is unchanged: quality failure also blocks matched."""
    from conftest import synthetic_embedding

    image = make_image(seed=612)
    model = FakeModel(detect_fn=lambda data: [
        FaceDetection(
            bbox=(0.0, 0.0, 64.0, 64.0),
            det_score=0.99,
            embedding=synthetic_embedding(data),
        )
    ])
    strict = make_client(
        model=model,
        settings_override=replace(settings, quality_min_det_score=0.9999),
    )
    assert _register(strict, "ns-quality3", "alice", image).status_code == 201
    body = _search(strict, "ns-quality3", image).json()
    # Same image => similarity 1.0, so only the quality gate can prevent matched.
    assert body["decision"] == "uncertain"
    assert "quality_below_minimum" in body["reasons"]
    assert "subject_id" not in body


# --------------------------------------------------------------------------
# 3. the vocabulary itself is exactly the contracted three values
# --------------------------------------------------------------------------
def test_decision_vocabulary_is_exactly_the_contracted_three(client, register, settings):
    """No fourth value may appear: the Worker treats unknown ones as a failure.

    ``assessment_analyze.py:415-420`` maps any classification outside
    ``matched|uncertain|ambiguous|reliable_new`` to ``DEPENDENCY_UNAVAILABLE``, so
    a stray ``no_match`` would silently turn every search into a dependency error.
    """
    allowed = {"matched", "uncertain", "reliable_new"}
    ns = "ns-vocab"
    image = make_image(seed=620)
    assert register(client, ns, "alice", image).status_code == 201
    seen = {
        _search(client, ns, image).json()["decision"],                 # matched
        _search(client, ns, make_image(seed=621)).json()["decision"],  # reliable_new
    }
    assert client.delete(f"/v1/namespaces/{ns}/subjects/alice").status_code == 200
    seen.add(_search(client, ns, image).json()["decision"])            # uncertain (empty)
    assert seen == allowed, seen
    assert "no_match" not in seen


def test_matched_is_the_only_decision_that_discloses_identity(client, register):
    ns = "ns-disclosure"
    image = make_image(seed=622)
    assert register(client, ns, "alice", image).status_code == 201
    matched = _search(client, ns, image).json()
    assert matched["decision"] == "matched"
    assert matched["subject_id"] == "alice"
    assert isinstance(matched["similarity"], float)
    for other in (make_image(seed=623), make_image(seed=624)):
        body = _search(client, ns, other).json()
        assert body["decision"] != "matched"
        assert "subject_id" not in body
        assert "similarity" not in body
        # No candidate list, no embedding, no numeric thresholds.
        assert "candidates" not in body
        assert "embedding" not in body
        assert "search_margin" not in body
        assert "search_match_threshold" not in body
        assert "search_uncertain_band" not in body
