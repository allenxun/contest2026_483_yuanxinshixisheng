"""llm_rag（weijing assess / shuiguang_cloud_v1）真实适配器契约级测试。

本地 ``threading.http.server`` 替身（临时端口）；fixture 样本来自用户授权合同草稿
（``tests/fixtures/shuiguang_cloud_v1/``，非线上算法证据）。核心红线：
受理（HTTP 2xx / problem 正确分类）≠ 完成（结构合法 **且** 批准输出映射 **且** 冻结
校验通过 → 才可能 ready）；未获批准映射 → fail-closed 终态；绝不臆造分数、绝不
丢分区口径静默降级、绝不 mock 回退。
"""
from __future__ import annotations

import hashlib
import http.server
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    fetch_plan,
    make_ctx,
    mark_report_ready,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_microcrystal,
    seed_plan,
)
from mvp_worker.handlers import JobFailed
from mvp_worker.handlers.dshared import weijing_mapping
from mvp_worker.handlers.dshared.dconfig import DConfig, ProviderConfigError
from mvp_worker.handlers.dshared.providers import (
    LLMRagPlanAdapter,
    PlanDouble,
    ProviderUnavailable,
    build_plan_port,
)
from mvp_worker.handlers.plan_generate import handler as plan_handler
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import StaleGeneration, complete_failure

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "shuiguang_cloud_v1"
API_KEY = "test-key-not-a-secret"
REQUEST_MAPPING = {
    "score_transform": "invert_100_minus",
    "rounding": "half_up",
    "score_source": "global_front",
}


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def _load_raw() -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / "response_example.json").read_text(encoding="utf-8"))


def _snapshot(*, report_id: str = "rep-1") -> dict[str, Any]:
    return {"report": {"assessment_id": str(uuid.uuid4()), "report_id": report_id}}


def _adapter(
    base_url: str,
    *,
    request_mapping: Any = None,
    output_mapping: Any = None,
    timeout: int = 5,
) -> LLMRagPlanAdapter:
    cfg = replace(
        DConfig.from_env(),
        plan_provider="llm_rag",
        llm_rag_base_url=base_url,
        llm_rag_api_key=API_KEY,
        llm_rag_timeout_seconds=timeout,
        llm_rag_request_mapping=request_mapping,
        llm_rag_output_mapping=output_mapping,
    )
    return LLMRagPlanAdapter(cfg)


# ---------------------------------------------------------------- stub server


class _StubHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib 签名
        return

    def do_POST(self) -> None:  # noqa: N802
        srv = self.server
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = None
        srv.requests.append(  # type: ignore[attr-defined]
            {
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body,
            }
        )
        if srv.delay:  # type: ignore[attr-defined]
            time.sleep(srv.delay)  # type: ignore[attr-defined]
        if srv.raw_body is not None:  # type: ignore[attr-defined]
            data = srv.raw_body  # type: ignore[attr-defined]
        else:
            data = json.dumps(srv.body, ensure_ascii=False).encode("utf-8")  # type: ignore[attr-defined]
        self.send_response(srv.status)  # type: ignore[attr-defined]
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _WeijingStub:
    def __init__(
        self,
        *,
        status: int = 200,
        body: Any = None,
        raw_body: Optional[bytes] = None,
        delay: float = 0.0,
    ) -> None:
        self.requests: list[dict[str, Any]] = []
        self._status = status
        self._body = body
        self._raw_body = raw_body
        self._delay = delay
        self._server: Optional[http.server.ThreadingHTTPServer] = None

    def __enter__(self) -> "_WeijingStub":
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        server.requests = self.requests  # type: ignore[attr-defined]
        server.status = self._status  # type: ignore[attr-defined]
        server.body = self._body  # type: ignore[attr-defined]
        server.raw_body = self._raw_body  # type: ignore[attr-defined]
        server.delay = self._delay  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._server = server
        self.port = server.server_address[1]
        return self

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()


def _assessment(status: str = "READY_CARE") -> dict[str, Any]:
    return {
        "assessment_id": str(uuid.uuid4()),
        "created_at": "2026-09-14T00:00:00Z",
        "rendered_markdown": "## 方案\n（真实感渲染文本）",
        "plan": {
            "plan_id": "plan-1",
            "status": status,
            "knowledge_version": "1.0",
            "device_enabled": False,
            "actual_device_seconds": 0,
        },
    }


