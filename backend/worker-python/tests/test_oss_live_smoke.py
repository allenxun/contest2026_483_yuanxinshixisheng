"""本地回归：B 真实 OSS 跨语言 smoke 的 Python 侧（**绝不联网、无需真实凭据**）。

运行器：``tests/oss_live_smoke.py``（不以 ``test_`` 开头，pytest 不收集）。
契约：``.coordination/B-work/oss-live-smoke/contract.md``。
"""
from __future__ import annotations

import hashlib
from typing import Any

import pytest

import oss_live_smoke as smoke

# 明显占位的合成假值（绝不使用真实凭据/桶名）。
FAKE_BUCKET = "fake-bucket-do-not-use"
FAKE_AK = "LTAI-FAKE-DO-NOT-USE"
FAKE_SK = "fake-secret-do-not-use"
FAKE_STS = "fake-sts-token-do-not-use"
FAKE_SERVER_ENDPOINT = "https://oss-fake-server.example.com"
FAKE_PUBLIC_ENDPOINT = "https://oss-fake-public.example.com"
FAKE_REGION = "cn-hangzhou"

VECTOR_SEED = "b-oss-smoke-vector"
# 契约 §2.1 权威向量（与 Java 侧硬编码同一取值，不得各自重算后填不同值）。
VECTOR_256_SHA = "0e46beb450377892dc132e1f97087b55311f042a8757d105c03a1a2030e14e32"
VECTOR_64_SHA = "f3a9429115790ee322b3f4a20263f2c9e1ad286928c7f9fac6d4a6cd93c258fd"
VECTOR_1_SHA = "0a43b22d89fa2499be5c7704c9bf273260b0ca9588e4cd1897cd80f9c96cd97a"
KEY_DIGEST_EXAMPLE = "6ca2e86b3621"

VALID_KEY = "dev/assessment_result/00000000-0000-4000-8000-000000000000"

