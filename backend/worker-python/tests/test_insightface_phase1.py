# -*- coding: utf-8 -*-
"""D 包 phase 1：insightface/face-service 绑定的**纯单元**测试（零 live service、零合同绑定）。

覆盖（对应任务书 §6，并按 2026-09-16 监督更正收缩）：

1. token 文件安全读取矩阵（0600 通过 / 0644/0640/0700/0777/0400 拒绝 / 缺失 / 目录 /
   空 / 纯空白 / 只剥一个结尾换行 / 取值绝不出现在异常文本与 caplog）；
2. 配置解析（默认值、严格整数、严格浮点、非法值 fail fast 且消息只含键名）；
3. ``build_face_port`` 选择矩阵（double / insightface / aliyun_face / unknown）；
4. 生产信号 fail-closed（insightface 是真实 provider；替身在生产信号下被拒；
   insightface + 替身旋钮**绝不**回退 double）；
5. 适配器未绑定行为（5 个操作各抛类型化 :class:`FaceServiceNotBound`；分类可重试；
   零 transport 调用）；
6. ``resolve.face_port_for`` 既有分类路径（配置错误 → 可重试 DEPENDENCY_UNAVAILABLE）；
7. 传输替身 + **通用**错误分类矩阵（只依赖通用 HTTP 语义与调用方声明的 ``retryable``）；
8. 活体策略（永不请求 ``require_liveness``；``supported=false`` 不是失败；永不 "passed"）；
9. **非合同守卫**：断言本阶段没有引入任何 per-code/路由/状态码绑定（防回归到过早绑定）。

DB：本文件不读写任何业务表（conftest 的 autouse 清表 fixture 与本文件无耦合）。
"""
from __future__ import annotations

import inspect
import logging
import os
import stat
from types import SimpleNamespace
from typing import Any

import pytest

from mvp_worker.handlers import JobFailed
from mvp_worker.handlers.dshared import dliveness, dtokenfile, dtransport
from mvp_worker.handlers.dshared.dconfig import (
    BOOL_ENV_DOMAIN,
    DEFAULT_FACE_SERVICE_CONNECT_TIMEOUT_MS,
    DEFAULT_FACE_SERVICE_QUALITY_MIN_BBOX_RATIO,
    DEFAULT_FACE_SERVICE_QUALITY_MIN_DET_SCORE,
    DEFAULT_FACE_SERVICE_READ_TIMEOUT_MS,
    DEFAULT_FACE_SERVICE_SEARCH_THRESHOLD,
    DEFAULT_FACE_SERVICE_VERIFY_THRESHOLD,
    DConfig,
    FACE_PROVIDERS,
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_QUALITY_MIN_BBOX_RATIO_ENV,
    FACE_SERVICE_QUALITY_MIN_DET_SCORE_ENV,
    FACE_SERVICE_READ_TIMEOUT_MS_ENV,
    FACE_SERVICE_SEARCH_THRESHOLD_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    FACE_SERVICE_VERIFY_THRESHOLD_ENV,
    ProviderConfigError,
    assert_no_double_injection_in_production,
    double_injection_overrides,
)
from mvp_worker.handlers.dshared.dtokenfile import TokenFileError, read_token_file
from mvp_worker.handlers.dshared.dtransport import (
    FakeTransport,
    FaceServiceAuthConfigError,
    FaceServiceDependencyError,
    FaceServiceTerminalError,
    SealedHttpTransport,
    TransportErrorClass,
    TransportResult,
    classify_face_error_body,
    classify_face_response,
    error_code_from_body,
    raise_for_face_response,
)
from mvp_worker.handlers.dshared.providers import (
    AliyunFaceAdapter,
    FaceDouble,
    FacePort,
    FaceServiceNotBound,
    InsightFaceAdapter,
    ProviderUnavailable,
    build_face_port,
)
from mvp_worker.handlers.dshared.resolve import face_port_for

# 占位 token（**绝不**是真实凭据）。
TOKEN = "TEST-TOKEN-PLACEHOLDER"

_FACE_SERVICE_ENVS = (
    "MVP_D_FACE_PROVIDER",
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV,
    FACE_SERVICE_READ_TIMEOUT_MS_ENV,
    FACE_SERVICE_QUALITY_MIN_DET_SCORE_ENV,
    FACE_SERVICE_QUALITY_MIN_BBOX_RATIO_ENV,
    FACE_SERVICE_VERIFY_THRESHOLD_ENV,
    FACE_SERVICE_SEARCH_THRESHOLD_ENV,
)

_PRODUCTION_SIGNAL_ENVS = (
    "APP_ENV",
    "MVP_NOTIFY_ENV",
    "MVP_WORKER_ENVIRONMENT",
    "SPRING_PROFILES_ACTIVE",
)