def _envelope(assessment: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "request_id": "req-1",
        "invocation_id": "inv-1",
        "spoken_text": "中文方案文本",
        "assessment": _assessment() if assessment is None else assessment,
        "continuation_state": {
            "weijing_assessment_id": "a-1",
            "weijing_owner_id": "device:k7-01",
        },
    }


# ---------------------------------------------------------------- (a) fixture


def test_fixture_sha256_matches_attribution() -> None:
    attribution = (FIXTURE_DIR / "ATTRIBUTION.md").read_text(encoding="utf-8")
    expected = {
        "response_example.json": "f533781f07867f6eb93dd9a3d46f1937111dfe6a940b7cebba30551edc52cb6f",
        "response_models.reference.py": "c6ac30dd90f38f1c4a941efaec01cca7c63903620dde6a3885d221b62e7b9413",
        "字段说明.md": "dcba1490c10e1fdab2da1eae724052a6f0ffe926ce54f5e117e42b538b5059ee",
    }
    for name, digest in expected.items():
        actual = hashlib.sha256((FIXTURE_DIR / name).read_bytes()).hexdigest()
        assert actual == digest, name
        assert digest in attribution, name


# ------------------------------------------------- (b) approved request build


def test_request_build_approved_mechanism() -> None:
    raw = _load_raw()
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(weijing_mapping.MappingNotApproved):
            adapter.generate({"raw_detection": raw}, _snapshot(report_id="rep-xyz"))
        assert len(stub.requests) == 1  # 受理发生（请求已发出）
        req = stub.requests[0]
        assert req["path"] == "/internal/v1/weijing/reports/assess"
        headers = req["headers"]
        assert headers["x-service-name"] == "medical-platform"
        assert headers["x-api-key"] == API_KEY
        assert re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", headers["x-request-id"])
        assert re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", headers["idempotency-key"])
        assert headers["x-protocol-version"] == "1.0"
        assert re.fullmatch(
            r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", headers["traceparent"]
        )
        assert headers["accept"] == "application/json"
        assert headers["content-type"] == "application/json"

        body = req["body"]
        assert set(body["regions"]) <= {"F", "L", "R", "C"}
        assert set(body["regions"]) == {"F", "L", "R", "C"}
        for region in ("F", "L", "R", "C"):
            assert body["regions"][region] == {"P": 40, "O": 82}  # 100−59.9=40.1→40; 100−17.6=82.4→82
            assert isinstance(body["regions"][region]["P"], int)
            assert isinstance(body["regions"][region]["O"], int)
            assert "D" not in body["regions"][region]
        assert body["report_id"] == "rep-xyz"
        assert body["algorithm_version"] == "shuiguang_cloud_v1"
        assert "device_id" not in body  # device_id absent in report_context → OMIT
        flat = json.dumps(body)
        for forbidden in ("total_count", "unassigned", "views", "nose", "perioral", "pores"):
            assert forbidden not in flat


def test_request_build_omits_null_score_never_zero() -> None:
    raw = _load_raw()
    # 合法 null：score 与 severity 必须同时为 null（合同 score None ⇔ severity None）。
    raw["results"]["surface_gloss"]["score"] = None
    raw["results"]["surface_gloss"]["severity"] = None
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(weijing_mapping.MappingNotApproved):
            adapter.generate({"raw_detection": raw}, _snapshot())
        body = stub.requests[0]["body"]
        for region in ("F", "L", "R", "C"):
            assert "O" not in body["regions"][region]  # null → 省略，绝不写 0
            assert body["regions"][region]["P"] == 40


# -------------------------------------------- (c)(d) pre-network fail-closed


def test_request_mapping_unset_terminal_pre_network() -> None:
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=None)
        with pytest.raises(weijing_mapping.MappingNotApproved):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())
        assert stub.requests == []  # 无网络


def test_request_mapping_unregistered_transform_terminal() -> None:
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(
            stub.base_url,
            request_mapping={"score_transform": "not_registered", "rounding": "half_up", "score_source": "global_front"},
        )
        with pytest.raises(weijing_mapping.MappingNotApproved):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())
        assert stub.requests == []


def test_raw_detection_absent_terminal_no_network() -> None:
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(weijing_mapping.MappingNotApproved) as excinfo:
            adapter.generate({}, _snapshot())
        assert "N.4" in str(excinfo.value)
        assert stub.requests == []


# ---------------------------------------- (e) acceptance != completion (200)


def test_success_envelope_output_mapping_unset_terminal_after_acceptance() -> None:
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING, output_mapping=None)
        with pytest.raises(weijing_mapping.MappingNotApproved):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())
        assert len(stub.requests) == 1  # HTTP 已受理（200），但完成被拒绝