_ENV_CLEAR = (
    "MVP_D_STORAGE_PROVIDER",
    "MVP_A_STORAGE_OSS_REGION",
    "MVP_A_STORAGE_OSS_ENDPOINT",
    "MVP_A_STORAGE_OSS_SERVER_ENDPOINT",
    "MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT",
    "MVP_A_STORAGE_OSS_BUCKET",
    "MVP_A_STORAGE_OSS_ACCESS_KEY_ID",
    "MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET",
    "MVP_A_STORAGE_OSS_SECURITY_TOKEN",
    "MVP_OSS_LIVE_SMOKE",
    "MVP_D_STORAGE_DOUBLE_FAIL_PUT",
    "MVP_NOTIFY_ENV",
    "MVP_WORKER_ENVIRONMENT",
    "APP_ENV",
    "SPRING_PROFILES_ACTIVE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_CLEAR:
        monkeypatch.delenv(name, raising=False)


def _set_fake_live_env(monkeypatch: pytest.MonkeyPatch, *, opt_in: bool = True) -> None:
    monkeypatch.setenv("MVP_D_STORAGE_PROVIDER", "aliyun_oss")
    monkeypatch.setenv("MVP_A_STORAGE_OSS_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_ID", FAKE_AK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET", FAKE_SK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_SERVER_ENDPOINT", FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT", FAKE_PUBLIC_ENDPOINT)
    if opt_in:
        monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")


def _run_double(tmp_path: Any, phase: str, key: str = VALID_KEY, *, seed: str = "seed", nbytes: int = 64) -> Any:
    return smoke.run_phase(
        mode="double",
        phase=phase,
        object_key=key,
        content_seed=seed,
        content_bytes=nbytes,
        double_root=str(tmp_path / "shared-root"),
    )


# ============================================================ 1) 权威向量（跨语言）


@pytest.mark.parametrize(
    ("nbytes", "expected"),
    [(256, VECTOR_256_SHA), (64, VECTOR_64_SHA), (1, VECTOR_1_SHA)],
)
def test_authoritative_vectors(nbytes: int, expected: str) -> None:
    """smoke_bytes 与契约 §2.1 的权威向量逐字一致（=与 Java 强制同构）。"""
    assert hashlib.sha256(smoke.smoke_bytes(VECTOR_SEED, nbytes)).hexdigest() == expected


def test_authoritative_vector_length_and_prefix_rules() -> None:
    assert smoke.smoke_bytes(VECTOR_SEED, 256).startswith(smoke.smoke_bytes(VECTOR_SEED, 1))
    assert len(smoke.smoke_bytes(VECTOR_SEED, 33)) == 33
    assert smoke.smoke_bytes(VECTOR_SEED, 0) == b""


def test_key_digest_contract_example() -> None:
    assert smoke.key_digest(VALID_KEY) == KEY_DIGEST_EXAMPLE
    assert smoke.key_digest("") == "none"


# ============================================================ 2) 对象键校验


@pytest.mark.parametrize(
    "key",
    [
        VALID_KEY,
        "prod-1/assessment_result/abcdef00-1234-4abc-8def-0123456789ab",
    ],
)
def test_object_key_accepts_valid(key: str) -> None:
    assert smoke.is_valid_object_key(key) is True


@pytest.mark.parametrize(
    ("key", "why"),
    [
        ("dev/assessment_result/../00000000-0000-4000-8000-000000000000", "contains .."),
        ("/dev/assessment_result/00000000-0000-4000-8000-000000000000", "leading slash"),
        ("dev/assessment_result/00000000-0000-4000-8000-000000000000/", "trailing slash"),
        ("dev/assessment_result", "two segments"),
        ("dev/assessment_result/00000000-0000-4000-8000-000000000000/extra", "four segments"),
        ("dev/assessment_source/00000000-0000-4000-8000-000000000000", "wrong purpose"),
        ("dev/assessment_result/not-a-uuid", "bad uuid shape"),
        ("dev/assessment_result/00000000-0000-4000-8000-00000000000", "uuid too short"),
        ("DEV/assessment_result/00000000-0000-4000-8000-000000000000", "uppercase env"),
        ("dev/assessment_result/00000000-0000-4000-8000-00000000000A", "uppercase uuid hex"),
        ("", "empty"),
    ],
)
def test_object_key_rejects_invalid(key: str, why: str) -> None:
    assert smoke.is_valid_object_key(key) is False, why


# ============================================================ 3) 输出净化


class _RaisingPort:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def put(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        raise self._exc

    def get(self, object_key: str) -> bytes:
        raise self._exc

    def delete(self, object_key: str) -> None:
        raise self._exc

    def exists(self, object_key: str) -> bool:
        raise self._exc


def test_error_output_is_sanitized(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """异常 message 含 bucket/endpoint/key/AK/SK/STS → 输出必须全部剔除，且含 keyDigest。"""
    monkeypatch.setenv("MVP_A_STORAGE_OSS_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_ID", FAKE_AK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET", FAKE_SK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_SECURITY_TOKEN", FAKE_STS)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_SERVER_ENDPOINT", FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT", FAKE_PUBLIC_ENDPOINT)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_REGION", FAKE_REGION)
    nasty = (
        f"object not found: {VALID_KEY!r} bucket={FAKE_BUCKET}"
        f" server={FAKE_SERVER_ENDPOINT} public={FAKE_PUBLIC_ENDPOINT}"
        f" region={FAKE_REGION} ak={FAKE_AK} sk={FAKE_SK} sts={FAKE_STS}"
    )
    monkeypatch.setattr(smoke, "build_port", lambda **_: _RaisingPort(RuntimeError(nasty)))

    res = _run_double(tmp_path, "write")
    assert res.result == "fail" and res.exit_code != 0
    blob = "\n".join(res.lines)
    for forbidden in (
        FAKE_BUCKET, VALID_KEY, FAKE_AK, FAKE_SK, FAKE_STS,
        FAKE_SERVER_ENDPOINT, FAKE_PUBLIC_ENDPOINT, FAKE_REGION,
    ):
        assert forbidden not in blob, f"leaked: {forbidden}"
    assert "[oss-smoke-error]" in blob
    assert f"keyDigest={KEY_DIGEST_EXAMPLE}" in res.lines[0]


def test_scrub_redacts_ltai_shape_and_preserves_key_digest() -> None:
    msg = "credential LTAI-something-else key=" + VALID_KEY
    scrubbed = smoke._scrub(msg, [VALID_KEY])
    assert "LTAI" not in scrubbed
    assert VALID_KEY not in scrubbed
    assert "<redacted>" in scrubbed


# ============================================================ 4) 三重门


def test_live_gate_requires_aliyun_oss_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    assert smoke.check_live_gates() == ("live-provider-not-aliyun-oss", [])


def test_live_gate_missing_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_D_STORAGE_PROVIDER", "aliyun_oss")
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_ID", FAKE_AK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET", FAKE_SK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_SERVER_ENDPOINT", FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT", FAKE_PUBLIC_ENDPOINT)
    monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")
    step, missing = smoke.check_live_gates()  # type: ignore[misc]
    assert step == "missing-config-key"
    assert missing == ["MVP_A_STORAGE_OSS_BUCKET"]


def test_live_gate_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_D_STORAGE_PROVIDER", "aliyun_oss")
    monkeypatch.setenv("MVP_A_STORAGE_OSS_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_ID", FAKE_AK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_SERVER_ENDPOINT", FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT", FAKE_PUBLIC_ENDPOINT)
    monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")
    step, missing = smoke.check_live_gates()  # type: ignore[misc]
    assert step == "missing-config-key"
    assert missing == ["MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET"]


def test_live_gate_missing_server_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_D_STORAGE_PROVIDER", "aliyun_oss")
    monkeypatch.setenv("MVP_A_STORAGE_OSS_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_ID", FAKE_AK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET", FAKE_SK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT", FAKE_PUBLIC_ENDPOINT)
    monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")
    step, missing = smoke.check_live_gates()  # type: ignore[misc]
    assert step == "missing-config-key"
    assert missing == ["MVP_A_STORAGE_OSS_SERVER_ENDPOINT"]


def test_live_gate_missing_public_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_D_STORAGE_PROVIDER", "aliyun_oss")
    monkeypatch.setenv("MVP_A_STORAGE_OSS_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_ID", FAKE_AK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET", FAKE_SK)
    monkeypatch.setenv("MVP_A_STORAGE_OSS_SERVER_ENDPOINT", FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")
    step, missing = smoke.check_live_gates()  # type: ignore[misc]
    assert step == "missing-config-key"
    assert missing == ["MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT"]


def test_live_gate_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_fake_live_env(monkeypatch, opt_in=False)
    assert smoke.check_live_gates() == ("live-opt-in-missing", [])


def test_live_gate_all_satisfied_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_fake_live_env(monkeypatch)
    assert smoke.check_live_gates() is None
    # public-url-probe 短路：即使 gates 通过也绝不联网/绝不发 HTTP。
    res = smoke.run_phase(
        mode="live", phase="public-url-probe", object_key=VALID_KEY,
        content_seed="s", content_bytes=8, double_root=None,
    )
    assert res.result == "skipped" and res.reason == "no-live-bucket"
    assert res.step == "public-url-probe-owned-by-java"


def test_live_phase_aborts_when_provider_missing() -> None:
    res = smoke.run_phase(
        mode="live", phase="write", object_key=VALID_KEY,
        content_seed="s", content_bytes=8, double_root=None,
    )
    assert res.result == "fail" and res.exit_code == 1
    assert res.reason == "not-opted-in"
    assert res.step == "live-provider-not-aliyun-oss"


def test_live_phase_aborts_missing_config_key_reports_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_D_STORAGE_PROVIDER", "aliyun_oss")
    monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")
    res = smoke.run_phase(
        mode="live", phase="write", object_key=VALID_KEY,
        content_seed="s", content_bytes=8, double_root=None,
    )
    assert res.result == "fail" and res.reason == "missing-config-key"
    blob = "\n".join(res.lines)
    assert "MVP_A_STORAGE_OSS_BUCKET" in blob  # 只报键名
    assert "MVP_A_STORAGE_OSS_SERVER_ENDPOINT" in blob
    assert "MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT" in blob
    assert FAKE_BUCKET not in blob


def test_double_mode_refuses_live_opt_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("MVP_OSS_LIVE_SMOKE", "true")
    res = _run_double(tmp_path, "write")
    assert res.result == "fail" and res.exit_code == 1
    assert res.reason == "not-opted-in"
    assert res.step == "double-mode-refuses-live-opt-in"


# ============================================================ 5) double 全流程


def test_double_full_flow_layout_and_bytes(tmp_path: Any) -> None:
    root = tmp_path / "shared-root"
    expected = smoke.smoke_bytes("seed", 64)
    expected_sha12 = hashlib.sha256(expected).hexdigest()[:12]

    wrote = _run_double(tmp_path, "write")
    assert wrote.result == "ok" and wrote.exit_code == 0
    assert wrote.nbytes == 64 and wrote.sha12 == expected_sha12
    # 跨语言前提：布局为 <root>/<object_key> 原样。
    assert (root / VALID_KEY).read_bytes() == expected

    verified = _run_double(tmp_path, "verify")
    assert verified.result == "ok" and verified.reason == "none"
    assert verified.nbytes == 64 and verified.sha12 == expected_sha12

    deleted = _run_double(tmp_path, "delete")
    assert deleted.result == "ok" and deleted.exit_code == 0
    assert not (root / VALID_KEY).exists()

    absent = _run_double(tmp_path, "confirm-absent")
    assert absent.result == "ok" and absent.reason == "absent-confirmed"


def test_double_write_result_line_matches_contract(tmp_path: Any) -> None:
    res = _run_double(tmp_path, "write")
    parsed = smoke.parse_result_line(res.lines[0])
    assert parsed == {
        "side": "python",
        "mode": "double",
        "phase": "write",
        "step": "write",
        "result": "ok",
        "reason": "none",
        "code": "none",
        "requestId": "none",
        "bytes": "64",
        "sha256": smoke.sha256_hex(smoke.smoke_bytes("seed", 64))[:12],
        "keyDigest": KEY_DIGEST_EXAMPLE,
        "purpose": "assessment_result",
    }


def test_double_invalid_key_rejected_before_port(tmp_path: Any) -> None:
    res = smoke.run_phase(
        mode="double", phase="write", object_key="not/a/valid/key/at/all",
        content_seed="s", content_bytes=8, double_root=str(tmp_path / "r"),
    )
    assert res.result == "fail" and res.reason == "invalid-object-key"
    assert res.step == "object-key-validation"


def test_double_missing_root_is_structured_failure() -> None:
    res = smoke.run_phase(
        mode="double", phase="write", object_key=VALID_KEY,
        content_seed="s", content_bytes=8, double_root=None,
    )
    assert res.result == "fail" and res.reason == "missing-config-key"
    assert res.step == "double-root-required"


# ============================================================ 6) CLI 接线


def test_cli_config_flag_accepted_and_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    rc = smoke.main([
        "--mode", "double", "--phase", "write", "--object-key", VALID_KEY,
        "--content-seed", "seed", "--content-bytes", "8",
        "--double-root", str(tmp_path / "r"), "--config", "/nonexistent/java-only.yml",
    ])
    out = capsys.readouterr()
    assert rc == 0
    assert "[oss-smoke] side=python mode=double phase=write step=write result=ok" in out.out
    assert "config-ignored-python-reads-env" in out.err