_DOUBLE_INJECTION_ENVS = (
    "MVP_D_FACE_DOUBLE_QUALITY",
    "MVP_D_FACE_DOUBLE_REQUIRED_VIEWS",
    "MVP_D_FACE_DOUBLE_SAME_PERSON",
    "MVP_D_FACE_DOUBLE_SEARCH",
)


@pytest.fixture(autouse=True)
def _clean_face_service_env(monkeypatch: Any) -> None:
    """每个测试从"未配置 insightface + 无生产信号 + 无替身注入"起步。"""
    for name in _FACE_SERVICE_ENVS + _PRODUCTION_SIGNAL_ENVS + _DOUBLE_INJECTION_ENVS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------- helpers


def _write_token_file(
    tmp_path: Any, *, content: str = TOKEN, mode: int = 0o600, name: str = "token"
) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)
    return str(path)


def _set_insightface_env(
    monkeypatch: Any, tmp_path: Any, *, token_content: str = TOKEN, mode: int = 0o600
) -> str:
    """配置一套**合法**的 insightface env（token 文件 0600）；返回 token 路径。"""
    token_path = _write_token_file(tmp_path, content=token_content, mode=mode)
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, "http://127.0.0.1:1")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, "mvp-ns-1")
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, token_path)
    return token_path


def _ctx_stub(environment: str = "dev") -> Any:
    """``face_port_for`` 只读 ``extras``/``config.environment``；无需 engine/job/DB。"""
    return SimpleNamespace(extras={}, config=SimpleNamespace(environment=environment))


# ================================================================ 1) token 文件


def test_token_file_0600_returns_value(tmp_path: Any) -> None:
    path = _write_token_file(tmp_path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert read_token_file(path) == TOKEN


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o700, 0o777, 0o400, 0o660, 0o666])
def test_token_file_rejects_non_0600_permissions(tmp_path: Any, mode: int) -> None:
    """权限必须**精确** 0600；任何 group/other/额外 owner 位都 fail-closed。"""
    path = _write_token_file(tmp_path, mode=mode)
    with pytest.raises(TokenFileError) as ei:
        read_token_file(path)
    message = str(ei.value)
    assert FACE_SERVICE_TOKEN_FILE_ENV in message
    assert "0600" in message
    assert oct(mode) in message
    # 绝密卫生：取值绝不进异常文本。
    assert TOKEN not in message
    assert isinstance(ei.value, ProviderConfigError)


def test_token_file_missing_path_rejected(tmp_path: Any) -> None:
    path = str(tmp_path / "does-not-exist")
    with pytest.raises(TokenFileError) as ei:
        read_token_file(path)
    assert FACE_SERVICE_TOKEN_FILE_ENV in str(ei.value)
    assert TOKEN not in str(ei.value)


def test_token_file_unset_rejected() -> None:
    with pytest.raises(TokenFileError) as ei:
        read_token_file("")
    assert FACE_SERVICE_TOKEN_FILE_ENV in str(ei.value)


def test_token_file_directory_rejected(tmp_path: Any) -> None:
    directory = tmp_path / "a-directory"
    directory.mkdir()
    os.chmod(directory, 0o600)
    with pytest.raises(TokenFileError) as ei:
        read_token_file(str(directory))
    assert "regular file" in str(ei.value)


@pytest.mark.parametrize("content", ["", "   ", "\n", "\t \n  "])
def test_token_file_empty_or_whitespace_rejected(tmp_path: Any, content: str) -> None:
    path = _write_token_file(tmp_path, content=content)
    with pytest.raises(TokenFileError) as ei:
        read_token_file(path)
    assert "empty" in str(ei.value)
    assert TOKEN not in str(ei.value)


@pytest.mark.parametrize(
    "content,expected",
    [
        (TOKEN + "\n", TOKEN),
        (TOKEN + "\r\n", TOKEN),
        (TOKEN, TOKEN),
        # 只剥**一个**结尾换行：第二个换行属于 token 值，保留。
        (TOKEN + "\n\n", TOKEN + "\n"),
        ("  " + TOKEN + "  \n", "  " + TOKEN + "  "),
    ],
)
def test_token_file_strips_exactly_one_trailing_newline(
    tmp_path: Any, content: str, expected: str
) -> None:
    path = _write_token_file(tmp_path, content=content)
    assert read_token_file(path) == expected


def test_token_value_never_in_exception_text_or_logs(
    tmp_path: Any, caplog: Any
) -> None:
    """拒绝路径（权限/内容）与成功路径都不泄漏取值到异常文本或日志。"""
    bad_path = _write_token_file(tmp_path, mode=0o644, name="bad")
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(TokenFileError) as ei:
            read_token_file(bad_path)
        read_token_file(_write_token_file(tmp_path, name="good"))
    assert TOKEN not in str(ei.value)
    assert TOKEN not in caplog.text
    for record in caplog.records:
        assert TOKEN not in record.getMessage()