# --------------------------------------------- (f) envelope contract violations


def _mut_spoken_text_only(body: dict[str, Any]) -> None:
    for key in ("request_id", "invocation_id", "assessment", "continuation_state"):
        del body[key]


def _mut_missing_assessment(body: dict[str, Any]) -> None:
    del body["assessment"]


def _mut_unknown_plan_status(body: dict[str, Any]) -> None:
    body["assessment"]["plan"]["status"] = "MADE_UP_STATUS"


def _mut_extra_envelope_key(body: dict[str, Any]) -> None:
    body["extra"] = 1


@pytest.mark.parametrize(
    "mutator",
    [_mut_spoken_text_only, _mut_missing_assessment, _mut_unknown_plan_status, _mut_extra_envelope_key],
    ids=["spoken_text_only", "missing_assessment", "unknown_plan_status", "extra_envelope_key"],
)
def test_envelope_violations_terminal_never_ready(mutator: Callable[[dict], None]) -> None:
    body = _envelope()
    mutator(body)
    with _WeijingStub(status=200, body=body) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(weijing_mapping.ResponseContractViolation):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())


# ---------------------------------------------------- (g) problem matrix


def _status_for(code: str) -> int:
    return {
        "AI_UNAUTHORIZED": 401,
        "AI_REQUEST_INVALID": 400,
        "AI_PAYLOAD_TOO_LARGE": 413,
        "AI_SERVICE_UNAVAILABLE": 503,
        "AI_UPSTREAM_TIMEOUT": 504,
        "AI_INTERNAL_ERROR": 500,
    }[code]


@pytest.mark.parametrize(
    "code,retryable_flag,expected",
    [
        ("AI_UNAUTHORIZED", True, weijing_mapping.PlanProviderConfigRequired),
        ("AI_UNAUTHORIZED", False, weijing_mapping.PlanProviderConfigRequired),
        ("AI_REQUEST_INVALID", True, weijing_mapping.ResponseContractViolation),
        ("AI_REQUEST_INVALID", False, weijing_mapping.ResponseContractViolation),
        ("AI_PAYLOAD_TOO_LARGE", True, weijing_mapping.ResponseContractViolation),
        ("AI_PAYLOAD_TOO_LARGE", False, weijing_mapping.ResponseContractViolation),
        ("AI_SERVICE_UNAVAILABLE", True, ProviderUnavailable),
        ("AI_SERVICE_UNAVAILABLE", False, weijing_mapping.ResponseContractViolation),
        ("AI_UPSTREAM_TIMEOUT", True, ProviderUnavailable),
        ("AI_UPSTREAM_TIMEOUT", False, weijing_mapping.ResponseContractViolation),
        ("AI_INTERNAL_ERROR", True, ProviderUnavailable),
        ("AI_INTERNAL_ERROR", False, weijing_mapping.ResponseContractViolation),
    ],
)
def test_problem_matrix_classification(
    code: str, retryable_flag: bool, expected: type
) -> None:
    problem = {
        "type": f"urn:aisia:ai:error:{code}",
        "title": "t",
        "status": _status_for(code),
        "code": code,
        "detail": "sanitized field path only, no values",
        "retryable": retryable_flag,
    }
    with _WeijingStub(status=_status_for(code), body=problem) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(expected):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())


def test_unparseable_problem_is_retryable() -> None:
    with _WeijingStub(status=500, raw_body=b"<<not-json>>") as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(ProviderUnavailable):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())


# ---------------------------------------------------- (h) transport


def test_transport_connection_refused_retryable() -> None:
    adapter = _adapter("http://127.0.0.1:1", request_mapping=REQUEST_MAPPING)
    with pytest.raises(ProviderUnavailable):
        adapter.generate({"raw_detection": _load_raw()}, _snapshot())
    assert not isinstance(adapter, PlanDouble)  # 绝不回退 mock


def test_transport_timeout_retryable() -> None:
    with _WeijingStub(status=200, body=_envelope(), delay=2.0) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING, timeout=1)
        with pytest.raises(ProviderUnavailable):
            adapter.generate({"raw_detection": _load_raw()}, _snapshot())


# ---------------------------------------------------- (i) config


