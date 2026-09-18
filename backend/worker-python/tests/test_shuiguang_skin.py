"""真实 shuiguang skin 适配器（``dshared.dshuiguang``）的定向测试。

隔离 • 本地 • 合成：临时端口 HTTP stub（精确实现契约形状）+ stdlib 合成 PNG/JPEG
（**无真实人物照**）。覆盖激活门、task_id 派生、暂存、预检、轮询生命周期、
成功体严格校验、V3-only 发布、失败分类、清理与泄漏纪律。
"""
from __future__ import annotations

import json
import logging
import os
import re
import struct
import threading
import uuid
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    fetch_assessment,
    make_ctx,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_source_media,
)
from mvp_worker.handlers import JobFailed
from test_skin_v3_groups import (  # 复用 D-owned helper
    _attach_photo_versions,
    _enqueue_analyze,
    _seed_analysis_case,
)
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.expire import release_claim
from mvp_worker.handlers.dshared.dmedia import load_image_bytes

from mvp_worker.handlers.assessment_analyze import handler as analyze_handler
from mvp_worker.handlers.dshared.dconfig import (
    SHUIGUANG_BASE_URL_ENV,
    SHUIGUANG_INPUT_ROOT_ENV,
    DConfig,
    ProviderConfigError,
)
from mvp_worker.handlers.dshared.dshuiguang import (
    ShuiguangInputViolation,
    ShuiguangScoringReferenceNotReady,
    ShuiguangSkinAdapter,
    ShuiguangStagingError,
    build_shuiguang_skin_port,
    derive_task_id,
)
from mvp_worker.handlers.dshared.dv3 import V3SkinViolation
from mvp_worker.handlers.dshared.providers import (
    FaceDouble,
    ProviderUnavailable,
    SkinAnalysisResult,
    build_skin_port,
)
from mvp_worker.media.storage import FilesystemStorageDouble


# ---------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _clean(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: Any) -> Any:
    for key in (
        "MVP_D_SKIN_PROVIDER",
        SHUIGUANG_BASE_URL_ENV,
        SHUIGUANG_INPUT_ROOT_ENV,
        "MVP_D_SHUIGUANG_CONNECT_TIMEOUT_MS",
        "MVP_D_SHUIGUANG_READ_TIMEOUT_MS",
        "MVP_D_SHUIGUANG_POLL_INTERVAL_SECONDS",
        "MVP_D_SHUIGUANG_POLL_MAX_SECONDS",
        "MVP_ENV",
        "APP_ENV",
        "MVP_NOTIFY_ENV",
        "MVP_WORKER_ENVIRONMENT",
        "SPRING_PROFILES_ACTIVE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def _set_env(
    monkeypatch: Any,
    base_url: str,
    root: Any,
    *,
    interval: int = 1,
    poll_max: int = 120,
    connect: int = 2000,
    read: int = 10000,
) -> DConfig:
    monkeypatch.setenv("MVP_D_SKIN_PROVIDER", "shuiguang")
    monkeypatch.setenv(SHUIGUANG_BASE_URL_ENV, base_url)
    monkeypatch.setenv(SHUIGUANG_INPUT_ROOT_ENV, str(root))
    monkeypatch.setenv("MVP_D_SHUIGUANG_POLL_INTERVAL_SECONDS", str(interval))
    monkeypatch.setenv("MVP_D_SHUIGUANG_POLL_MAX_SECONDS", str(poll_max))
    monkeypatch.setenv("MVP_D_SHUIGUANG_CONNECT_TIMEOUT_MS", str(connect))
    monkeypatch.setenv("MVP_D_SHUIGUANG_READ_TIMEOUT_MS", str(read))
    return DConfig.from_env()


# ---------------------------------------------------------------- synthetic images (stdlib)
def _png(seed: int = 0, size: int = 8) -> bytes:
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            v = (x * 31 + y * 17 + seed * 7) % 256
            raw += bytes((v, (v * 3) % 256, (v * 5) % 256))

    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + typ
            + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _jpeg(seed: int = 0) -> bytes:
    return b"\xff\xd8\xff\xe0" + bytes((seed + i) % 256 for i in range(64))


def _images() -> dict[str, bytes]:
    return {"front": _png(1), "left": _png(2), "right": _png(3)}


def _v3_969() -> dict[str, Any]:
    """真实诊断形状：9/6/9 区域，冻结词表，含一个 null（缺测）区域。"""
    def region(code: str, name: str, score: Any, sev: Any) -> dict[str, Any]:
        return {"region": code, "name": name, "score": score, "severity": sev}

    return {
        "pores": {
            "name": "毛孔", "score": 57.0, "severity": "中度",
            "regions": [region(f"p{i}", "额部", 50.0 + i, "轻度") for i in range(9)],
        },
        "spots": {
            "name": "可见色斑", "score": 42.0, "severity": "中度",
            "regions": [region(f"s{i}", "画面左颧部", 40.0 + i, "中度") for i in range(5)]
            + [region("s5", "画面右面颊", None, None)],  # 缺测 null ≠ 0
        },
        "surface_gloss": {
            "name": "表面油光", "score": 72.0, "severity": "轻度",
            "regions": [region(f"g{i}", "下巴", 100.0, "未见明显") for i in range(9)],
        },
    }