def test_token_file_error_is_config_error_subtype() -> None:
    """token 错误复用既有配置错误类型（既有 face 工厂路径据此分类）。"""
    assert issubclass(TokenFileError, ProviderConfigError)


# ================================================================ 2) 配置解析


def test_face_service_config_defaults_are_conservative() -> None:
    cfg = DConfig.from_env()
    assert cfg.face_provider == "double"
    assert cfg.face_service_base_url == ""
    assert cfg.face_service_namespace == ""
    assert cfg.face_service_token_file == ""
    assert cfg.face_service_connect_timeout_ms == DEFAULT_FACE_SERVICE_CONNECT_TIMEOUT_MS
    assert cfg.face_service_read_timeout_ms == DEFAULT_FACE_SERVICE_READ_TIMEOUT_MS
    assert cfg.face_service_quality_min_det_score == DEFAULT_FACE_SERVICE_QUALITY_MIN_DET_SCORE
    assert (
        cfg.face_service_quality_min_bbox_ratio
        == DEFAULT_FACE_SERVICE_QUALITY_MIN_BBOX_RATIO
    )
    assert cfg.face_service_verify_threshold == DEFAULT_FACE_SERVICE_VERIFY_THRESHOLD
    assert cfg.face_service_search_threshold == DEFAULT_FACE_SERVICE_SEARCH_THRESHOLD
    # search 阈值存在但 phase 2 前未被任何实现读取（见下方非合同守卫）。
    assert DEFAULT_FACE_SERVICE_SEARCH_THRESHOLD == 0.0


def test_face_service_config_explicit_values(monkeypatch: Any, tmp_path: Any) -> None:
    token_path = _write_token_file(tmp_path)
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, "http://127.0.0.1:8010")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, "ns-x")
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, token_path)
    monkeypatch.setenv(FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV, "1500")
    monkeypatch.setenv(FACE_SERVICE_READ_TIMEOUT_MS_ENV, "4500")
    monkeypatch.setenv(FACE_SERVICE_QUALITY_MIN_DET_SCORE_ENV, "0.5")
    monkeypatch.setenv(FACE_SERVICE_QUALITY_MIN_BBOX_RATIO_ENV, "0.02")
    monkeypatch.setenv(FACE_SERVICE_VERIFY_THRESHOLD_ENV, "0.42")
    monkeypatch.setenv(FACE_SERVICE_SEARCH_THRESHOLD_ENV, "0.35")
    cfg = DConfig.from_env()
    assert cfg.face_service_base_url == "http://127.0.0.1:8010"
    assert cfg.face_service_namespace == "ns-x"
    assert cfg.face_service_token_file == token_path
    assert cfg.face_service_connect_timeout_ms == 1500
    assert cfg.face_service_read_timeout_ms == 4500
    assert cfg.face_service_quality_min_det_score == 0.5
    assert cfg.face_service_quality_min_bbox_ratio == 0.02
    assert cfg.face_service_verify_threshold == 0.42
    assert cfg.face_service_search_threshold == 0.35


def test_face_service_config_repr_redacts_token_path(
    monkeypatch: Any, tmp_path: Any
) -> None:
    token_path = _set_insightface_env(monkeypatch, tmp_path)
    text = repr(DConfig.from_env())
    assert "face_service_token_file='<redacted>'" in text
    assert token_path not in text
    assert TOKEN not in text


@pytest.mark.parametrize(
    "env_name,bad_value",
    [
        (FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV, "abc"),
        (FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV, "0"),
        (FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV, "-5"),
        (FACE_SERVICE_READ_TIMEOUT_MS_ENV, "1.5"),
        (FACE_SERVICE_READ_TIMEOUT_MS_ENV, "0"),
    ],
)
def test_face_service_timeout_strict_int_fail_fast(
    monkeypatch: Any, env_name: str, bad_value: str
) -> None:
    monkeypatch.setenv(env_name, bad_value)
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    assert env_name in str(ei.value)


@pytest.mark.parametrize(
    "env_name,bad_value",
    [
        (FACE_SERVICE_QUALITY_MIN_DET_SCORE_ENV, "abc"),
        (FACE_SERVICE_QUALITY_MIN_DET_SCORE_ENV, "1.5"),
        (FACE_SERVICE_QUALITY_MIN_DET_SCORE_ENV, "-0.1"),
        (FACE_SERVICE_QUALITY_MIN_BBOX_RATIO_ENV, "2"),
        (FACE_SERVICE_VERIFY_THRESHOLD_ENV, "not-a-number"),
        (FACE_SERVICE_VERIFY_THRESHOLD_ENV, "1.01"),
        (FACE_SERVICE_SEARCH_THRESHOLD_ENV, "-1"),
    ],
)
def test_face_service_threshold_strict_float_fail_fast(
    monkeypatch: Any, env_name: str, bad_value: str
) -> None:
    monkeypatch.setenv(env_name, bad_value)
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    message = str(ei.value)
    assert env_name in message
    assert bad_value in message