def test_llm_rag_missing_config_names_keys_only(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "llm_rag")
    monkeypatch.delenv("MVP_D_LLM_RAG_BASE_URL", raising=False)
    monkeypatch.delenv("MVP_D_LLM_RAG_API_KEY", raising=False)
    cfg = DConfig.from_env()
    with pytest.raises(ProviderConfigError) as excinfo:
        build_plan_port(cfg, environment="dev")
    assert "MVP_D_LLM_RAG_BASE_URL" in str(excinfo.value)
    assert "MVP_D_LLM_RAG_API_KEY" in str(excinfo.value)


def test_plan_provider_default_double_and_production_refusal(monkeypatch: Any) -> None:
    monkeypatch.delenv("MVP_D_PLAN_PROVIDER", raising=False)
    assert isinstance(build_plan_port(DConfig.from_env(), environment="dev"), PlanDouble)
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "double")
    with pytest.raises(ProviderConfigError):
        build_plan_port(DConfig.from_env(), environment="production")


def test_plan_provider_unknown_fails_fast(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "nope")
    with pytest.raises(ProviderConfigError):
        build_plan_port(DConfig.from_env(), environment="dev")


def test_llm_rag_config_valid_builds_adapter(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "llm_rag")
    monkeypatch.setenv("MVP_D_LLM_RAG_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MVP_D_LLM_RAG_API_KEY", API_KEY)
    port = build_plan_port(DConfig.from_env(), environment="dev")
    assert isinstance(port, LLMRagPlanAdapter)
    assert port.provider_name == "llm_rag"


# ---------------------------------------------------- (j) handler level


def _seed_plan_with_raw(engine: Engine, raw_detection: dict[str, Any]) -> tuple[str, str, str]:
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=1)
    member_id = seed_member(engine, ns=DEFAULT_NS, ref=str(uuid.uuid4()), assessment_id=aid)
    mark_report_ready(engine, aid, member_id=member_id, report_photo_version=1)
    with engine.begin() as conn:
        payload = {
            "schema_version": 1,
            "conclusion": "balanced",
            "metrics": [{"name": "moisture", "value": 55.0, "unit": "percent"}],
            "description": "seed report",
            "images": [],
            "raw_detection": raw_detection,
        }
        conn.execute(
            text("UPDATE skin_assessments SET report_payload = CAST(:p AS jsonb) WHERE id = CAST(:a AS uuid)"),
            {"p": json.dumps(payload), "a": aid},
        )
    seed_microcrystal(engine)  # 能力齐 → waiting_inputs 分支可进入 generating
    pid = seed_plan(
        engine, assessment_id=aid, member_id=member_id,
        generation_status="waiting_inputs", generation_revision=0, input_photo_version=1,
    )
    jid, _ = enqueue(
        engine,
        job_type="plan.generate",
        dedup_key=f"plan:{pid}:0",
        owner_type="plan",
        owner_id=pid,
        input_revision=0,
        payload={"schema_version": 1, "plan_id": pid, "generation_revision": "0"},
    )
    return aid, pid, jid


def test_handler_output_mapping_unset_terminal_t06_failed(engine: Engine) -> None:
    raw = _load_raw()
    _aid, pid, jid = _seed_plan_with_raw(engine, raw)
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING, output_mapping=None)
        status, exc, _ = run_claimed(engine, plan_handler, jid, extras={"plan_port": adapter})
        assert status == "failed" and exc is not None
        assert exc.code == "PLAN_MAPPING_NOT_APPROVED" and exc.retryable is False
        assert len(stub.requests) == 1  # 受理发生

    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"  # 非 stranded 'generating'
    assert plan["generation_revision"] == 0  # 代次不变
    assert plan["plan_payload"] is None  # 绝不 ready
    assert plan["completed_count"] == 0  # K 未动
    assert plan["completed_at"] is None
    assert plan["progress_revision"] == 0


def test_handler_request_mapping_unset_terminal_pre_network(engine: Engine) -> None:
    raw = _load_raw()
    _aid, pid, jid = _seed_plan_with_raw(engine, raw)
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=None)
        status, exc, _ = run_claimed(engine, plan_handler, jid, extras={"plan_port": adapter})
        assert status == "failed" and exc is not None
        assert exc.code == "PLAN_MAPPING_NOT_APPROVED" and exc.retryable is False
        assert stub.requests == []  # 未发起网络

    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"
    assert plan["plan_payload"] is None
    assert plan["completed_count"] == 0


# ---------------------------------------------------- (k) secret hygiene