# ---------------------------------------------------------------- stub server
class _Stub:
    def __init__(self) -> None:
        self.score_source = "shuiguang-v1"
        self.submit_override: Optional[tuple[int, Any]] = None
        self.poll_script: Optional[list[tuple[int, Any]]] = None
        self.success_groups: Any = _v3_969()
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []
        self.queue_ids: dict[str, str] = {}
        self.poll_index: dict[str, int] = {}
        self.next_queue = 0


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 静默
        return

    @property
    def stub(self) -> _Stub:
        return self.server.stub  # type: ignore[attr-defined]

    def _send(self, status: int, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> Any:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self) -> None:  # noqa: N802
        body = self._body()
        self.stub.posts.append(body)
        if self.path != "/api/score-jobs":
            self._send(404, {"error": {"code": "INVALID_REQUEST"}})
            return
        if self.stub.submit_override is not None:
            self._send(*self.stub.submit_override)
            return
        task_id = body.get("task_id")
        qid = self.stub.queue_ids.get(task_id)
        if qid is None:
            self.stub.next_queue += 1
            qid = f"q-{self.stub.next_queue}"
            self.stub.queue_ids[task_id] = qid
        self._send(202, {
            "task_id": task_id, "queue_id": qid, "status": "queued",
            "score_source": self.stub.score_source,
        })

    def do_GET(self) -> None:  # noqa: N802
        self.stub.gets.append(self.path)
        qid = self.path.rsplit("/", 1)[1]
        if self.stub.poll_script is None:
            self._send(200, self.stub.success_groups)
            return
        idx = self.stub.poll_index.get(qid, 0)
        self.stub.poll_index[qid] = idx + 1
        entry = self.stub.poll_script[min(idx, len(self.stub.poll_script) - 1)]
        self._send(*entry)


@pytest.fixture
def stub_server() -> Any:
    stub = _Stub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.stub = stub  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _adapter(cfg: DConfig, **kw: Any) -> ShuiguangSkinAdapter:
    kw.setdefault("sleep", lambda _s: None)
    kw.setdefault("clock", lambda: 0.0)
    return ShuiguangSkinAdapter(cfg, **kw)


