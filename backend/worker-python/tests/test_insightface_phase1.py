# -*- coding: utf-8 -*-
"""D 包 insightface：配置 / 0600 token / 工厂选择 / 生产守卫 / 活体策略 纯单元测试。

phase 2 说明：冻结合同已到位，路由/字段/错误码**已绑定**，故 phase 1 的“禁止绑定”
守卫已按合同调整（绑定矩阵在 ``test_insightface_phase2.py``）。本文件聚焦不依赖 HTTP 的
纯单元面：

1. token 文件安全读取矩阵（0600 通过 / 其余权限拒绝 / 缺失 / 目录 / 空 / 纯空白 /
   只剥一个结尾换行 / 取值绝不入异常与日志）；
2. 配置解析（base/namespace/token/connect/read/auto_enroll；phase 1 的 4 个客户端阈值键
   已**移除**；严格整数与严格布尔 fail fast）；
3. ``build_face_port`` 选择矩阵（double / insightface / aliyun_face / unknown）；
4. 生产信号 fail-closed（替身只在 dev/test；insightface 是真实 provider，绝不回退替身）；
5. ``resolve.face_port_for`` 既有分类路径；
6. 活体策略纯函数（永不请求 ``require_liveness``；``supported=false`` 不是失败；无 "passed"）。
"""
from __future__ import annotations

import logging
import os
import stat
from types import SimpleNamespace
from typing import Any

import pytest

from mvp_worker.handlers import JobFailed
from mvp_worker.handlers.dshared import dliveness, dtokenfile
from mvp_worker.handlers.dshared.dconfig import (
    BOOL_ENV_DOMAIN,
    DEFAULT_FACE_SERVICE_AUTO_ENROLL,
    DEFAULT_FACE_SERVICE_CONNECT_TIMEOUT_MS,
    DEFAULT_FACE_SERVICE_READ_TIMEOUT_MS,
    DConfig,
    FACE_PROVIDERS,
    FACE_SERVICE_AUTO_ENROLL_ENV,
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_READ_TIMEOUT_MS_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    ProviderConfigError,
    assert_no_double_injection_in_production,
    double_injection_overrides,
)
from mvp_worker.handlers.dshared.dtokenfile import TokenFileError, read_token_file
from mvp_worker.handlers.dshared.providers import (
    AliyunFaceAdapter,
    FaceDouble,
    FacePort,
    InsightFaceAdapter,
    ProviderUnavailable,
    build_face_port,
)
from mvp_worker.handlers.dshared.resolve import face_port_for

# 占位 token（**绝不**是真实凭据）。
TOKEN = "TEST-TOKEN-PLACEHOLDER"

_REMOVED_THRESHOLD_KEYS = (
    "MVP_D_FACE_SERVICE_QUALITY_MIN_DET_SCORE",
    "MVP_D_FACE_SERVICE_QUALITY_MIN_BBOX_RATIO",
    "MVP_D_FACE_SERVICE_VERIFY_THRESHOLD",
    "MVP_D_FACE_SERVICE_SEARCH_THRESHOLD",
)

_FACE_SERVICE_ENVS = (
    "MVP_D_FACE_PROVIDER",
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV,
    FACE_SERVICE_READ_TIMEOUT_MS_ENV,
    FACE_SERVICE_AUTO_ENROLL_ENV,
    *_REMOVED_THRESHOLD_KEYS,
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
    """每个测试从“未配置 insightface + 无生产信号 + 无替身注入”起步。"""
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
    token_path = _write_token_file(tmp_path, content=token_content, mode=mode)
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, "http://127.0.0.1:1")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, "mvp-ns-1")
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, token_path)
    return token_path


def _ctx_stub(environment: str = "dev") -> Any:
    return SimpleNamespace(extras={}, config=SimpleNamespace(environment=environment))


# ================================================================ 1) token 文件