def test_api_key_never_logged_success_and_error_paths(caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)
    raw = _load_raw()
    # 成功信封 + 未批准输出映射（含请求已发）
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(Exception):
            adapter.generate({"raw_detection": raw}, _snapshot())
    # problem 错误路径（detail 为服务端脱敏文本）
    problem = {
        "type": "urn:aisia:ai:error:AI_REQUEST_INVALID",
        "title": "t",
        "status": 400,
        "code": "AI_REQUEST_INVALID",
        "detail": "sanitized field path only",
        "retryable": False,
    }
    with _WeijingStub(status=400, body=problem) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(Exception):
            adapter.generate({"raw_detection": raw}, _snapshot())

    assert API_KEY not in caplog.text
    assert "test-key" not in caplog.text


# ---------------------------------------------------------------- Fix 2 negatives


def _neg_score_basis_spots(raw: dict) -> None:
    raw["results"]["spots"]["score_basis"] = "v2_oiliness_tendency"


def _neg_float_count(raw: dict) -> None:
    raw["results"]["pores"]["total_count"]["left"] = 1.5


def _neg_negative_count(raw: dict) -> None:
    raw["results"]["pores"]["regions"][0]["front"] = -1


def _neg_bool_score(raw: dict) -> None:
    raw["results"]["spots"]["score"] = True


def _neg_extra_top_key(raw: dict) -> None:
    raw["extra"] = 1


def _neg_extra_region_key(raw: dict) -> None:
    raw["results"]["pores"]["regions"][0]["extra"] = 1


def _neg_primary_count_mismatch(raw: dict) -> None:
    raw["results"]["pores"]["regions"][0]["primary_count"] = 999


def _neg_primary_view_null_with_count(raw: dict) -> None:
    raw["results"]["pores"]["regions"][0]["primary_view"] = None


def _neg_main_image_mismatch(raw: dict) -> None:
    raw["main_image_id"] = "image_99"


def _neg_reconciliation_off_by_one(raw: dict) -> None:
    raw["results"]["pores"]["total_count"]["front"] += 1


def _neg_severity_with_null_score(raw: dict) -> None:
    raw["results"]["spots"]["score"] = None


def _neg_unknown_region(raw: dict) -> None:
    raw["results"]["pores"]["regions"][0]["region"] = "unknown_region"


def _neg_invalid_severity(raw: dict) -> None:
    raw["results"]["spots"]["severity"] = "极度"


def _neg_missing_task_id(raw: dict) -> None:
    del raw["task_id"]


@pytest.mark.parametrize(
    "mutator",
    [
        _neg_score_basis_spots,
        _neg_float_count,
        _neg_negative_count,
        _neg_bool_score,
        _neg_extra_top_key,
        _neg_extra_region_key,
        _neg_primary_count_mismatch,
        _neg_primary_view_null_with_count,
        _neg_main_image_mismatch,
        _neg_reconciliation_off_by_one,
        _neg_severity_with_null_score,
        _neg_unknown_region,
        _neg_invalid_severity,
        _neg_missing_task_id,
    ],
    ids=[
        "score_basis_spots",
        "float_count",
        "negative_count",
        "bool_score",
        "extra_top_key",
        "extra_region_key",
        "primary_count_mismatch",
        "primary_view_null_with_count",
        "main_image_mismatch",
        "reconciliation_off_by_one",
        "severity_with_null_score",
        "unknown_region",
        "invalid_severity",
        "missing_task_id",
    ],
)
def test_raw_detection_contract_negatives_pre_network(
    mutator: Callable[[dict], None]
) -> None:
    raw = json.loads(json.dumps(_load_raw()))
    mutator(raw)
    with _WeijingStub(status=200, body=_envelope()) as stub:
        adapter = _adapter(stub.base_url, request_mapping=REQUEST_MAPPING)
        with pytest.raises(weijing_mapping.RawDetectionContractViolation):
            adapter.generate({"raw_detection": raw}, _snapshot())
        assert stub.requests == []  # 违反合同绝不发请求


def test_fixture_passes_full_closed_contract_verbatim() -> None:
    weijing_mapping.validate_raw_detection(_load_raw())  # 正例：fixture 原样通过


# ------------------------------------------------ Fix 1(a) generation fence


class _UnapprovedAdapter:
    provider_name = "llm_rag"
    model_version = "weijing-shuiguang_cloud_v1"

    def generate(self, report_context: Any, input_snapshot: Any) -> Any:
        raise weijing_mapping.MappingNotApproved("not approved (test stub)")