def test_insightface_is_registered_face_provider() -> None:
    assert "insightface" in FACE_PROVIDERS
    assert FACE_PROVIDERS == ("double", "aliyun_face", "insightface")


# ================================================================ 3) 工厂选择矩阵


def test_build_face_port_double_dev(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "double")
    port = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(port, FaceDouble)
    assert port.provider_name == "double"


def test_build_face_port_aliyun_face_unchanged(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "aliyun_face")
    port = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(port, AliyunFaceAdapter)
    # 既有语义不变：未激活即拒绝（不伪造结果）。
    with pytest.raises(ProviderUnavailable):
        port.quality({"front": b"x"})


def test_build_face_port_insightface(monkeypatch: Any, tmp_path: Any) -> None:
    _set_insightface_env(monkeypatch, tmp_path)
    port = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(port, InsightFaceAdapter)
    assert isinstance(port, FacePort)
    assert port.provider_name == "insightface"


def test_build_face_port_unknown_provider_fail_fast(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "bogus")
    with pytest.raises(ProviderConfigError) as ei:
        build_face_port(DConfig.from_env(), environment="dev")
    assert "unknown face provider" in str(ei.value)
    assert "bogus" in str(ei.value)


@pytest.mark.parametrize(
    "missing_env,expected_key",
    [
        (FACE_SERVICE_BASE_URL_ENV, FACE_SERVICE_BASE_URL_ENV),
        (FACE_SERVICE_NAMESPACE_ENV, FACE_SERVICE_NAMESPACE_ENV),
        (FACE_SERVICE_TOKEN_FILE_ENV, FACE_SERVICE_TOKEN_FILE_ENV),
    ],
)
def test_build_face_port_insightface_missing_config_names_key_only(
    monkeypatch: Any, tmp_path: Any, missing_env: str, expected_key: str
) -> None:
    """insightface 必填项缺失 → 构建期 fail fast，消息只含**键名**。"""
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.delenv(missing_env)
    with pytest.raises(ProviderConfigError) as ei:
        build_face_port(DConfig.from_env(), environment="dev")
    message = str(ei.value)
    assert expected_key in message
    assert TOKEN not in message


def test_build_face_port_insightface_bad_token_file_fails(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """token 文件权限不合规 → 构建期 fail-closed，且不回退 double。"""
    _set_insightface_env(monkeypatch, tmp_path, mode=0o644)
    with pytest.raises(ProviderConfigError) as ei:
        build_face_port(DConfig.from_env(), environment="dev")
    assert "0600" in str(ei.value)
    assert TOKEN not in str(ei.value)


# ================================================================ 4) 生产信号 fail-closed


def test_production_refuses_face_double(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "double")
    with pytest.raises(ProviderConfigError):
        build_face_port(DConfig.from_env(), environment="production")


@pytest.mark.parametrize(
    "prod_env",
    [
        {"APP_ENV": "production"},
        {"MVP_WORKER_ENVIRONMENT": "prod"},
        {"MVP_NOTIFY_ENV": "production"},
        {"APP_ENV": "dev", "SPRING_PROFILES_ACTIVE": "prod,dev"},
        {"MVP_NOTIFY_ENV": "dev", "APP_ENV": "production"},
    ],
)
def test_production_signals_refuse_face_double_even_with_dev_environment(
    monkeypatch: Any, prod_env: dict[str, str]
) -> None:
    """替身只在 dev/test：任何生产信号命中都拒绝（对齐 storage 守卫语义）。"""
    for key, value in prod_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "double")
    with pytest.raises(ProviderConfigError) as ei:
        build_face_port(DConfig.from_env(), environment="dev")
    assert "forbidden in production" in str(ei.value)