def test_token_file_0600_returns_value(tmp_path: Any) -> None:
    path = _write_token_file(tmp_path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert read_token_file(path) == TOKEN


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o700, 0o777, 0o400, 0o660, 0o666])
def test_token_file_rejects_non_0600_permissions(tmp_path: Any, mode: int) -> None:
    path = _write_token_file(tmp_path, mode=mode)
    with pytest.raises(TokenFileError) as ei:
        read_token_file(path)
    message = str(ei.value)
    assert FACE_SERVICE_TOKEN_FILE_ENV in message
    assert "0600" in message
    assert oct(mode) in message
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
        (TOKEN + "\n\n", TOKEN + "\n"),
        ("  " + TOKEN + "  \n", "  " + TOKEN + "  "),
    ],
)
def test_token_file_strips_exactly_one_trailing_newline(
    tmp_path: Any, content: str, expected: str
) -> None:
    path = _write_token_file(tmp_path, content=content)
    assert read_token_file(path) == expected


def test_token_value_never_in_exception_text_or_logs(tmp_path: Any, caplog: Any) -> None:
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
    assert cfg.face_service_auto_enroll is DEFAULT_FACE_SERVICE_AUTO_ENROLL is False


def test_read_timeout_default_covers_server_inference_timeout() -> None:
    """合同 §7：客户端读超时必须 >= 服务端推理超时（默认 30s），否则误判 timeout。"""
    assert DEFAULT_FACE_SERVICE_READ_TIMEOUT_MS >= 30000


def test_removed_client_threshold_keys_are_gone() -> None:
    """phase 1 的 4 个客户端阈值键**移除**：服务端固定策略，不可发送（合同 §4.1/§5.1）。"""
    fields = set(DConfig.__dataclass_fields__)
    for removed in (
        "face_service_quality_min_det_score",
        "face_service_quality_min_bbox_ratio",
        "face_service_verify_threshold",
        "face_service_search_threshold",
    ):
        assert removed not in fields, removed


def test_removed_threshold_env_keys_are_ignored(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """旧键即使残留于环境也**不被解析**（不产生字段、不影响构建）。"""
    for key in _REMOVED_THRESHOLD_KEYS:
        monkeypatch.setenv(key, "0.99")
    cfg = DConfig.from_env()
    assert not any("threshold" in name or "quality_min" in name for name in vars(cfg))
    _set_insightface_env(monkeypatch, tmp_path)
    assert isinstance(build_face_port(DConfig.from_env(), environment="dev"), InsightFaceAdapter)


def test_face_service_config_explicit_values(monkeypatch: Any, tmp_path: Any) -> None:
    token_path = _write_token_file(tmp_path)
    monkeypatch.setenv(FACE_SERVICE_BASE_URL_ENV, "http://127.0.0.1:8010")
    monkeypatch.setenv(FACE_SERVICE_NAMESPACE_ENV, "ns-x")
    monkeypatch.setenv(FACE_SERVICE_TOKEN_FILE_ENV, token_path)
    monkeypatch.setenv(FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV, "1500")
    monkeypatch.setenv(FACE_SERVICE_READ_TIMEOUT_MS_ENV, "4500")
    monkeypatch.setenv(FACE_SERVICE_AUTO_ENROLL_ENV, "true")
    cfg = DConfig.from_env()
    assert cfg.face_service_base_url == "http://127.0.0.1:8010"
    assert cfg.face_service_namespace == "ns-x"
    assert cfg.face_service_token_file == token_path
    assert cfg.face_service_connect_timeout_ms == 1500
    assert cfg.face_service_read_timeout_ms == 4500
    assert cfg.face_service_auto_enroll is True


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("On", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("", False),  # 空 = 默认 false
    ],
)
def test_auto_enroll_strict_bool_accepts_known_values(
    monkeypatch: Any, raw: str, expected: bool
) -> None:
    monkeypatch.setenv(FACE_SERVICE_AUTO_ENROLL_ENV, raw)
    assert DConfig.from_env().face_service_auto_enroll is expected


def test_auto_enroll_strict_bool_rejects_unknown(monkeypatch: Any) -> None:
    monkeypatch.setenv(FACE_SERVICE_AUTO_ENROLL_ENV, "maybe")
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    assert FACE_SERVICE_AUTO_ENROLL_ENV in str(ei.value)
    assert BOOL_ENV_DOMAIN in str(ei.value)


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