def test_terminal_stale_generation_does_not_touch_new_revision(engine: Engine) -> None:
    """Fix 1(a)：旧代次终态回调在新一代 T06 上 0 行 → StaleGeneration 整体回滚。"""
    _aid, pid, jid = _seed_plan_with_raw(engine, _load_raw())
    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=50)
    claim = next(c for c in claims if c.id == jid)
    ctx = make_ctx(engine, claim, extras={"plan_port": _UnapprovedAdapter()})
    with pytest.raises(JobFailed) as ei:
        plan_handler.handle(ctx, claim)
    assert ei.value.code == "PLAN_MAPPING_NOT_APPROVED" and ei.value.retryable is False
    assert ei.value.business_tx is not None  # fenced terminal 回调（plan_id+rev 守卫）

    # C 侧输入翻转：T06 推进到 generation_revision=1（新一代）。
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE care_plans SET generation_status='generating',"
                " generation_revision=1 WHERE id=CAST(:id AS uuid)"
            ),
            {"id": pid},
        )
    before = fetch_plan(engine, pid)

    with pytest.raises(StaleGeneration):
        complete_failure(
            engine, claim,
            code=ei.value.code, message=ei.value.message,
            retryable=ei.value.retryable, business_tx=ei.value.business_tx,
        )

    after = fetch_plan(engine, pid)
    assert after["generation_status"] == "generating"  # 新一代未被旧代次标失败
    assert after["generation_revision"] == 1
    assert after["failure_detail"] == before["failure_detail"]  # 未写诊断
    assert fetch_job(engine, jid)["status"] == "running"  # T12 未提交为 failed


# ------------------------------------------------ Fix 1(c) persistence-free


def test_llm_rag_adapter_is_persistence_free() -> None:
    providers_src = (
        Path(__file__).resolve().parents[1]
        / "src/mvp_worker/handlers/dshared/providers.py"
    ).read_text(encoding="utf-8")
    assert "care_plans" not in providers_src
    assert "sqlalchemy" not in providers_src
    assert "BusinessTx" not in providers_src
    assert "_MARK_PLAN_FAILED" not in providers_src
    assert "text(" not in providers_src


# ------------------------------------------------ Fix 3 config terminal


def test_handler_missing_base_url_terminal_plan_provider_config(
    engine: Engine, monkeypatch: Any
) -> None:
    _aid, pid, jid = _seed_plan_with_raw(engine, _load_raw())
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "llm_rag")
    monkeypatch.delenv("MVP_D_LLM_RAG_BASE_URL", raising=False)
    monkeypatch.setenv("MVP_D_LLM_RAG_API_KEY", API_KEY)

    status, exc, _ = run_claimed(engine, plan_handler, jid, extras={})
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_PROVIDER_CONFIG" and exc.retryable is False

    job = fetch_job(engine, jid)
    assert job["status"] == "failed"
    assert job["last_error"]["code"] == "PLAN_PROVIDER_CONFIG"
    assert int(job["attempt_count"]) == 1  # 仅本次 claim，不耗尽 attempt
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"  # T06 不滞留 waiting_inputs/generating
    assert plan["generation_revision"] == 0
    assert plan["plan_payload"] is None
    assert plan["completed_count"] == 0


def test_handler_missing_api_key_terminal_plan_provider_config(
    engine: Engine, monkeypatch: Any
) -> None:
    _aid, pid, jid = _seed_plan_with_raw(engine, _load_raw())
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "llm_rag")
    monkeypatch.setenv("MVP_D_LLM_RAG_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("MVP_D_LLM_RAG_API_KEY", raising=False)

    status, exc, _ = run_claimed(engine, plan_handler, jid, extras={})
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_PROVIDER_CONFIG" and exc.retryable is False
    assert fetch_plan(engine, pid)["generation_status"] == "failed"


def test_handler_aliyun_llm_stays_retryable(engine: Engine, monkeypatch: Any) -> None:
    """非 llm_rag provider 的解析路径不变：aliyun_llm 未激活 → 可重试。"""
    _aid, _pid, jid = _seed_plan_with_raw(engine, _load_raw())
    monkeypatch.setenv("MVP_D_PLAN_PROVIDER", "aliyun_llm")
    monkeypatch.delenv("MVP_D_ALIYUN_ACTIVATED", raising=False)

    status, exc, _ = run_claimed(engine, plan_handler, jid, extras={})
    assert status == "failed" and exc is not None
    assert exc.code == "DEPENDENCY_UNAVAILABLE" and exc.retryable is True