def test_production_allows_insightface_real_provider(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """insightface 是真实 provider：生产允许构造，且绝不构造替身。"""
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    port = build_face_port(DConfig.from_env(), environment="production")
    assert isinstance(port, InsightFaceAdapter)
    assert not isinstance(port, FaceDouble)


def test_production_insightface_service_failure_is_retryable_not_double(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """生产 + insightface + 服务失败 → 可重试 fail-closed（NO double fallback）。"""
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    port = build_face_port(DConfig.from_env(), environment="production")
    with pytest.raises(FaceServiceNotBound) as ei:
        port.search_1n("mvp-ns-1", {"front": b"x"})
    assert isinstance(ei.value, ProviderUnavailable)
    assert "double" not in str(ei.value).lower().replace("no double fallback", "")


def test_insightface_never_falls_back_to_double_even_with_double_knobs(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """替身旋钮被显式设置也不影响 insightface 解析（无回退路径）。"""
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SEARCH", "matched")
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_QUALITY", "accepted")
    port = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(port, InsightFaceAdapter)
    with pytest.raises(FaceServiceNotBound):
        port.search_1n("mvp-ns-1", {"front": b"x"})


def test_production_with_insightface_and_injection_switch_refused(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """生产 + insightface + 替身注入开关 → 既有生产守卫拒绝启动（不复用为新回退）。"""
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SEARCH", "matched")
    assert double_injection_overrides()
    with pytest.raises(ProviderConfigError) as ei:
        assert_no_double_injection_in_production()
    assert "MVP_D_FACE_DOUBLE_SEARCH" in str(ei.value)


def test_dev_with_insightface_and_defaults_passes_injection_guard(
    monkeypatch: Any, tmp_path: Any
) -> None:
    _set_insightface_env(monkeypatch, tmp_path)
    assert double_injection_overrides() == {}
    assert_no_double_injection_in_production()  # 不抛
    assert isinstance(build_face_port(DConfig.from_env(), environment="dev"), InsightFaceAdapter)


def test_strict_bool_domain_message_mentions_allowed_values(monkeypatch: Any) -> None:
    """既有严格布尔语义未被本批改动破坏（回归锚点）。"""
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SAME_PERSON", "maybe")
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    assert BOOL_ENV_DOMAIN in str(ei.value)


# ================================================================ 5) 适配器未绑定


def _call_all_face_ops(port: Any) -> list[tuple[str, Any]]:
    """按 FacePort 面调用全部 5 个操作，返回 (op, exception) 列表。"""
    calls: list[tuple[str, Any]] = []
    images = {"front": b"x", "left": b"y", "right": b"z"}
    for name, thunk in (
        ("quality", lambda: port.quality(images)),
        ("same_person", lambda: port.same_person(images)),
        ("search_1n", lambda: port.search_1n("mvp-ns-1", images)),
        (
            "register_person",
            lambda: port.register_person("mvp-ns-1", "entity-1", images, "corr-1", "req-1"),
        ),
        (
            "query_registration",
            lambda: port.query_registration(
                "corr-1", "req-1", namespace="mvp-ns-1", entity_id="entity-1"
            ),
        ),
    ):
        with pytest.raises(FaceServiceNotBound) as ei:
            thunk()
        calls.append((name, ei.value))
    return calls


def test_insightface_adapter_all_ops_raise_typed_not_bound(
    monkeypatch: Any, tmp_path: Any
) -> None:
    _set_insightface_env(monkeypatch, tmp_path)
    port = build_face_port(DConfig.from_env(), environment="dev")
    raised = _call_all_face_ops(port)
    assert [name for name, _ in raised] == [
        "quality",
        "same_person",
        "search_1n",
        "register_person",
        "query_registration",
    ]
    for name, exc in raised:
        # 既有 handler 的 ``except ProviderUnavailable`` → 可重试 DEPENDENCY_UNAVAILABLE。
        assert isinstance(exc, ProviderUnavailable), name
        assert name in str(exc)
        assert TOKEN not in str(exc)


def test_insightface_adapter_not_bound_performs_zero_network() -> None:
    """注入内存替身传输：任何操作都**不触碰** transport（零网络、零副作用）。"""
    fake = FakeTransport()
    cfg = DConfig.from_env()
    port = InsightFaceAdapter(cfg, fake)
    _call_all_face_ops(port)
    assert fake.calls == []


def test_insightface_adapter_message_never_claims_success() -> None:
    fake = FakeTransport()
    port = InsightFaceAdapter(DConfig.from_env(), fake)
    with pytest.raises(FaceServiceNotBound) as ei:
        port.quality({"front": b"x"})
    message = str(ei.value).lower()
    assert "not bound" in message
    assert "phase 2" in message
    for forbidden in ("succeeded", "matched", "accepted", "registered"):
        assert forbidden not in message


def test_face_service_not_bound_is_retryable_classification() -> None:
    """类型层级即分类证据：NotBound ⊂ ProviderUnavailable（既有可重试路径）。"""
    assert issubclass(FaceServiceNotBound, ProviderUnavailable)
    assert issubclass(ProviderUnavailable, RuntimeError)
    exc = FaceServiceNotBound("insightface not bound")
    assert isinstance(exc, ProviderUnavailable)


# ================================================================ 6) resolve 分类


def test_face_port_for_maps_insightface_config_error_to_retryable(monkeypatch: Any) -> None:
    """既有 ``face_port_for`` 路径：配置错误 → 可重试 DEPENDENCY_UNAVAILABLE。"""
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
    # 三项必填全缺 → 底层配置错误只报键名（外层按既有语义包成可重试失败）。
    with pytest.raises(JobFailed) as ei:
        face_port_for(_ctx_stub("dev"))
    failure = ei.value
    assert failure.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.retryable is True
    cause = failure.__cause__
    assert isinstance(cause, ProviderConfigError)
    cause_message = str(cause)
    for key in (
        FACE_SERVICE_BASE_URL_ENV,
        FACE_SERVICE_NAMESPACE_ENV,
        FACE_SERVICE_TOKEN_FILE_ENV,
    ):
        assert key in cause_message
    assert TOKEN not in cause_message
    assert TOKEN not in str(failure)


def test_face_port_for_builds_insightface_adapter(monkeypatch: Any, tmp_path: Any) -> None:
    _set_insightface_env(monkeypatch, tmp_path)
    port = face_port_for(_ctx_stub("dev"))
    assert isinstance(port, InsightFaceAdapter)


def test_face_port_for_respects_injected_port() -> None:
    injected = FaceDouble()
    ctx: Any = SimpleNamespace(
        extras={"face_port": injected}, config=SimpleNamespace(environment="dev")
    )
    assert face_port_for(ctx) is injected


def test_face_port_for_unknown_provider_retryable(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "bogus")
    with pytest.raises(JobFailed) as ei:
        face_port_for(_ctx_stub("dev"))
    assert ei.value.code == "DEPENDENCY_UNAVAILABLE"
    assert ei.value.retryable is True


# ================================================================ 7) 传输 + 通用分类


def test_fake_transport_queues_and_records() -> None:
    fake = FakeTransport(
        [
            TransportResult(200, {"ok": True}, {"x-request-id": "r1"}),
            TransportResult(503, {"error": {"code": "X", "retryable": True}}),
        ]
    )
    first = fake.request("POST", "/a", json_body={"k": "v"}, headers_extra={"h": "1"})
    second = fake.request("GET", "/b")
    assert first.status == 200 and first.json == {"ok": True}
    assert second.status == 503
    assert fake.calls == [
        {"method": "POST", "path": "/a", "json_body": {"k": "v"}, "headers_extra": {"h": "1"}},
        {"method": "GET", "path": "/b", "json_body": None, "headers_extra": None},
    ]


def test_fake_transport_default_result_and_exhaustion() -> None:
    default = TransportResult(204, None)
    fake = FakeTransport([TransportResult(200, {})], default_result=default)
    assert fake.request("GET", "/x").status == 200
    assert fake.request("GET", "/x") is default
    strict = FakeTransport()
    with pytest.raises(FaceServiceDependencyError):
        strict.request("GET", "/x")


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_classify_success_statuses(status: int) -> None:
    assert classify_face_response(status, {"anything": True}) is None


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": "WHATEVER", "retryable": True}},
        {"error": {"code": "WHATEVER", "retryable": False}},
        None,
        "not-json",
    ],
)
def test_classify_auth_statuses_win_over_envelope(status: int, body: Any) -> None:
    """HTTP 401/403 → 配置型终态（通用 HTTP 语义，优先于信封 retryable）。"""
    assert classify_face_response(status, body) is TransportErrorClass.AUTH_CONFIG


@pytest.mark.parametrize("status", [500, 502, 503, 504, 408, 429, 425])
def test_classify_retryable_status_fallback(status: int) -> None:
    assert classify_face_response(status, None) is TransportErrorClass.RETRYABLE
    assert classify_face_response(status, "unparseable") is TransportErrorClass.RETRYABLE


@pytest.mark.parametrize("status", [400, 404, 405, 409, 413, 415, 422, 451])
def test_classify_terminal_status_fallback(status: int) -> None:
    assert classify_face_response(status, None) is TransportErrorClass.TERMINAL
    assert classify_face_response(status, [1, 2, 3]) is TransportErrorClass.TERMINAL


@pytest.mark.parametrize("status", [400, 404, 409, 422, 500, 503, 504, 429])
def test_classify_honours_declared_retryable_flag(status: int) -> None:
    """分类只看调用方声明的 ``retryable`` 布尔，不按 code 名称猜测。"""
    retryable_body = {"error": {"code": "ANY_CODE_NAME", "retryable": True}}
    terminal_body = {"error": {"code": "ANY_CODE_NAME", "retryable": False}}
    if status in (401, 403):
        pytest.skip("auth statuses are covered separately")
    assert classify_face_response(status, retryable_body) is TransportErrorClass.RETRYABLE
    assert classify_face_response(status, terminal_body) is TransportErrorClass.TERMINAL


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"error": {}},
        {"error": {"code": "SOME_CODE"}},
        {"error": {"code": "SOME_CODE", "retryable": "true"}},
        {"error": {"code": 123}},
        {"error": "string"},
        {"message": "no envelope"},
    ],
)
def test_classify_envelope_without_boolean_retryable_falls_back(body: Any) -> None:
    assert classify_face_error_body(body) is None
    assert classify_face_response(400, body) is TransportErrorClass.TERMINAL
    assert classify_face_response(503, body) is TransportErrorClass.RETRYABLE