# ================================================================ 1) 激活门
def test_build_missing_base_url_fails_closed(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("MVP_D_SKIN_PROVIDER", "shuiguang")
    monkeypatch.setenv(SHUIGUANG_INPUT_ROOT_ENV, str(tmp_path))
    with pytest.raises(ProviderConfigError) as ei:
        build_skin_port(DConfig.from_env(), environment="dev")
    assert SHUIGUANG_BASE_URL_ENV in str(ei.value)
    assert str(tmp_path) not in str(ei.value)  # 绝不含取值


def test_build_missing_input_root_fails_closed(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("MVP_D_SKIN_PROVIDER", "shuiguang")
    monkeypatch.setenv(SHUIGUANG_BASE_URL_ENV, "http://127.0.0.1:1")
    with pytest.raises(ProviderConfigError) as ei:
        build_skin_port(DConfig.from_env(), environment="dev")
    assert SHUIGUANG_INPUT_ROOT_ENV in str(ei.value)


def test_build_nonexistent_input_root_fails_closed(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path / "nope")
    with pytest.raises(ProviderConfigError) as ei:
        build_skin_port(cfg, environment="dev")
    assert SHUIGUANG_INPUT_ROOT_ENV in str(ei.value)


def test_build_non_writable_input_root_fails_closed(monkeypatch: Any, tmp_path: Any) -> None:
    root = tmp_path / "ro"
    root.mkdir()
    os.chmod(root, 0o500)
    try:
        cfg = _set_env(monkeypatch, "http://127.0.0.1:1", root)
        with pytest.raises(ProviderConfigError):
            build_skin_port(cfg, environment="dev")
    finally:
        os.chmod(root, 0o700)


def test_build_ok_with_writable_root(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    port = build_skin_port(cfg, environment="dev")
    assert port.provider_name == "shuiguang"


def test_default_provider_still_double(monkeypatch: Any, tmp_path: Any) -> None:
    port = build_skin_port(DConfig.from_env(), environment="dev")
    assert port.provider_name == "double"


# ================================================================ 2) task_id / 暂存
def test_task_id_deterministic_and_charset(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    imgs = _images()
    tid = a._task_id(imgs)
    assert tid == a._task_id(dict(imgs))  # 同字节同 id
    other = dict(imgs)
    other["front"] = _png(99)
    # distinct fixtures → different IDs（碰撞抗性为概率性质，非"异字节必然异 id"）
    assert a._task_id(other) != tid
    assert re.match(r"^[A-Za-z0-9_-]{1,64}$", tid)


def test_staging_atomic_relative_and_mirrored_false(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    imgs = _images()
    tid = a._task_id(imgs)
    rel = a._stage(imgs, tid)
    assert [v for v, _ in rel] == ["front", "left", "right"]
    for view, path in rel:
        assert path == f"{tid}/{view}.png"
        assert not path.startswith("/")  # 相对 INPUT_ROOT
        assert (tmp_path / path).read_bytes() == imgs[view]
    assert not list((tmp_path / tid).glob("*.tmp"))  # 无残留临时文件


# ================================================================ 3) 预检（零 HTTP）
def _preflight_case(monkeypatch: Any, tmp_path: Any, imgs: dict[str, bytes], **kw: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg, **kw)
    calls: list[Any] = []
    a._do_request = lambda *args: calls.append(args) or (202, {})
    with pytest.raises(ShuiguangInputViolation):
        a.analyze(imgs)
    assert calls == []  # 预检失败 → 零 HTTP、零暂存


def test_preflight_oversize(monkeypatch: Any, tmp_path: Any) -> None:
    _preflight_case(monkeypatch, tmp_path, _images(), max_image_bytes=10)


def test_preflight_bad_magic(monkeypatch: Any, tmp_path: Any) -> None:
    imgs = _images()
    imgs["left"] = b"not-an-image" * 4
    _preflight_case(monkeypatch, tmp_path, imgs)


def test_preflight_duplicate_triple(monkeypatch: Any, tmp_path: Any) -> None:
    same = _png(7)
    _preflight_case(monkeypatch, tmp_path, {"front": same, "left": same, "right": same})


def test_preflight_missing_view(monkeypatch: Any, tmp_path: Any) -> None:
    imgs = _images()
    del imgs["right"]
    _preflight_case(monkeypatch, tmp_path, imgs)


# ================================================================ 4) 提交/轮询
def test_submit_malformed_202_variants(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    imgs = _images()
    rel = a._stage(imgs, a._task_id(imgs))
    for bad in (
        (200, {"task_id": "x", "queue_id": "q", "status": "queued", "score_source": "s"}),
        (202, {"task_id": a._task_id(imgs), "queue_id": "", "status": "queued", "score_source": "s"}),
        (202, {"task_id": a._task_id(imgs), "queue_id": "q", "status": "done", "score_source": "s"}),
        (202, {"task_id": a._task_id(imgs), "queue_id": "q", "status": "queued"}),
        (202, "not-a-dict"),
    ):
        a._do_request = lambda *args, _bad=bad: _bad
        with pytest.raises(ProviderUnavailable):
            a._submit(a._task_id(imgs), rel)


def test_poll_lifecycle_success(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    script = [(200, {"queue_id": "q", "status": "pending", "progress": 0}),
              (200, {"queue_id": "q", "status": "started", "progress": 10}),
              (200, {"queue_id": "q", "status": "progress", "progress": 50}),
              (200, _v3_969())]
    idx = {"i": 0}

    def req(method: str, path: str, body: Any) -> tuple[int, Any]:
        entry = script[min(idx["i"], len(script) - 1)]
        idx["i"] += 1
        return entry

    a._do_request = req
    groups = a._poll("q")
    assert set(groups) == {"pores", "spots", "surface_gloss"}


def test_poll_budget_exceeded_is_retryable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path, poll_max=1)
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += 0.4
        return state["t"]

    a = _adapter(cfg, clock=clock)
    a._do_request = lambda *args: (200, {"queue_id": "q", "status": "pending", "progress": 0})
    with pytest.raises(ProviderUnavailable):
        a._poll("q")


def test_poll_malformed_status_body_is_unavailable(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    a._do_request = lambda *args: (200, {"status": "banana"})
    with pytest.raises(ProviderUnavailable):
        a._poll("q")


def test_poll_no_status_non_result_body_is_terminal(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    a._do_request = lambda *args: (200, {"unexpected": True})
    with pytest.raises(V3SkinViolation):
        a._poll("q")


# ================================================================ 5) 失败分类
@pytest.mark.parametrize("code,expected", [
    ("WORKER_FAILED", ProviderUnavailable),
    ("SOMETHING_ELSE", ProviderUnavailable),
    ("lowercase_bad!", ProviderUnavailable),
])
def test_failure_codes_retryable(monkeypatch: Any, tmp_path: Any, code: str, expected: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    a._do_request = lambda *args: (200, {"status": "failed", "error": {"code": code, "message": "x"}})
    with pytest.raises(expected):
        a._poll("q")


def test_scoring_reference_not_ready_is_immediate_terminal(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    a._do_request = lambda *args: (
        200, {"status": "failed", "error": {"code": "SCORING_REFERENCE_NOT_READY", "message": "x"}}
    )
    with pytest.raises(ShuiguangScoringReferenceNotReady):
        a._poll("q")


# ================================================================ 6) 成功体严格校验
@pytest.mark.parametrize("mutate", [
    lambda g: g.update({"extra": 1}),                                  # 额外顶层键
    lambda g: g["pores"].update({"extra": 1}),                        # 额外组键
    lambda g: g["pores"]["regions"][0].update({"extra": 1}),          # 额外区域键
    lambda g: g["pores"].__setitem__("severity", "非常严重"),          # 未知词表
    lambda g: g["pores"].__setitem__("name", "  "),                   # 空白文本
    lambda g: g["pores"]["regions"][0].__setitem__("name", " \t "),   # 空白区域名
    lambda g: g["pores"]["regions"][0].__setitem__("region", "  "),   # 空白 region
    lambda g: g["pores"].__setitem__("regions", []),                  # 空区域数组
    lambda g: g["pores"].__setitem__("score", 101),                   # 越界
    lambda g: g["pores"].__setitem__("score", True),                  # bool
    lambda g: g["pores"].__setitem__("score", "50"),                  # 字符串
    lambda g: g["pores"].__setitem__("score", 10 ** 10000),           # 巨大整数
    lambda g: g["pores"].__setitem__("score", float("inf")),          # inf
    lambda g: g["pores"]["regions"].append(dict(g["pores"]["regions"][0])),  # 重复 region
    lambda g: g["pores"].pop("regions"),                              # 缺键
])
def test_success_body_strict_validation(monkeypatch: Any, tmp_path: Any, mutate: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    groups = _v3_969()
    mutate(groups)
    a._do_request = lambda *args: (200, groups)
    with pytest.raises(V3SkinViolation):
        a._poll("q")


def test_success_969_consumed_as_is(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)
    a._do_request = lambda *args: (200, _v3_969())
    groups = a._poll("q")
    assert len(groups["pores"]["regions"]) == 9  # 不补成 8/不加区
    assert len(groups["spots"]["regions"]) == 6  # 真实 6 区照收
    assert groups["spots"]["regions"][5]["score"] is None  # null 保留 ≠ 0


# ================================================================ 7) 端到端（真 HTTP stub）
def test_end_to_end_success_and_cleanup(monkeypatch: Any, tmp_path: Any, stub_server: Any) -> None:
    stub, url = stub_server
    cfg = _set_env(monkeypatch, url, tmp_path)
    a = ShuiguangSkinAdapter(cfg, sleep=lambda _s: None, clock=lambda: 0.0)
    imgs = _images()
    tid = a._task_id(imgs)
    result = a.analyze(imgs)
    assert result.metrics == [] and result.result_images == [] and result.conclusion == ""
    assert result.model_version == "shuiguang:shuiguang-v1"
    assert result.v3_groups is not None
    assert len(stub.posts) == 1
    body = stub.posts[0]
    assert body["mirrored"] is False
    assert [i["image_id"] for i in body["images"]] == [
        f"{tid}-front", f"{tid}-left", f"{tid}-right"
    ]
    assert [i["path"] for i in body["images"]] == [
        f"{tid}/front.png", f"{tid}/left.png", f"{tid}/right.png"
    ]
    assert not (tmp_path / tid).exists()  # 成功 → 清理


def test_end_to_end_retryable_keeps_staging(monkeypatch: Any, tmp_path: Any, stub_server: Any) -> None:
    stub, url = stub_server
    cfg = _set_env(monkeypatch, url, tmp_path, poll_max=100)
    state = {"t": 0.0, "step": 1000.0}

    def clock() -> float:
        state["t"] += state["step"]
        return state["t"]

    a = ShuiguangSkinAdapter(cfg, sleep=lambda _s: None, clock=clock)
    imgs = _images()
    tid = a._task_id(imgs)
    stub.poll_script = [(200, {"queue_id": "q", "status": "pending", "progress": 0})]
    with pytest.raises(ProviderUnavailable):
        a.analyze(imgs)  # 预算立即超限
    assert (tmp_path / tid / "front.png").exists()  # 可重试 → 保留

    # 幂等重发：同 task_id → 同 queue_id → 续轮询到成功
    state["t"] = 0.0
    state["step"] = 0.0  # 不再施加预算压力
    stub.poll_script = [
        (200, {"queue_id": "q", "status": "pending", "progress": 0}),
        (200, {"queue_id": "q", "status": "started", "progress": 50}),
        (200, _v3_969()),
    ]
    stub.poll_index.clear()
    result = a.analyze(imgs)
    assert result.v3_groups is not None
    assert len(stub.posts) == 2
    assert stub.posts[0]["task_id"] == stub.posts[1]["task_id"]  # 幂等同 id
    assert len(stub.queue_ids) == 1  # 同 queue
    assert not (tmp_path / tid).exists()


def test_end_to_end_terminal_cleans_staging(monkeypatch: Any, tmp_path: Any, stub_server: Any) -> None:
    stub, url = stub_server
    cfg = _set_env(monkeypatch, url, tmp_path)
    stub.poll_script = [(200, {"status": "failed", "error": {"code": "SCORING_REFERENCE_NOT_READY"}})]
    a = ShuiguangSkinAdapter(cfg, sleep=lambda _s: None, clock=lambda: 0.0)
    imgs = _images()
    tid = a._task_id(imgs)
    with pytest.raises(ShuiguangScoringReferenceNotReady):
        a.analyze(imgs)
    assert not (tmp_path / tid).exists()


def test_cleanup_failure_never_breaks_outcome(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)

    def req(method: str, path: str, body: Any) -> tuple[int, Any]:
        if method == "POST":
            return (202, {"task_id": body["task_id"], "queue_id": "q", "status": "queued", "score_source": "s"})
        return (200, _v3_969())

    a._do_request = req

    def boom(_path: Any) -> None:
        raise OSError("cleanup exploded")

    import mvp_worker.handlers.dshared.dshuiguang as mod

    monkeypatch.setattr(mod.shutil, "rmtree", boom)
    result = a.analyze(_images())  # 清理异常被吞，结果照常
    assert result.v3_groups is not None


# ================================================================ 8) 泄漏纪律
def test_no_leak_in_logs_or_chained_exceptions(
    monkeypatch: Any, tmp_path: Any, stub_server: Any, caplog: Any
) -> None:
    stub, url = stub_server
    cfg = _set_env(monkeypatch, url, tmp_path)
    imgs = _images()
    secret = "TOKEN-SECRET-PLACEHOLDER"
    a = ShuiguangSkinAdapter(cfg, sleep=lambda _s: None, clock=lambda: 0.0)
    stub.poll_script = [(200, {"status": "failed", "error": {"code": "WORKER_FAILED", "message": secret}})]
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderUnavailable) as ei:
            a.analyze(imgs)
    chain: list[str] = []
    cur: Any = ei.value
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain.append(str(cur))
        cur = cur.__cause__ or cur.__context__
    text = caplog.text + "\n" + "\n".join(chain)
    for needle in (secret, "front.png", str(tmp_path), url, "q-"):
        assert needle not in text, needle


# ================================================================ 9) handler 集成（真实 PG）
class _StubSkin:
    provider_name = "shuiguang"

    def __init__(self, result: Any = None, exc: Any = None) -> None:
        self._result = result
        self._exc = exc
        self.model_version = "shuiguang:test"
        self.calls = 0

    def analyze(self, images: dict[str, bytes]) -> Any:
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result


def _run_sg(engine: Engine, tmp_path: Any, skin: Any) -> tuple[str, Any, str, dict[str, Any]]:
    ref = str(uuid.uuid4())
    storage, aid = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid,
        extras={"storage": storage, "face_port": face, "skin_port": skin},
    )
    return status, exc, aid, fetch_assessment(engine, aid)


def _sg_result(groups: Any = None, *, metrics: Any = ..., images: Any = ...) -> SkinAnalysisResult:
    return SkinAnalysisResult(
        conclusion="", metrics=[] if metrics is ... else metrics,
        description="", result_images=[] if images is ... else images,
        model_version="shuiguang:test",
        v3_groups=_v3_969() if groups is None else groups,
    )


def test_handler_publish_v3_only(engine: Engine, tmp_path: Any, monkeypatch: Any) -> None:
    _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path / "in")
    (tmp_path / "in").mkdir()
    status, exc, _aid, a = _run_sg(engine, tmp_path, _StubSkin(_sg_result()))
    assert status == "succeeded", (status, exc)
    payload = a["report_payload"]
    assert payload["metrics"] == [] and payload["images"] == []
    assert payload["conclusion"] == "" and payload["description"] == ""
    assert set(payload) >= {"pores", "spots", "surface_gloss"}
    assert payload["model_info"]["skin_provider"] == "shuiguang"
    assert payload["model_info"]["model_version"].startswith("shuiguang:")
    snap = json.dumps(payload)
    assert '"pores"' in snap and '"regions"' in snap


@pytest.mark.parametrize("result", [
    _sg_result(metrics=[{"name": "moisture", "value": 1.0, "unit": "percent"}]),
    _sg_result(groups=None, metrics=[], images=[{"ref": "x", "provider_uri": "y", "caption": "z"}]),
    SkinAnalysisResult(conclusion="", metrics=[], description="", result_images=[],
                      model_version="shuiguang:test", v3_groups=None),
])
def test_handler_v3_only_violations_terminal(
    engine: Engine, tmp_path: Any, monkeypatch: Any, result: Any
) -> None:
    _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path / "in")
    (tmp_path / "in").mkdir()
    status, exc, _aid, a = _run_sg(engine, tmp_path, _StubSkin(result))
    assert status == "failed", (status, exc)
    assert exc is not None and exc.code == "PROVIDER_CONTRACT_VIOLATION"
    assert a["failure_code"] == "PROVIDER_CONTRACT_VIOLATION"
    assert a["report_payload"] is None


@pytest.mark.parametrize("exc,code", [
    (ShuiguangInputViolation("bad input"), "PROVIDER_CONTRACT_VIOLATION"),
    (V3SkinViolation("bad body"), "PROVIDER_CONTRACT_VIOLATION"),
    (ShuiguangScoringReferenceNotReady("not ready"), "SKIN_SCORING_REFERENCE_NOT_READY"),
])
def test_handler_adapter_exception_terminal_codes(
    engine: Engine, tmp_path: Any, monkeypatch: Any, exc: Any, code: str
) -> None:
    _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path / "in")
    (tmp_path / "in").mkdir()
    status, jf, _aid, a = _run_sg(engine, tmp_path, _StubSkin(exc=exc))
    assert status == "failed", (status, jf)
    assert jf is not None and jf.code == code and jf.retryable is False
    assert a["failure_code"] == code


def test_handler_skin_provider_config_immediate_terminal(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    # provider=shuiguang 但缺 BASE_URL/INPUT_ROOT，且**不注入** skin_port → 端口构造失败
    monkeypatch.setenv("MVP_D_SKIN_PROVIDER", "shuiguang")
    ref = str(uuid.uuid4())
    storage, aid = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid, extras={"storage": storage, "face_port": face},
    )
    assert status == "failed", (status, exc)
    assert exc is not None and exc.code == "SKIN_PROVIDER_CONFIG"
    a = fetch_assessment(engine, aid)
    assert a["failure_code"] == "SKIN_PROVIDER_CONFIG"


# ================================================================ 10) 生命周期 / 权限 / 泄漏（Oracle FAIL 修复）
class _StagingStub:
    """模拟适配器暂存后抛可重试错误（handler 语义）。"""

    provider_name = "shuiguang"

    def __init__(self, root: Any) -> None:
        self._root = Path(root)
        self.model_version = "shuiguang:test"

    def analyze(self, images: dict[str, bytes]) -> Any:
        tid = derive_task_id(images)
        d = self._root / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / "front.png").write_bytes(images["front"])
        raise ProviderUnavailable("injected retryable skin failure")


def _enqueue_ma(engine: Engine, aid: str, rev: int, max_attempts: int) -> str:
    jid, _ = enqueue(
        engine, job_type="assessment.analyze", dedup_key=f"assessment:{aid}:{rev}",
        owner_type="assessment", owner_id=aid, input_revision=rev,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": str(rev)},
        max_attempts=max_attempts,
    )
    return jid


def _seed_bits(engine: Engine, tmp_path: Any, *, rev: int = 2) -> tuple[Any, str, str, Any]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=rev)
    refs = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    # 用**互不相同且合法**的合成 PNG 覆盖三视图（seed 默认同字节 → 会被去重预检拒绝）。
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id::text AS id, object_key FROM media_objects"
                " WHERE assessment_id = CAST(:a AS uuid) AND photo_version = 1"
            ),
            {"a": aid},
        ).mappings().all()
    key_by_ref = {r["id"]: r["object_key"] for r in rows}
    for view, data in (("front", _png(1)), ("left", _png(2)), ("right", _png(3))):
        storage.put(key_by_ref[refs[view]], data)
    _attach_photo_versions(engine, aid, 1, refs)
    ref = str(uuid.uuid4())
    seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    images = load_image_bytes(engine, storage, refs)
    assert isinstance(images, dict)
    return storage, aid, ref, images


def _handle_once(
    engine: Engine, job_id: str, *, extras: dict[str, Any], abort: bool = False
) -> tuple[Any, Any]:
    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=50)
    claim = next(c for c in claims if c.id == job_id)
    for other in claims:
        if other.id != job_id:
            release_claim(engine, other, worker_id="w-d")
    analyze_handler.validate(claim.payload)
    ctx = make_ctx(engine, claim, extras=extras)
    if abort:
        ctx.abort_event.set()
    exc = None
    try:
        analyze_handler.handle(ctx, claim)
    except JobFailed as e:  # noqa: F821
        exc = e
    return claim, exc


def _chain_text(exc: Any) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(str(cur))
        parts.append(repr(cur))
        cur = cur.__cause__ or cur.__context__
    return "\n".join(parts)


def test_staging_error_sanitized_direct(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    imgs = _images()
    tid = derive_task_id(imgs)
    (tmp_path / tid).write_text("precreated file blocks staging")
    a = _adapter(cfg)
    with pytest.raises(ShuiguangStagingError) as ei:
        a.analyze(imgs)
    assert isinstance(ei.value, ProviderUnavailable)  # 可重试类别
    text = _chain_text(ei.value)
    for needle in (str(tmp_path), tid, ".tmp", "front.png"):
        assert needle not in text, needle


def test_staging_error_through_handler_sanitized(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    root = tmp_path / "in"
    root.mkdir()
    _set_env(monkeypatch, "http://127.0.0.1:1", root)
    storage, aid, ref, images = _seed_bits(engine, tmp_path)
    tid = derive_task_id(images)
    (root / tid).write_text("precreated file blocks staging")
    jid = _enqueue_ma(engine, aid, 2, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    real = build_shuiguang_skin_port(DConfig.from_env())  # 预检/暂存真实路径（零网络）
    _claim, exc = _handle_once(
        engine, jid, extras={"storage": storage, "face_port": face, "skin_port": real}
    )
    assert exc is not None and exc.retryable is True
    text = _chain_text(exc)
    for needle in (str(root), tid, ".tmp", "front.png"):
        assert needle not in text, needle


def test_final_attempt_exhaustion_keeps_staged_disclosed_orphan(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    root = tmp_path / "in"
    root.mkdir()
    _set_env(monkeypatch, "http://127.0.0.1:1", root)
    storage, aid, ref, images = _seed_bits(engine, tmp_path)
    tid = derive_task_id(images)
    jid = _enqueue_ma(engine, aid, 2, 1)  # 首次即最终尝试
    face = FaceDouble(search="matched", face_subject_ref=ref)
    _claim, exc = _handle_once(
        engine, jid, extras={"storage": storage, "face_port": face, "skin_port": _StagingStub(root)}
    )
    assert exc is not None and exc.retryable is False
    # 推断式补偿删除已移除：终态残留属**已披露孤儿**，延后到激活前置的 ops 机制。
    assert (root / tid / "front.png").exists()


def test_retryable_non_final_keeps_staged(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    root = tmp_path / "in"
    root.mkdir()
    _set_env(monkeypatch, "http://127.0.0.1:1", root)
    storage, aid, ref, images = _seed_bits(engine, tmp_path)
    tid = derive_task_id(images)
    jid = _enqueue_ma(engine, aid, 2, 3)  # 非最终
    face = FaceDouble(search="matched", face_subject_ref=ref)
    _claim, exc = _handle_once(
        engine, jid, extras={"storage": storage, "face_port": face, "skin_port": _StagingStub(root)}
    )
    assert exc is not None and exc.retryable is True
    assert (root / tid / "front.png").exists()  # 可重试 → 保留（勿回归）


def test_stale_supersession_deletes_neither_old_nor_new(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """真·照片版本换代：旧=A 内容、新=B 内容。作废退出**不得删任何一方**。

    这是针对 367bd14 破坏性行为的判别性测试：旧实现会误删**当前 B** 且漏掉旧 A。
    """
    root = tmp_path / "in"
    root.mkdir()
    _set_env(monkeypatch, "http://127.0.0.1:1", root)
    storage, aid, ref, images_a = _seed_bits(engine, tmp_path, rev=2)  # pv=1 content A
    tid_a = derive_task_id(images_a)
    (root / tid_a).mkdir(parents=True)
    (root / tid_a / "front.png").write_bytes(images_a["front"])
    # 换代：current_photo_version 1 → 2，内容 B 不同字节
    refs_b = seed_source_media(engine, storage, assessment_id=aid, photo_version=2)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id::text AS id, object_key FROM media_objects"
                " WHERE assessment_id = CAST(:a AS uuid) AND photo_version = 2"
            ),
            {"a": aid},
        ).mappings().all()
    key_by_ref = {r["id"]: r["object_key"] for r in rows}
    for view, data in (("front", _png(11)), ("left", _png(12)), ("right", _png(13))):
        storage.put(key_by_ref[refs_b[view]], data)
    _attach_photo_versions(engine, aid, 2, refs_b)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE skin_assessments SET current_photo_version = 2 WHERE id = CAST(:a AS uuid)"),
            {"a": aid},
        )
    images_b = load_image_bytes(engine, storage, refs_b)
    assert isinstance(images_b, dict)
    tid_b = derive_task_id(images_b)
    assert tid_a != tid_b
    (root / tid_b).mkdir(parents=True)
    (root / tid_b / "front.png").write_bytes(images_b["front"])
    jid = _enqueue_ma(engine, aid, 99, 5)  # rev != row.revision(2) → 旧代次作废
    face = FaceDouble(search="matched", face_subject_ref=ref)
    _claim, exc = _handle_once(
        engine, jid,
        extras={"storage": storage, "face_port": face, "skin_port": _StubSkin(_sg_result())},
    )
    assert exc is None  # 作废=成功
    assert (root / tid_a / "front.png").exists()  # 旧孤儿**不再被推断删除**
    assert (root / tid_b / "front.png").exists()  # 新活跃目录**绝不被删除**（判别点）


def test_abort_exit_keeps_staged(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    root = tmp_path / "in"
    root.mkdir()
    _set_env(monkeypatch, "http://127.0.0.1:1", root)
    storage, aid, ref, images = _seed_bits(engine, tmp_path)
    tid = derive_task_id(images)
    (root / tid).mkdir(parents=True)
    (root / tid / "front.png").write_bytes(images["front"])
    jid = _enqueue_ma(engine, aid, 2, 5)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    _claim, exc = _handle_once(
        engine, jid,
        extras={"storage": storage, "face_port": face, "skin_port": _StubSkin(_sg_result())},
        abort=True,
    )
    assert exc is None  # 协作中止（常见于租约丢失：他人可能已在用该目录）
    assert (root / tid / "front.png").exists()  # 不删（所有权不安全）


def test_cleanup_failure_warning_fires_without_leaks(
    monkeypatch: Any, tmp_path: Any, caplog: Any
) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    a = _adapter(cfg)

    def req(method: str, path: str, body: Any) -> tuple[int, Any]:
        if method == "POST":
            return (202, {"task_id": body["task_id"], "queue_id": "q", "status": "queued", "score_source": "s"})
        return (200, _v3_969())

    a._do_request = req
    imgs = _images()

    import mvp_worker.handlers.dshared.dshuiguang as mod

    def boom(_path: Any, **_kw: Any) -> None:
        raise OSError("rmtree denied")

    monkeypatch.setattr(mod.shutil, "rmtree", boom)
    with caplog.at_level(logging.WARNING):
        result = a.analyze(imgs)
    assert result.v3_groups is not None  # 清理失败不影响结果
    assert "staged_cleanup_failed" in caplog.text  # 失败可观测（此前被 ignore_errors 吞掉）
    for needle in (str(tmp_path), str(tmp_path), "http://", "front.png"):
        assert needle not in caplog.text


def test_stage_permissions_immune_to_umask(monkeypatch: Any, tmp_path: Any) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    imgs = _images()
    old = os.umask(0o000)
    try:
        a = _adapter(cfg)
        tid = a._task_id(imgs)
        a._stage(imgs, tid)
        d = tmp_path / tid
        assert oct(d.stat().st_mode & 0o777) == oct(0o700)
        for f in d.iterdir():
            assert oct(f.stat().st_mode & 0o777) == oct(0o600)
    finally:
        os.umask(old)


def test_partial_staging_failure_removes_temps_keeps_targets(
    monkeypatch: Any, tmp_path: Any
) -> None:
    cfg = _set_env(monkeypatch, "http://127.0.0.1:1", tmp_path)
    imgs = _images()
    tid = derive_task_id(imgs)
    job_dir = tmp_path / tid
    job_dir.mkdir()
    (job_dir / "front.png").write_bytes(imgs["front"])  # 上一尝试目标（同 task_id 同字节）
    (job_dir / "left.png").write_bytes(imgs["left"])

    import mvp_worker.handlers.dshared.dshuiguang as mod

    real_open = os.open
    calls = {"n": 0}

    def flaky_open(path: Any, flags: int, mode: int = 0o777) -> int:
        calls["n"] += 1
        if calls["n"] == 2:  # 第二个临时文件写入失败
            raise OSError("disk full")
        return real_open(path, flags, mode)

    monkeypatch.setattr(mod.os, "open", flaky_open)
    a = _adapter(cfg)
    with pytest.raises(ShuiguangStagingError) as ei:
        a._stage(imgs, tid)
    assert str(tmp_path) not in _chain_text(ei.value)
    assert (job_dir / "front.png").read_bytes() == imgs["front"]
    assert (job_dir / "left.png").read_bytes() == imgs["left"]  # 既有 target 未被删
    assert not list(job_dir.glob("*.tmp"))  # 本次临时文件已清


def test_repr_redacts_shuiguang_values(monkeypatch: Any, tmp_path: Any) -> None:
    sentinel_url = "http://sentinel-host.invalid:9999"
    sentinel_root = str(tmp_path / "sentinel-root")
    cfg = _set_env(monkeypatch, sentinel_url, sentinel_root)
    monkeypatch.setenv("MVP_D_FACE_SERVICE_TOKEN_FILE", "/x/secret.token")
    cfg = DConfig.from_env()
    text = repr(cfg)
    assert sentinel_url not in text
    assert sentinel_root not in text
    assert "secret.token" not in text  # 既有脱敏仍生效
