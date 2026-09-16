# -*- coding: utf-8 -*-
"""D 包 insightface **phase 2 绑定矩阵**：逐操作请求形状 + 响应校验 + 错误映射 + 守卫。

权威：``backend/handoffs/B-face-service-worker-contract.md``（最终代码 SHA ``bec9eb97``）。

覆盖：
1. 冻结 18 码表与合同 §7 字面清单双向一致；
2. ``request_headers``（鉴权 + 每调用 ``X-Request-Id``）；
3. ``quality`` 三视角聚合矩阵 + 失败分类；
4. ``same_person`` front 锚定两两比较矩阵 + 失败分类；
5. ``search_1n`` 三值词表 / 冻结键 / 结构非法 / 错误映射矩阵；
6. ``register_person`` 自动登记门（零网络）+ 幂等矩阵；
7. ``query_registration`` 矩阵（含 404→not_found 的合同依据）；
8. 活体与出站纪律守卫（无 require_liveness / 无阈值 / 无 on_exists）；
9. 日志/异常脱敏扫描（token / 图片字节 / 标识取值）；
10. 真实 stdlib 传输（``StdlibHttpTransport``）对本地**合同忠实 stub 服务**的端到端。

**关于 live face-service**：本文件 §10 的 stub 是**本测试自建的合同忠实替身**，不是 B 的
face-service（后者无法仅凭 env 激活 ``FakeModel``，且本 venv 无 fastapi/PIL；详见报告）。
"""
from __future__ import annotations

import base64
import http.server
import json
import logging
import os
import threading
from typing import Any, Optional
from urllib.parse import parse_qs

import pytest

from mvp_worker.handlers.dshared import dliveness
from mvp_worker.handlers.dshared.dconfig import (
    FACE_SERVICE_AUTO_ENROLL_ENV,
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    DConfig,
    ProviderConfigError,
)
from mvp_worker.handlers.dshared.dtransport import (
    FACE_ERROR_SPECS,
    FaceServiceConnectionError,
    FaceServiceHttpError,
    FaceServiceProtocolError,
    FaceServiceTimeout,
    FakeTransport,
    StdlibHttpTransport,
    TransportResult,
    parse_json_bytes,
    request_headers,
)
from mvp_worker.handlers.dshared.providers import (
    FaceDouble,
    InsightFaceAdapter,
    ProviderNotActivated,
    ProviderUnavailable,
    build_face_port,
)

TOKEN = "TEST-TOKEN-PLACEHOLDER"
NS = "mvp-ns-1"
FRONT, LEFT, RIGHT = b"front-image", b"left-image", b"right-image"
IMAGES = {"front": FRONT, "left": LEFT, "right": RIGHT}

#: 合同 §7 的 18 码字面清单（**测试自有字面**，不 import B 的 errors.py）。
CONTRACT_SECTION_7: tuple[tuple[str, int, bool], ...] = (
    ("NO_FACE", 400, False),
    ("MULTI_FACES_AMBIGUOUS", 400, False),
    ("IMAGE_DECODE_FAILED", 400, False),
    ("INVALID_REQUEST", 400, False),
    ("UNAUTHORIZED", 401, False),
    ("SUBJECT_NOT_FOUND", 404, False),
    ("NAMESPACE_NOT_FOUND", 404, False),
    ("SUBJECT_ALREADY_EXISTS", 409, False),
    ("IMAGE_TOO_LARGE", 413, False),
    ("UNSUPPORTED_MEDIA_TYPE", 415, False),
    ("QUALITY_INSUFFICIENT", 422, False),
    ("LIVENESS_UNSUPPORTED", 501, False),
    ("INTERNAL_ERROR", 500, True),
    ("MODEL_UNAVAILABLE", 503, True),
    ("MODEL_NOT_LOADED", 503, True),
    ("STORE_UNAVAILABLE", 503, True),
    ("CONCURRENCY_LIMIT", 429, True),
    ("INFERENCE_TIMEOUT", 504, True),
)

_SEARCH_CONFIG_CODES = ("INVALID_REQUEST", "IMAGE_DECODE_FAILED", "UNSUPPORTED_MEDIA_TYPE", "IMAGE_TOO_LARGE")
_SEARCH_UNAVAILABLE_CODES = (
    "NO_FACE",
    "MULTI_FACES_AMBIGUOUS",
    "QUALITY_INSUFFICIENT",
    "LIVENESS_UNSUPPORTED",
    "INTERNAL_ERROR",
    "MODEL_UNAVAILABLE",
    "MODEL_NOT_LOADED",
    "STORE_UNAVAILABLE",
    "CONCURRENCY_LIMIT",
    "INFERENCE_TIMEOUT",
)
_REGISTER_UNKNOWN_CODES = ("MODEL_UNAVAILABLE", "MODEL_NOT_LOADED", "STORE_UNAVAILABLE", "CONCURRENCY_LIMIT", "INFERENCE_TIMEOUT", "INTERNAL_ERROR", "LIVENESS_UNSUPPORTED")
_REGISTER_FAILED_CODES = ("INVALID_REQUEST", "NO_FACE", "MULTI_FACES_AMBIGUOUS", "IMAGE_DECODE_FAILED", "IMAGE_TOO_LARGE", "UNSUPPORTED_MEDIA_TYPE", "QUALITY_INSUFFICIENT")
FORBIDDEN_REQUEST_KEYS = ("require_liveness", "threshold", "on_exists", "top_k")

_ENVS = (
    "MVP_D_FACE_PROVIDER",
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    FACE_SERVICE_AUTO_ENROLL_ENV,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: Any) -> None:
    for name in _ENVS:
        monkeypatch.delenv(name, raising=False)


def _write_token(tmp_path: Any, *, content: str = TOKEN, mode: int = 0o600) -> str:
    path = tmp_path / "token"
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)
    return str(path)


def _cfg(monkeypatch: Any, tmp_path: Any, *, auto_enroll: bool = False) -> DConfig:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, "http://127.0.0.1:1")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, NS)
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, _write_token(tmp_path))
    monkeypatch.setenv(FACE_SERVICE_AUTO_ENROLL_ENV, "true" if auto_enroll else "false")
    return DConfig.from_env()


def _adapter(cfg: DConfig, responses: list[Any]) -> tuple[InsightFaceAdapter, FakeTransport]:
    fake = FakeTransport(responses)
    return InsightFaceAdapter(cfg, fake), fake


# ---------------------------------------------------------------- body builders

_SENTINEL = object()