@pytest.mark.parametrize("code", [123, None, "", ["LIST"], {"nested": True}])
def test_classify_ignores_non_string_code_and_honours_retryable_flag(code: Any) -> None:
    """code 名称/类型**从不**参与分类决策；只看布尔 ``retryable``（通用语义）。"""
    assert classify_face_error_body({"error": {"code": code, "retryable": True}}) is (
        TransportErrorClass.RETRYABLE
    )
    assert classify_face_error_body({"error": {"code": code, "retryable": False}}) is (
        TransportErrorClass.TERMINAL
    )


def test_error_code_from_body_is_log_only() -> None:
    assert error_code_from_body({"error": {"code": "SOME_CODE"}}) == "SOME_CODE"
    assert error_code_from_body({"error": {"code": ""}}) is None
    assert error_code_from_body(None) is None


@pytest.mark.parametrize(
    "status,body,expected_exc",
    [
        (503, {"error": {"code": "TRANSIENT", "retryable": True}}, FaceServiceDependencyError),
        (500, None, FaceServiceDependencyError),
        (429, {"error": {"code": "THROTTLED", "retryable": True}}, FaceServiceDependencyError),
        (400, {"error": {"code": "BAD_INPUT", "retryable": False}}, FaceServiceTerminalError),
        (404, {"error": {"code": "MISSING", "retryable": False}}, FaceServiceTerminalError),
        (401, {"error": {"code": "AUTH", "retryable": True}}, FaceServiceAuthConfigError),
        (403, None, FaceServiceAuthConfigError),
    ],
)
def test_raise_for_face_response_typed_exceptions(
    status: int, body: Any, expected_exc: type
) -> None:
    with pytest.raises(expected_exc) as ei:
        raise_for_face_response(status, body, request_id="req-123")
    message = str(ei.value)
    assert f"status={status}" in message
    assert "req-123" in message
    assert TOKEN not in message