def test_insightface_is_registered_face_provider() -> None:
    assert "insightface" in FACE_PROVIDERS
    assert FACE_PROVIDERS == ("double", "aliyun_face", "insightface")


def test_face_service_not_bound_symbol_removed() -> None:
    """phase 1 的“未绑定”状态符号已随真实绑定移除（防回归到 phase 1 假设）。"""
    import mvp_worker.handlers.dshared.providers as providers_module

    assert not hasattr(providers_module, "FaceServiceNotBound")


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
    for key, value in prod_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "double")
    with pytest.raises(ProviderConfigError) as ei:
        build_face_port(DConfig.from_env(), environment="dev")
    assert "forbidden in production" in str(ei.value)


def test_production_allows_insightface_real_provider(
    monkeypatch: Any, tmp_path: Any
) -> None:
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    port = build_face_port(DConfig.from_env(), environment="production")
    assert isinstance(port, InsightFaceAdapter)
    assert not isinstance(port, FaceDouble)


def test_insightface_never_falls_back_to_double_even_with_double_knobs(
    monkeypatch: Any, tmp_path: Any
) -> None:
    _set_insightface_env(monkeypatch, tmp_path)
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SEARCH", "matched")
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_QUALITY", "accepted")
    port = build_face_port(DConfig.from_env(), environment="dev")
    assert isinstance(port, InsightFaceAdapter)
    assert not isinstance(port, FaceDouble)


def test_production_with_insightface_and_injection_switch_refused(
    monkeypatch: Any, tmp_path: Any
) -> None:
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
    assert_no_double_injection_in_production()
    assert isinstance(
        build_face_port(DConfig.from_env(), environment="dev"), InsightFaceAdapter
    )


# ================================================================ 5) resolve 分类


def test_face_port_for_maps_insightface_config_error_to_retryable(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "insightface")
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


def test_face_port_for_builds_insightface_adapter(
    monkeypatch: Any, tmp_path: Any
) -> None:
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


# ================================================================ 6) 活体策略（纯函数）


def test_adapter_never_requests_liveness() -> None:
    assert dliveness.ADAPTER_NEVER_REQUESTS_LIVENESS is True
    params = dliveness.adapter_liveness_request_params()
    assert params == {}
    assert dliveness.LIVENESS_REQUEST_PARAM not in params
    params["require_liveness"] = True
    assert dliveness.adapter_liveness_request_params() == {}


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
    assert dliveness.liveness_supported_false_is_not_a_failure(block) is True
    assert dliveness.liveness_is_supported(block) is False
    assert dliveness.liveness_conclusion(block) == dliveness.LIVENESS_CONCLUSION_UNSUPPORTED


def test_liveness_supported_true_is_not_treated_as_passed() -> None:
    block = {"supported": True}
    assert dliveness.liveness_is_supported(block) is True
    assert dliveness.liveness_supported_false_is_not_a_failure(block) is False
    assert dliveness.liveness_conclusion(block) == dliveness.LIVENESS_CONCLUSION_SUPPORTED


@pytest.mark.parametrize("block", [{"supported": False}, {"supported": True}, {}, None])
def test_liveness_conclusion_is_never_passed(block: Any) -> None:
    conclusion = dliveness.liveness_conclusion(block)
    assert conclusion in (
        dliveness.LIVENESS_CONCLUSION_SUPPORTED,
        dliveness.LIVENESS_CONCLUSION_UNSUPPORTED,
    )
    assert dliveness.liveness_never_concluded_passed(conclusion) is True
    assert "passed" not in conclusion.lower()


def test_liveness_policy_defines_no_passed_conclusion() -> None:
    conclusions = {
        value
        for name, value in vars(dliveness).items()
        if name.startswith("LIVENESS_CONCLUSION_") and isinstance(value, str)
    }
    assert conclusions == {"supported", "unsupported"}
    assert all("passed" not in conclusion for conclusion in conclusions)