def quality_body(min_acceptable: bool, *, request_id: str = "req") -> dict[str, Any]:
    return {
        "face_count": 1,
        "faces": [
            {
                "bbox": [0.0, 0.0, 64.0, 64.0],
                "det_score": 0.99,
                "quality": {
                    "det_score": 0.99,
                    "min_acceptable": min_acceptable,
                    "liveness": {"supported": False, "reason": "no liveness model"},
                },
                "largest_face": True,
            }
        ],
        "largest_face_index": 0,
        "namespace": None,
        "model_version": "stub-model@0",
        "library_revision": 1,
        "liveness": {"supported": False, "reason": "no liveness model"},
        "request_id": request_id,
    }


def compare_body(matched: bool) -> dict[str, Any]:
    return {
        "matched": matched,
        "similarity": 0.9 if matched else 0.1,
        "threshold": 0.4,
        "face_count_a": 1,
        "face_count_b": 1,
        "quality_a": {"min_acceptable": True, "liveness": {"supported": False}},
        "quality_b": {"min_acceptable": True, "liveness": {"supported": False}},
        "liveness": {"supported": False},
        "reasons": [],
        "model_version": "stub-model@0",
        "library_revision": 1,
        "request_id": "req",
    }


def search_body(
    decision: str,
    *,
    subject_id: Any = _SENTINEL,
    ambiguous: bool = False,
    reasons: Optional[list[str]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "decision": decision,
        "ambiguous": ambiguous,
        "quality": {"min_acceptable": True, "liveness": {"supported": False}},
        "reasons": reasons if reasons is not None else [],
        "subject_count": 3,
        "top_k": 5,
        "policy_version": "search-v2",
        "model_version": "stub-model@0",
        "library_revision": 4,
        "request_id": "req",
    }
    if subject_id is not _SENTINEL:
        body["subject_id"] = subject_id
        body["similarity"] = 0.73
    return body


def register_body(subject_id: str, *, created: bool = True, replayed: bool = False) -> dict[str, Any]:
    return {
        "subject_id": subject_id,
        "namespace": NS,
        "created": created,
        "created_at": "2026-09-16T00:00:00Z",
        "updated_at": "2026-09-16T00:00:00Z",
        "embedding_dim": 64,
        "model_version": "stub-model@0",
        "quality": {"min_acceptable": True},
        "library_revision": 1,
        "replayed": replayed,
        "registered_at": "2026-09-16T00:00:00Z",
        "request_id": "req",
    }


def query_body(status: str, subject_id: Optional[str] = None) -> dict[str, Any]:
    if status == "registered":
        return {
            "status": "registered",
            "subject_id": subject_id or "subj-1",
            "correlation_id": "corr-1",
            "provider_request_id": "req-1",
            "registered_at": "2026-09-16T00:00:00Z",
            "library_revision": 1,
            "request_id": "req",
        }
    return {"status": status, "request_id": "req"}


def http_error(status: int, code: str, retryable: bool) -> FaceServiceHttpError:
    return FaceServiceHttpError(status=status, code=code, retryable=retryable, request_id="req")


def _call_bodies(fake: FakeTransport) -> list[dict[str, Any]]:
    return [call["json_body"] for call in fake.calls if call["json_body"] is not None]


def _exception_chain_text(exc: BaseException) -> str:
    """异常自身 + 整条 ``__cause__``/``__context__`` 链的文本（脱敏扫描用）。

    单看 ``str(exc)`` 会漏掉被 ``raise ... from exc`` 包装的底层传输异常文本
    （Oracle 指出的 Focus-5 弱点）。
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


# ================================================================ 1) 冻结码表


def test_frozen_error_table_matches_contract_section7() -> None:
    expected = {code: (status, retryable) for code, status, retryable in CONTRACT_SECTION_7}
    assert FACE_ERROR_SPECS == expected
    assert len(CONTRACT_SECTION_7) == 18
    assert len({code for code, _, _ in CONTRACT_SECTION_7}) == 18


def test_contract_table_has_both_retryable_kinds() -> None:
    assert any(r for _, _, r in CONTRACT_SECTION_7)
    assert any(not r for _, _, r in CONTRACT_SECTION_7)


# ================================================================ 2) 出站头


def test_request_headers_carry_token_and_request_id() -> None:
    headers = request_headers(TOKEN)
    assert headers["X-Internal-Token"] == TOKEN
    assert len(headers["X-Request-Id"]) == 32
    assert all(c in "0123456789abcdef" for c in headers["X-Request-Id"])
    assert headers["Accept"] == "application/json"


def test_request_headers_honour_explicit_request_id() -> None:
    headers = request_headers(TOKEN, request_id="abc123")
    assert headers["X-Request-Id"] == "abc123"


def test_stdlib_transport_repr_redacts_token() -> None:
    transport = StdlibHttpTransport(
        base_url="http://127.0.0.1:1",
        token=TOKEN,
        connect_timeout_ms=10,
        read_timeout_ms=20,
    )
    assert transport.has_token() is True
    assert TOKEN not in repr(transport)
    assert "<redacted>" in repr(transport)


# ================================================================ 3) quality


def test_quality_all_acceptable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, quality_body(True)) for _ in range(3)])
    result = adapter.quality(IMAGES)
    assert result.status == "accepted"
    assert result.required_views == ()
    assert [(c["method"], c["path"]) for c in fake.calls] == [("POST", "/v1/quality")] * 3
    for body in _call_bodies(fake):
        assert set(body) == {"image_base64"}
        assert "require_liveness" not in body and "threshold" not in body


@pytest.mark.parametrize("bad_views,expected", [([1], ("left",)), ([0], ("front",)), ([2], ("right",)), ([0, 2], ("front", "right")), ([0, 1, 2], ("front", "left", "right"))])
def test_quality_aggregates_failing_views_in_canonical_order(
    monkeypatch: Any, tmp_path: Any, bad_views: list[int], expected: tuple[str, ...]
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    responses = [
        TransportResult(200, quality_body(i not in bad_views)) for i in range(3)
    ]
    adapter, _ = _adapter(cfg, responses)
    result = adapter.quality(IMAGES)
    assert result.status == "needs_retake"
    assert result.required_views == expected


def test_quality_calls_views_in_canonical_order(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, quality_body(True)) for _ in range(3)])
    adapter.quality({"right": RIGHT, "left": LEFT, "front": FRONT})
    encoded = [c["json_body"]["image_base64"] for c in fake.calls]
    assert encoded == [
        base64.b64encode(FRONT).decode(),
        base64.b64encode(LEFT).decode(),
        base64.b64encode(RIGHT).decode(),
    ]


@pytest.mark.parametrize("view", ["front", "left", "right"])
def test_quality_missing_view_is_unavailable(monkeypatch: Any, tmp_path: Any, view: str) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [])
    images = {k: v for k, v in IMAGES.items() if k != view}
    with pytest.raises(ProviderUnavailable):
        adapter.quality(images)
    assert fake.calls == []


@pytest.mark.parametrize(
    "exc",
    [
        FaceServiceTimeout("t"),
        FaceServiceConnectionError("c"),
        FaceServiceProtocolError("p"),
        http_error(500, "INTERNAL_ERROR", True),
        http_error(400, "NO_FACE", False),
        http_error(400, "MULTI_FACES_AMBIGUOUS", False),
        http_error(503, "MODEL_UNAVAILABLE", True),
        http_error(504, "INFERENCE_TIMEOUT", True),
    ],
)
def test_quality_failure_is_unavailable_not_pass(monkeypatch: Any, tmp_path: Any, exc: Exception) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [exc])
    with pytest.raises(ProviderUnavailable):
        adapter.quality(IMAGES)


def test_quality_auth_is_config_error(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(401, "UNAUTHORIZED", False)])
    with pytest.raises(ProviderConfigError) as ei:
        adapter.quality(IMAGES)
    assert FACE_SERVICE_TOKEN_FILE_ENV in str(ei.value)
    assert TOKEN not in str(ei.value)


@pytest.mark.parametrize(
    "body",
    [
        {"faces": []},
        {"faces": [{}]},
        {"faces": [{"quality": {"min_acceptable": "yes"}}]},
        {"faces": "not-a-list"},
        {"faces": [{"quality": {}}]},
    ],
)
def test_quality_invalid_2xx_is_unavailable(monkeypatch: Any, tmp_path: Any, body: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.quality(IMAGES)


@pytest.mark.parametrize(
    "index",
    ["0", True, False, 0.5, -1, 3, 99, None],
)
def test_quality_invalid_largest_face_index_is_unavailable(
    monkeypatch: Any, tmp_path: Any, index: Any
) -> None:
    """Oracle IMPORTANT 3：非法 `largest_face_index` **绝不**静默修复为 0。"""
    cfg = _cfg(monkeypatch, tmp_path)
    body = quality_body(True)
    body["largest_face_index"] = index
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.quality(IMAGES)


def test_quality_missing_largest_face_index_is_unavailable(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = quality_body(True)
    del body["largest_face_index"]
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.quality(IMAGES)


# ================================================================ 4) same_person


def test_same_person_front_anchored_all_matched(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, compare_body(True)), TransportResult(200, compare_body(True))])
    result = adapter.same_person(IMAGES)
    assert result.ok is True
    assert [c["path"] for c in fake.calls] == ["/v1/compare", "/v1/compare"]
    first, second = _call_bodies(fake)
    assert first["image_a_base64"] == base64.b64encode(FRONT).decode()
    assert first["image_b_base64"] == base64.b64encode(LEFT).decode()
    assert second["image_b_base64"] == base64.b64encode(RIGHT).decode()
    for body in (first, second):
        assert set(body) == {"image_a_base64", "image_b_base64"}
        assert "threshold" not in body and "require_liveness" not in body


@pytest.mark.parametrize("matched_pair", [(True, False), (False, True), (False, False)])
def test_same_person_any_false_is_false(monkeypatch: Any, tmp_path: Any, matched_pair: tuple[bool, bool]) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, compare_body(m)) for m in matched_pair])
    assert adapter.same_person(IMAGES).ok is False


def test_same_person_failure_on_second_call_still_raises(monkeypatch: Any, tmp_path: Any) -> None:
    """两次都执行：第一次 matched 但第二次失败 → 抛不可用（不谎报同人）。"""
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, compare_body(True)), FaceServiceTimeout("t")])
    with pytest.raises(ProviderUnavailable):
        adapter.same_person(IMAGES)


def test_same_person_auth_is_config_error(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(403, None, False)])  # type: ignore[arg-type]
    with pytest.raises(ProviderConfigError):
        adapter.same_person(IMAGES)


def test_same_person_invalid_2xx_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, {"matched": "yes"})])
    with pytest.raises(ProviderUnavailable):
        adapter.same_person(IMAGES)


def test_same_person_missing_side_view_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [])
    with pytest.raises(ProviderUnavailable):
        adapter.same_person({"front": FRONT})
    assert fake.calls == []


# ================================================================ 5) search_1n


def test_search_matched_passes_subject_ref(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, search_body("matched", subject_id="subj-9"))])
    result = adapter.search_1n(NS, IMAGES)
    assert result.classification == "matched"
    assert result.face_subject_ref == "subj-9"
    call = fake.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == f"/v1/namespaces/{NS}/search"
    assert set(call["json_body"]) == {"image_base64"}
    assert call["json_body"]["image_base64"] == base64.b64encode(FRONT).decode()


@pytest.mark.parametrize(
    "decision,ambiguous,reasons",
    [
        ("uncertain", True, ["ambiguous_top_candidates"]),
        ("uncertain", False, ["similarity_in_uncertain_band"]),
        ("reliable_new", False, ["empty_library"]),
        ("reliable_new", False, ["no_candidates_above_threshold"]),
    ],
)
def test_search_decision_passthrough_without_subject_ref(
    monkeypatch: Any, tmp_path: Any, decision: str, ambiguous: bool, reasons: list[str]
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, search_body(decision, ambiguous=ambiguous, reasons=reasons))])
    result = adapter.search_1n(NS, IMAGES)
    assert result.classification == decision
    assert result.face_subject_ref is None


def test_search_quotes_namespace(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, search_body("reliable_new"))])
    adapter.search_1n("ns with space", IMAGES)
    assert fake.calls[0]["path"] == "/v1/namespaces/ns%20with%20space/search"


@pytest.mark.parametrize("decision", ["no_match", "matched_new", "", None, 7])
def test_search_invalid_decision_is_unavailable(monkeypatch: Any, tmp_path: Any, decision: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = search_body("matched", subject_id="s")
    body["decision"] = decision
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


def test_search_matched_without_subject_id_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, search_body("matched"))])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


def test_search_matched_with_bad_similarity_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = search_body("matched", subject_id="s")
    body["similarity"] = "high"
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


def test_search_non_matched_with_subject_id_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = search_body("uncertain")
    body["subject_id"] = "leaked"
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


@pytest.mark.parametrize(
    "key",
    ["decision", "ambiguous", "quality", "reasons", "subject_count", "top_k", "policy_version", "model_version", "library_revision", "request_id"],
)
def test_search_missing_frozen_key_is_unavailable(monkeypatch: Any, tmp_path: Any, key: str) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = search_body("reliable_new")
    del body[key]
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


@pytest.mark.parametrize("code", _SEARCH_CONFIG_CODES)
def test_search_config_codes_are_config_error(monkeypatch: Any, tmp_path: Any, code: str) -> None:
    status = dict((c, s) for c, s, _ in CONTRACT_SECTION_7)[code]
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(status, code, False)])
    with pytest.raises(ProviderConfigError) as ei:
        adapter.search_1n(NS, IMAGES)
    assert TOKEN not in str(ei.value)


@pytest.mark.parametrize("code", _SEARCH_UNAVAILABLE_CODES)
def test_search_other_codes_are_unavailable(monkeypatch: Any, tmp_path: Any, code: str) -> None:
    status, retryable = dict((c, (s, r)) for c, s, r in CONTRACT_SECTION_7)[code]
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(status, code, retryable)])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


def test_search_auth_is_config_error(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(401, "UNAUTHORIZED", False)])
    with pytest.raises(ProviderConfigError):
        adapter.search_1n(NS, IMAGES)


@pytest.mark.parametrize("exc", [FaceServiceTimeout("t"), FaceServiceConnectionError("c"), FaceServiceProtocolError("p")])
def test_search_transport_failures_are_unavailable(monkeypatch: Any, tmp_path: Any, exc: Exception) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [exc])
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


# ================================================================ 6) register_person


def test_register_gate_closed_by_default_is_not_activated_zero_network(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)  # auto_enroll default false
    adapter, fake = _adapter(cfg, [])
    with pytest.raises(ProviderNotActivated) as ei:
        adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1")
    assert fake.calls == []  # 零网络
    message = str(ei.value)
    assert "auto-enroll gate closed" in message
    assert "663" in message
    assert TOKEN not in message


def test_register_gate_closed_even_when_env_false(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv(FACE_SERVICE_AUTO_ENROLL_ENV, "false")
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [])
    with pytest.raises(ProviderNotActivated):
        adapter.register_person(NS, "e", IMAGES, "c", "r")
    assert fake.calls == []


def test_register_gate_open_created_success(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, fake = _adapter(cfg, [TransportResult(201, register_body("entity-1"))])
    result = adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1")
    assert result.status == "success"
    call = fake.calls[0]
    assert call["path"] == f"/v1/namespaces/{NS}/subjects"
    body = call["json_body"]
    assert body["subject_id"] == "entity-1"
    assert body["correlation_id"] == "corr-1"
    assert body["provider_request_id"] == "req-1"
    assert body["image_base64"] == base64.b64encode(FRONT).decode()
    assert set(body) == {"image_base64", "subject_id", "correlation_id", "provider_request_id"}
    assert "on_exists" not in body and "require_liveness" not in body


def test_register_replay_200_is_success(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [TransportResult(200, register_body("entity-1", created=False, replayed=True))])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "success"


def test_register_conflict_same_or_different_correlation_is_failed(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    for _ in range(2):  # 相同/不同 correlation 在服务端都是 409 → failed（绝不静默覆盖）
        adapter, _ = _adapter(cfg, [http_error(409, "SUBJECT_ALREADY_EXISTS", False)])
        assert adapter.register_person(NS, "entity-1", IMAGES, "corr-x", "req-1").status == "failed"


def test_register_client_timeout_is_timeout(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [FaceServiceTimeout("t")])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "timeout"


@pytest.mark.parametrize("exc", [FaceServiceConnectionError("c"), FaceServiceProtocolError("p")])
def test_register_transport_uncertainty_is_unknown(monkeypatch: Any, tmp_path: Any, exc: Exception) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [exc])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


@pytest.mark.parametrize("code", _REGISTER_UNKNOWN_CODES)
def test_register_retryable_codes_are_unknown(monkeypatch: Any, tmp_path: Any, code: str) -> None:
    status, retryable = dict((c, (s, r)) for c, s, r in CONTRACT_SECTION_7)[code]
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [http_error(status, code, retryable)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


@pytest.mark.parametrize("code", _REGISTER_FAILED_CODES)
def test_register_other_4xx_is_failed(monkeypatch: Any, tmp_path: Any, code: str) -> None:
    status = dict((c, s) for c, s, _ in CONTRACT_SECTION_7)[code]
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [http_error(status, code, False)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "failed"


def test_register_auth_is_config_error(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [http_error(401, "UNAUTHORIZED", False)])
    with pytest.raises(ProviderConfigError):
        adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1")


def test_register_subject_mismatch_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [TransportResult(201, register_body("some-other-subject"))])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


# --- Oracle BLOCKER 1: malformed / non-whitelisted 2xx must NEVER be success ---


@pytest.mark.parametrize("status", [200, 202, 204, 206, 299])
def test_register_empty_body_2xx_is_unknown(monkeypatch: Any, tmp_path: Any, status: int) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [TransportResult(status, {})])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


@pytest.mark.parametrize("status", [202, 204, 206, 299])
def test_register_non_whitelisted_2xx_with_full_body_is_unknown(
    monkeypatch: Any, tmp_path: Any, status: int
) -> None:
    """只有合同 §6.1 的 200/201 是成功（api.py:742）；其它 2xx 无法证明已创建。"""
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [TransportResult(status, register_body("entity-1"))])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


def test_register_201_null_subject_id_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1")
    body["subject_id"] = None
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


@pytest.mark.parametrize("status", [201, 200])
def test_register_created_status_inconsistency_is_unknown(
    monkeypatch: Any, tmp_path: Any, status: int
) -> None:
    """api.py: `201 if created else 200` ⇒ created 必须与状态一致。"""
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=not (status == 201), replayed=False)
    adapter, _ = _adapter(cfg, [TransportResult(status, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


@pytest.mark.parametrize(
    "key",
    ["subject_id", "namespace", "created", "created_at", "updated_at", "embedding_dim",
     "model_version", "quality", "library_revision", "replayed", "registered_at", "request_id"],
)
def test_register_missing_frozen_key_is_unknown(monkeypatch: Any, tmp_path: Any, key: str) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1")
    del body[key]
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("namespace", ""),
        ("namespace", 7),
        ("created", "true"),
        ("replayed", "false"),
        ("created_at", ""),
        ("updated_at", None),
        ("embedding_dim", True),
        ("embedding_dim", "64"),
        ("model_version", ""),
        ("quality", "not-a-dict"),
        ("library_revision", True),
        ("library_revision", "1"),
        ("request_id", ""),
        ("registered_at", ""),
        ("registered_at", 123),
    ],
)
def test_register_bad_frozen_field_type_is_unknown(
    monkeypatch: Any, tmp_path: Any, key: str, bad_value: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1")
    body[key] = bad_value
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


def test_register_nullable_registered_at_none_is_success(monkeypatch: Any, tmp_path: Any) -> None:
    """`registered_at` 是可空列（api.py 直接外发 record.registered_at）⇒ null 合法。"""
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1")
    body["registered_at"] = None
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "success"


# --- Oracle round-3 IMPORTANT: namespace equality + status/created/replayed triple ---


@pytest.mark.parametrize("status", [201, 200])
def test_register_wrong_namespace_echo_is_unknown(
    monkeypatch: Any, tmp_path: Any, status: int
) -> None:
    """回显 namespace 必须精确等于本次请求的 namespace。"""
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=(status == 201), replayed=(status == 200))
    body["namespace"] = "SOME-OTHER-NAMESPACE"
    adapter, _ = _adapter(cfg, [TransportResult(status, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


def test_register_201_replayed_true_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    """201  created=True ∧ replayed=False（store.py:514-577 新建；replayed 默认 False）。"""
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=True, replayed=True)
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


def test_register_200_replayed_false_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    """Worker 路径唯一可达的 200 是幂等重放（store.py:462-491）⇒ replayed 必须 True。"""
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=False, replayed=False)
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


def test_register_200_created_true_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=True, replayed=True)
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


def test_register_201_created_true_replayed_false_requested_namespace_is_success(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=True, replayed=False)
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "success"


def test_register_200_created_false_replayed_true_requested_namespace_is_success(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    body = register_body("entity-1", created=False, replayed=True)
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "success"


@pytest.mark.parametrize("body", [None, [], "ok", 7])
def test_register_non_mapping_2xx_is_unknown(monkeypatch: Any, tmp_path: Any, body: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    adapter, _ = _adapter(cfg, [TransportResult(201, body)])
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "unknown"


# ================================================================ 7) query_registration


def test_query_registered(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, query_body("registered", "subj-1"))])
    result = adapter.query_registration("corr-1", "req-1", namespace=NS, entity_id="subj-1")
    assert result.status == "registered"
    call = fake.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == f"/v1/namespaces/{NS}/registrations/corr-1?provider_request_id=req-1&entity_id=subj-1"


def test_query_not_found(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, query_body("not_found"))])
    assert adapter.query_registration("corr-1", "req-1", namespace=NS).status == "not_found"


def test_query_404_namespace_is_not_found(monkeypatch: Any, tmp_path: Any) -> None:
    """合同 §6.2：对账针对已发起的登记，404 是确定性“查错地方”否定 → not_found。"""
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(404, "NAMESPACE_NOT_FOUND", False)])
    assert adapter.query_registration("corr-1", "req-1", namespace=NS).status == "not_found"


@pytest.mark.parametrize(
    "exc",
    [
        FaceServiceTimeout("t"),
        FaceServiceConnectionError("c"),
        FaceServiceProtocolError("p"),
        http_error(500, "INTERNAL_ERROR", True),
        http_error(503, "STORE_UNAVAILABLE", True),
    ],
)
def test_query_transport_and_5xx_are_unknown(monkeypatch: Any, tmp_path: Any, exc: Exception) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [exc])
    assert adapter.query_registration("corr-1", "req-1", namespace=NS).status == "unknown"


def test_query_auth_is_config_error(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [http_error(401, "UNAUTHORIZED", False)])
    with pytest.raises(ProviderConfigError):
        adapter.query_registration("corr-1", "req-1", namespace=NS)


@pytest.mark.parametrize(
    "body",
    [
        {"status": "registered"},  # 缺 subject_id
        {"status": "registered", "subject_id": ""},
        {"status": "weird"},
        {"no_status": True},
        "not-an-object",
        None,
    ],
)
def test_query_invalid_2xx_is_unknown(monkeypatch: Any, tmp_path: Any, body: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert adapter.query_registration("corr-1", "req-1", namespace=NS).status == "unknown"


def test_query_requires_namespace(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [])
    with pytest.raises(ProviderConfigError):
        adapter.query_registration("corr-1", "req-1")
    assert fake.calls == []


# --- Oracle BLOCKER 2: confirmation must echo the exact requested identity ---


def _query_call(adapter: InsightFaceAdapter, entity_id: Optional[str] = "entity-1") -> Any:
    return adapter.query_registration(
        "corr-1", "req-1", namespace=NS, entity_id=entity_id
    )


def test_query_wrong_subject_echo_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, query_body("registered", "WRONG-SUBJECT"))])
    assert _query_call(adapter).status == "unknown"


def test_query_wrong_correlation_echo_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = query_body("registered", "entity-1")
    body["correlation_id"] = "some-other-correlation"
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert _query_call(adapter).status == "unknown"


def test_query_wrong_provider_request_echo_is_unknown(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = query_body("registered", "entity-1")
    body["provider_request_id"] = "some-other-request"
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert _query_call(adapter).status == "unknown"


def test_query_null_provider_request_when_supplied_is_unknown(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = query_body("registered", "entity-1")
    body["provider_request_id"] = None
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert _query_call(adapter).status == "unknown"


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("subject_id", 7),
        ("subject_id", ""),
        ("correlation_id", 7),
        ("correlation_id", None),
        ("provider_request_id", 7),
        ("registered_at", 123),
        ("registered_at", ""),
        ("library_revision", True),
        ("library_revision", "1"),
        ("request_id", ""),
        ("request_id", None),
    ],
)
def test_query_bad_frozen_field_is_unknown(
    monkeypatch: Any, tmp_path: Any, key: str, bad_value: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = query_body("registered", "entity-1")
    body[key] = bad_value
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert _query_call(adapter).status == "unknown"


def test_query_nullable_registered_at_none_is_registered(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    body = query_body("registered", "entity-1")
    body["registered_at"] = None
    adapter, _ = _adapter(cfg, [TransportResult(200, body)])
    assert _query_call(adapter).status == "registered"


def test_query_without_entity_id_skips_subject_comparison(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """未提供 entity_id 时不做主体相等比较，但仍要求非空 subject_id。"""
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, query_body("registered", "any-subject"))])
    assert _query_call(adapter, entity_id=None).status == "registered"


def test_query_full_correct_shape_is_registered(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, query_body("registered", "entity-1"))])
    assert _query_call(adapter).status == "registered"


# --- Oracle round-3 BLOCKER: query route is 200-only (api.py:805-852) ---


@pytest.mark.parametrize("status", [201, 202, 204, 206, 299])
def test_query_registered_body_at_non_200_2xx_is_unknown(
    monkeypatch: Any, tmp_path: Any, status: int
) -> None:
    """即使 body 是完整合法的 registered 形状，非 200 的 2xx 也不得当作权威确认。"""
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(status, query_body("registered", "entity-1"))])
    assert _query_call(adapter).status == "unknown"


@pytest.mark.parametrize("status", [201, 202, 204, 299])
def test_query_not_found_body_at_non_200_2xx_is_unknown(
    monkeypatch: Any, tmp_path: Any, status: int
) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(status, query_body("not_found"))])
    assert _query_call(adapter).status == "unknown"


def test_query_not_found_at_200_is_not_found(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [TransportResult(200, query_body("not_found"))])
    assert _query_call(adapter).status == "not_found"


def test_query_optional_params_omitted_when_absent(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, fake = _adapter(cfg, [TransportResult(200, query_body("not_found"))])
    adapter.query_registration("corr-1", "", namespace=NS)
    assert fake.calls[0]["path"] == f"/v1/namespaces/{NS}/registrations/corr-1"


# ================================================================ 8) 活体 + 出站纪律


def test_no_op_ever_sends_require_liveness_or_threshold(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)
    responses = [
        TransportResult(200, quality_body(True)),
        TransportResult(200, quality_body(True)),
        TransportResult(200, quality_body(True)),
        TransportResult(200, compare_body(True)),
        TransportResult(200, compare_body(True)),
        TransportResult(200, search_body("reliable_new")),
        TransportResult(201, register_body("e")),
        TransportResult(200, query_body("registered", "e")),
    ]
    adapter, fake = _adapter(cfg, responses)
    adapter.quality(IMAGES)
    adapter.same_person(IMAGES)
    adapter.search_1n(NS, IMAGES)
    adapter.register_person(NS, "e", IMAGES, "c", "r")
    adapter.query_registration("c", "r", namespace=NS, entity_id="e")
    assert len(fake.calls) == 8
    for call in fake.calls:
        body = call["json_body"] or {}
        for forbidden in FORBIDDEN_REQUEST_KEYS:
            assert forbidden not in body, (call["path"], forbidden)
        assert call["headers_extra"] is None


def test_liveness_unsupported_response_is_not_a_failure(monkeypatch: Any, tmp_path: Any) -> None:
    """服务诚实报告 supported=false 不构成失败，也不中断身份链。"""
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(
        cfg,
        [
            TransportResult(200, quality_body(True)),
            TransportResult(200, quality_body(True)),
            TransportResult(200, quality_body(True)),
            TransportResult(200, compare_body(True)),
            TransportResult(200, compare_body(True)),
            TransportResult(200, search_body("uncertain", reasons=["empty_library"])),
        ],
    )
    assert adapter.quality(IMAGES).status == "accepted"
    assert adapter.same_person(IMAGES).ok is True
    assert adapter.search_1n(NS, IMAGES).classification == "uncertain"


def test_adapter_docstring_states_no_anti_spoofing() -> None:
    doc = InsightFaceAdapter.__doc__ or ""
    assert "照片比对" in doc and "无防翻拍" in doc


def test_no_double_fallback_on_service_failure(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [FaceServiceConnectionError("c")])
    assert not isinstance(adapter, FaceDouble)
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


# ================================================================ 9) 脱敏扫描


def test_no_secret_or_identifier_values_in_logs_or_exceptions(
    monkeypatch: Any, tmp_path: Any, caplog: Any
) -> None:
    secret = TOKEN
    namespace = "secret-namespace-value"
    correlation = "secret-correlation-value"
    entity = "secret-entity-value"
    image = b"secret-image-bytes"
    images = {"front": image, "left": image, "right": image}
    cfg = _cfg(monkeypatch, tmp_path, auto_enroll=True)

    raised: list[str] = []
    with caplog.at_level(logging.DEBUG):
        # 成功路径：每个操作各自一个 adapter + 恰好的响应序列。
        scenarios = (
            (["quality"] * 3, [TransportResult(200, quality_body(True)) for _ in range(3)]),
            (["same_person"] * 2, [TransportResult(200, compare_body(True)) for _ in range(2)]),
            (["search"], [TransportResult(200, search_body("reliable_new"))]),
            (["register"], [TransportResult(201, register_body(entity))]),
            (["query"], [TransportResult(200, query_body("registered", entity))]),
        )
        for ops, responses in scenarios:
            adapter, _ = _adapter(cfg, list(responses))
            if ops[0] == "quality":
                adapter.quality(images)
            elif ops[0] == "same_person":
                adapter.same_person(images)
            elif ops[0] == "search":
                adapter.search_1n(namespace, images)
            elif ops[0] == "register":
                adapter.register_person(namespace, entity, images, correlation, "req")
            else:
                adapter.query_registration(correlation, "req", namespace=namespace, entity_id=entity)
        # 失败路径（异常文本）
        for exc in (
            FaceServiceTimeout("t"),
            http_error(500, "INTERNAL_ERROR", True),
            http_error(401, "UNAUTHORIZED", False),
        ):
            adapter, _ = _adapter(cfg, [exc])
            with pytest.raises((ProviderUnavailable, ProviderConfigError)) as ei:
                adapter.search_1n(namespace, images)
            # 整条异常因果链（__cause__/__context__）都不得泄漏取值。
            raised.append(_exception_chain_text(ei.value))

    haystack = caplog.text + "".join(raised)
    for needle in (secret, namespace, correlation, entity):
        assert needle not in haystack, needle
    assert base64.b64encode(image).decode() not in haystack
    assert str(image) not in haystack


def test_register_gate_closed_exception_has_no_ids(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _cfg(monkeypatch, tmp_path)
    adapter, _ = _adapter(cfg, [])
    with pytest.raises(ProviderNotActivated) as ei:
        adapter.register_person("secret-ns", "secret-entity", IMAGES, "secret-corr", "secret-req")
    message = _exception_chain_text(ei.value)
    for needle in ("secret-ns", "secret-entity", "secret-corr", "secret-req", TOKEN):
        assert needle not in message


def test_exception_chain_text_includes_wrapped_cause() -> None:
    """判别力：链扫描必须真的覆盖 ``raise ... from`` 的底层异常文本。"""
    try:
        try:
            raise ValueError("secret-cause-marker")
        except ValueError as cause:
            raise RuntimeError("outer") from cause
    except RuntimeError as exc:
        text = _exception_chain_text(exc)
    assert "secret-cause-marker" in text
    assert "outer" in text


# ================================================================ 10) 真实传输 + 合同忠实 stub 服务


class _StubFaceService(http.server.BaseHTTPRequestHandler):
    """本地 stub（**非** B 的 face-service）：验证真实 stdlib 传输 + 严格响应校验。

    **保真度声明**：对所实现的端点，成功/错误**响应**与冻结合同逐键一致
    （register: api.py:726-741 全 12 键 + 201/200 状态；registrations: api.py:844-852
    全 7 键；search: 合同 §4.3；quality/compare: api.py 对应构造）。它**只实现**本测试
    所需端点（quality/compare/search/subjects/registrations），不实现 extract/verify/
    delete/info/health/ready；语义（幂等/可见性/一致性）是简化模型，不是数据库实现。
    """

    protocol_version = "HTTP/1.1"

    _REGISTERED_AT = "2026-09-16T00:00:00Z"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002,D102 - 静默
        return

    # -- helpers ------------------------------------------------------
    def _json_in(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _send(self, status: int, body: Any) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-Id", self.headers.get("X-Request-Id") or "stub")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, code: str, retryable: bool) -> None:
        self._send(
            status,
            {"error": {"code": code, "message": "stub", "retryable": retryable,
                       "request_id": self.headers.get("X-Request-Id") or "stub"}},
        )

    def _authorized(self) -> bool:
        return self.headers.get("X-Internal-Token") == self.server.expected_token  # type: ignore[attr-defined]

    def _register_response(
        self,
        *,
        subject_id: str,
        namespace: str,
        created: bool,
        replayed: bool,
        revision: int,
    ) -> dict[str, Any]:
        """Full frozen register shape — api.py:726-741 (12 keys)."""
        return {
            "subject_id": subject_id,
            "namespace": namespace,
            "created": created,
            "created_at": "2026-09-16T00:00:00Z",
            "updated_at": "2026-09-16T00:00:00Z",
            "embedding_dim": 64,
            "model_version": "stub-model@0",
            "quality": {"min_acceptable": True, "liveness": {"supported": False}},
            "library_revision": revision,
            "replayed": replayed,
            "registered_at": "2026-09-16T00:00:00Z",
            "request_id": self.headers.get("X-Request-Id") or "stub",
        }

    # -- routes -------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        state = self.server.state  # type: ignore[attr-defined]
        if not self._authorized():
            self._error(401, "UNAUTHORIZED", False)
            return
        path = self.path.split("?", 1)[0]
        if path.startswith("/v1/namespaces/") and "/registrations/" in path:
            ns = path.split("/")[3]
            correlation = path.rsplit("/", 1)[1]
            if ns not in state["namespaces"]:
                self._error(404, "NAMESPACE_NOT_FOUND", False)
                return
            record = state["registrations"].get((ns, correlation))
            if record is not None:
                # Mirror store.find_registration: supplied filters must agree, else not_found.
                query = (
                    parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
                )
                wanted_request = query.get("provider_request_id", [None])[0]
                wanted_entity = query.get("entity_id", [None])[0]
                if wanted_request is not None and wanted_request != record["provider_request_id"]:
                    record = None
                elif wanted_entity is not None and wanted_entity != record["subject_id"]:
                    record = None
            if record is None:
                self._send(200, {"status": "not_found", "request_id": self.headers.get("X-Request-Id") or "stub"})
                return
            # Full frozen shape — api.py:844-852 (7 keys).
            self._send(200, {
                "status": "registered",
                "subject_id": record["subject_id"],
                "correlation_id": correlation,
                "provider_request_id": record["provider_request_id"],
                "registered_at": record["registered_at"],
                "library_revision": state["revision"],
                "request_id": self.headers.get("X-Request-Id") or "stub",
            })
            return
        self._error(404, "INVALID_REQUEST", False)

    def do_POST(self) -> None:  # noqa: N802
        state = self.server.state  # type: ignore[attr-defined]
        if not self._authorized():
            self._error(401, "UNAUTHORIZED", False)
            return
        path = self.path.split("?", 1)[0]
        payload = self._json_in()
        if path == "/v1/quality":
            ok = not payload.get("image_base64", "").startswith(base64.b64encode(b"BAD").decode())
            self._send(200, {
                "face_count": 1,
                "faces": [{"bbox": [0, 0, 1, 1], "det_score": 0.9,
                           "quality": {"min_acceptable": ok, "liveness": {"supported": False}},
                           "largest_face": True}],
                "largest_face_index": 0, "namespace": None, "model_version": "stub",
                "library_revision": state["revision"], "liveness": {"supported": False},
                "request_id": "stub",
            })
            return
        if path == "/v1/compare":
            matched = payload.get("image_a_base64") == payload.get("image_b_base64")
            self._send(200, {"matched": matched, "similarity": 1.0 if matched else 0.0, "threshold": 0.4,
                             "face_count_a": 1, "face_count_b": 1,
                             "quality_a": {"min_acceptable": True}, "quality_b": {"min_acceptable": True},
                             "liveness": {"supported": False}, "reasons": [],
                             "model_version": "stub", "library_revision": state["revision"],
                             "request_id": "stub"})
            return
        if path.endswith("/search"):
            ns = path.split("/")[3]
            if not state["subjects"]:
                body = {"decision": "reliable_new", "ambiguous": False,
                        "quality": {"min_acceptable": True}, "reasons": ["empty_library"],
                        "subject_count": 0, "top_k": 5, "policy_version": "search-v2",
                        "model_version": "stub", "library_revision": state["revision"],
                        "request_id": "stub"}
            else:
                sid = sorted(state["subjects"])[0]
                body = {"decision": "matched", "subject_id": sid, "similarity": 0.9, "ambiguous": False,
                        "quality": {"min_acceptable": True}, "reasons": [],
                        "subject_count": len(state["subjects"]), "top_k": 5,
                        "policy_version": "search-v2", "model_version": "stub",
                        "library_revision": state["revision"], "request_id": "stub"}
            self._send(200, body)
            return
        if path.endswith("/subjects"):
            ns = path.split("/")[3]
            subject_id = payload.get("subject_id")
            correlation = payload.get("correlation_id")
            if not isinstance(subject_id, str) or not subject_id:
                self._error(400, "INVALID_REQUEST", False)
                return
            existing = state["registrations"].get((ns, correlation)) if correlation else None
            if subject_id in state["subjects"]:
                if existing is not None and existing["subject_id"] == subject_id:
                    # Idempotent replay — 200, created=False, replayed=True (no revision bump).
                    self._send(200, self._register_response(
                        subject_id=subject_id, namespace=ns, created=False, replayed=True,
                        revision=state["revision"],
                    ))
                    return
                self._error(409, "SUBJECT_ALREADY_EXISTS", False)
                return
            state["namespaces"].add(ns)
            state["subjects"].add(subject_id)
            if correlation:
                state["registrations"][(ns, correlation)] = {
                    "subject_id": subject_id,
                    "provider_request_id": payload.get("provider_request_id"),
                    "registered_at": self._REGISTERED_AT,
                }
            state["revision"] += 1
            self._send(201, self._register_response(
                subject_id=subject_id, namespace=ns, created=True, replayed=False,
                revision=state["revision"],
            ))
            return
        self._error(404, "INVALID_REQUEST", False)


@pytest.fixture
def stub_service() -> Any:
    """本地合同忠实 stub：临时端口 127.0.0.1:0 + 内存状态（无文件写入）。"""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubFaceService)
    server.expected_token = TOKEN  # type: ignore[attr-defined]
    server.state = {"namespaces": set(), "subjects": set(), "registrations": {}, "revision": 0}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _live_adapter(
    monkeypatch: Any, tmp_path: Any, server: Any, *, auto_enroll: bool = True
) -> InsightFaceAdapter:
    port = server.server_address[1]
    assert port not in {18083, 18084, 55435, 55432, 18087, 18088, 18085, 8010}
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, f"http://127.0.0.1:{port}")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, NS)
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, _write_token(tmp_path))
    monkeypatch.setenv(FACE_SERVICE_AUTO_ENROLL_ENV, "true" if auto_enroll else "false")
    port_obj = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(port_obj, InsightFaceAdapter)
    return port_obj


def test_live_transport_quality_and_compare(monkeypatch: Any, tmp_path: Any, stub_service: Any) -> None:
    adapter = _live_adapter(monkeypatch, tmp_path, stub_service)
    assert adapter.quality(IMAGES).status == "accepted"
    assert adapter.quality({"front": b"BAD", "left": LEFT, "right": RIGHT}).required_views == ("front",)
    assert adapter.same_person({"front": FRONT, "left": FRONT, "right": b"other"}).ok is False
    assert adapter.same_person({"front": FRONT, "left": FRONT, "right": FRONT}).ok is True


def test_live_transport_search_empty_then_register_and_reconcile(
    monkeypatch: Any, tmp_path: Any, stub_service: Any
) -> None:
    adapter = _live_adapter(monkeypatch, tmp_path, stub_service, auto_enroll=True)
    state = stub_service.state
    # 空库 → reliable_new（合同 §4.2 裁定 1）
    empty = adapter.search_1n(NS, IMAGES)
    assert empty.classification == "reliable_new"
    assert empty.face_subject_ref is None
    # 登记 → 201 success；revision 仅因真实创建 +1
    assert state["revision"] == 0
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "success"
    assert state["revision"] == 1
    # 同 correlation 重放 → 200 success；revision 不变
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1").status == "success"
    assert state["revision"] == 1
    # 不同 correlation 同 subject → 409 → failed；revision 不变
    assert adapter.register_person(NS, "entity-1", IMAGES, "corr-2", "req-2").status == "failed"
    assert state["revision"] == 1
    # 对账：命中 / 未命中
    assert adapter.query_registration("corr-1", "req-1", namespace=NS, entity_id="entity-1").status == "registered"
    assert adapter.query_registration("corr-unknown", "req-1", namespace=NS).status == "not_found"
    # 登记后搜索 → matched + subject ref
    matched = adapter.search_1n(NS, IMAGES)
    assert matched.classification == "matched"
    assert matched.face_subject_ref == "entity-1"


def test_live_transport_bad_token_is_config_error(
    monkeypatch: Any, tmp_path: Any, stub_service: Any
) -> None:
    adapter = _live_adapter(monkeypatch, tmp_path, stub_service)
    stub_service.expected_token = "A-DIFFERENT-TOKEN"
    with pytest.raises(ProviderConfigError) as ei:
        adapter.search_1n(NS, IMAGES)
    assert FACE_SERVICE_TOKEN_FILE_ENV in str(ei.value)
    assert TOKEN not in str(ei.value)


def test_live_transport_gate_closed_makes_no_registration_write(
    monkeypatch: Any, tmp_path: Any, stub_service: Any
) -> None:
    adapter = _live_adapter(monkeypatch, tmp_path, stub_service, auto_enroll=False)
    with pytest.raises(ProviderNotActivated):
        adapter.register_person(NS, "entity-1", IMAGES, "corr-1", "req-1")
    assert stub_service.state["revision"] == 0
    assert stub_service.state["subjects"] == set()


def test_live_transport_no_token_in_logs(monkeypatch: Any, tmp_path: Any, stub_service: Any, caplog: Any) -> None:
    adapter = _live_adapter(monkeypatch, tmp_path, stub_service)
    with caplog.at_level(logging.DEBUG):
        adapter.search_1n("live-secret-ns", IMAGES)
    assert TOKEN not in caplog.text
    assert "live-secret-ns" not in caplog.text


def test_live_transport_unreachable_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    """无服务监听 → 连接失败 → 可重试不可用（绝不回退替身）。"""
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, "http://127.0.0.1:1")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, NS)
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, _write_token(tmp_path))
    adapter = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(adapter, InsightFaceAdapter)
    with pytest.raises(ProviderUnavailable):
        adapter.search_1n(NS, IMAGES)


def test_parse_json_bytes_helper() -> None:
    assert parse_json_bytes(b'{"a": 1}') == {"a": 1}
    assert parse_json_bytes('{"a": 1}') == {"a": 1}
    assert parse_json_bytes(b"not-json") is None
    assert parse_json_bytes(b"") is None
    assert parse_json_bytes({"a": 1}) == {"a": 1}