def test_raise_for_face_response_success_is_noop() -> None:
    assert raise_for_face_response(200, {"ok": True}) is None
    assert raise_for_face_response(201, None) is None


def test_transport_error_class_hierarchy() -> None:
    assert issubclass(FaceServiceDependencyError, FaceServiceTerminalError.__bases__[0])
    assert issubclass(FaceServiceAuthConfigError, FaceServiceTerminalError)
    assert FaceServiceDependencyError.retryable is True
    assert FaceServiceTerminalError.retryable is False


def test_sealed_transport_fails_closed_and_redacts_token() -> None:
    transport = SealedHttpTransport(
        base_url="http://127.0.0.1:1", token=TOKEN, connect_timeout_ms=10, read_timeout_ms=20
    )
    assert transport.has_token() is True
    assert transport.base_url == "http://127.0.0.1:1"
    with pytest.raises(FaceServiceDependencyError):
        transport.request("POST", "/anything")
    rendered = repr(transport)
    assert TOKEN not in rendered
    assert "<redacted>" in rendered


def test_sealed_transport_without_token_reports_false() -> None:
    transport = SealedHttpTransport(
        base_url="http://127.0.0.1:1", token="", connect_timeout_ms=10, read_timeout_ms=20
    )
    assert transport.has_token() is False
    with pytest.raises(FaceServiceDependencyError):
        transport.request("GET", "/anything")


def test_parse_json_bytes_helper() -> None:
    assert dtransport.parse_json_bytes(b'{"a": 1}') == {"a": 1}
    assert dtransport.parse_json_bytes('{"a": 1}') == {"a": 1}
    assert dtransport.parse_json_bytes(b"not-json") is None
    assert dtransport.parse_json_bytes(b"\xff\xfe") is None
    assert dtransport.parse_json_bytes({"a": 1}) == {"a": 1}


# ================================================================ 8) 活体策略


def test_adapter_never_requests_liveness() -> None:
    assert dliveness.ADAPTER_NEVER_REQUESTS_LIVENESS is True
    params = dliveness.adapter_liveness_request_params()
    assert params == {}
    assert dliveness.LIVENESS_REQUEST_PARAM not in params
    # 返回新字典：调用方改动不影响策略。
    params["require_liveness"] = True
    assert dliveness.adapter_liveness_request_params() == {}


def test_insightface_adapter_sends_no_liveness_request(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """端到端保证：phase 1 适配器根本不发请求，故不可能请求活体。"""
    _set_insightface_env(monkeypatch, tmp_path)
    fake = FakeTransport()
    port = InsightFaceAdapter(DConfig.from_env(), fake)
    _call_all_face_ops(port)
    assert fake.calls == []
    for call in fake.calls:  # pragma: no cover - 防御性
        assert dliveness.LIVENESS_REQUEST_PARAM not in (call.get("json_body") or {})


@pytest.mark.parametrize(
    "block",
    [
        {"supported": False, "reason": "no liveness model"},
        {"supported": False},
        {},
        None,
        {"supported": None},
        "not-a-mapping",
        42,
    ],
)
def test_liveness_supported_false_is_not_a_failure(block: Any) -> None:
    """诚实报告“不支持活体”（或缺失/畸形）→ **不是**失败，身份链必须继续。"""
    assert dliveness.liveness_supported_false_is_not_a_failure(block) is True
    assert dliveness.liveness_is_supported(block) is False
    assert dliveness.liveness_conclusion(block) == dliveness.LIVENESS_CONCLUSION_UNSUPPORTED


def test_liveness_supported_true_is_not_treated_as_passed() -> None:
    block = {"supported": True}
    assert dliveness.liveness_is_supported(block) is True
    # 该谓词是“supported==false 且不构成失败”的合取：supported=true 时不成立。
    assert dliveness.liveness_supported_false_is_not_a_failure(block) is False
    assert dliveness.liveness_conclusion(block) == dliveness.LIVENESS_CONCLUSION_SUPPORTED


@pytest.mark.parametrize(
    "block",
    [
        {"supported": False},
        {"supported": True},
        {},
        None,
    ],
)
def test_liveness_conclusion_is_never_passed(block: Any) -> None:
    conclusion = dliveness.liveness_conclusion(block)
    assert conclusion in (
        dliveness.LIVENESS_CONCLUSION_SUPPORTED,
        dliveness.LIVENESS_CONCLUSION_UNSUPPORTED,
    )
    assert dliveness.liveness_never_concluded_passed(conclusion) is True
    assert "passed" not in conclusion.lower()


def test_liveness_policy_defines_no_passed_conclusion() -> None:
    """结论词表只有 supported/unsupported：**没有** "passed" 这一结论。"""
    conclusions = {
        value
        for name, value in vars(dliveness).items()
        if name.startswith("LIVENESS_CONCLUSION_") and isinstance(value, str)
    }
    assert conclusions == {"supported", "unsupported"}
    assert all("passed" not in conclusion for conclusion in conclusions)


# ================================================================ 9) 非合同守卫


def test_no_per_code_error_table_bound_in_phase1() -> None:
    """监督更正：phase 1 **不得**镜像/绑定 face-service 错误码表（防过早绑定回归）。"""
    assert not hasattr(dtransport, "FACE_ERROR_SPECS")
    assert not hasattr(dtransport, "FACE_AUTH_ERROR_CODES")
    source = inspect.getsource(dtransport)
    # 通用 HTTP 语义允许；逐码 → (status, retryable) 绑定不允许。
    for forbidden_code in (
        "NO_FACE",
        "MULTI_FACES_AMBIGUOUS",
        "IMAGE_DECODE_FAILED",
        "IMAGE_TOO_LARGE",
        "UNSUPPORTED_MEDIA_TYPE",
        "INVALID_REQUEST",
        "SUBJECT_NOT_FOUND",
        "NAMESPACE_NOT_FOUND",
        "SUBJECT_ALREADY_EXISTS",
        "QUALITY_INSUFFICIENT",
        "LIVENESS_UNSUPPORTED",
        "MODEL_UNAVAILABLE",
        "MODEL_NOT_LOADED",
        "UNAUTHORIZED",
        "CONCURRENCY_LIMIT",
        "INFERENCE_TIMEOUT",
        "INTERNAL_ERROR",
    ):
        assert forbidden_code not in source, forbidden_code


@pytest.mark.parametrize("module", [dtransport, dliveness, dtokenfile])
def test_phase1_modules_bind_no_route_paths(module: Any) -> None:
    """phase 1 新模块不得出现任何 face-service 路由字面量（路径/合同未冻结）。"""
    source = inspect.getsource(module)
    for forbidden in ("/v1/", "namespaces/", "subjects", "image_base64", "library_revision"):
        assert forbidden not in source, (module.__name__, forbidden)


def test_insightface_adapter_binds_no_route_paths() -> None:
    source = inspect.getsource(InsightFaceAdapter)
    for forbidden in ("/v1/", "namespaces/", "subjects", "image_base64", "library_revision"):
        assert forbidden not in source, forbidden


def test_search_threshold_config_exists_but_unused_in_phase1() -> None:
    """search 阈值只存在于配置层：适配器/传输实现均不读取（1:N 合同未冻结）。"""
    assert hasattr(DConfig, "__dataclass_fields__")
    assert "face_service_search_threshold" in DConfig.__dataclass_fields__
    for source in (
        inspect.getsource(dtransport),
        inspect.getsource(InsightFaceAdapter),
    ):
        assert "face_service_search_threshold" not in source
        assert "search_threshold" not in source
