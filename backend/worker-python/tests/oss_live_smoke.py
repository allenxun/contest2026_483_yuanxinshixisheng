"""B 真实 OSS 跨语言 smoke —— Python 侧阶段运行器（CLI，非 pytest 收集文件）。

共享契约：``.coordination/B-work/oss-live-smoke/contract.md``（两侧逐字一致）。
- **默认绝不联网**：``--mode live`` 需三重显式 opt-in + 真实凭据环境变量，仅由根执行；
  OpenCode 本地只跑 ``--mode double``（``FilesystemStorageDouble``，与 Java 共享 root）。
- 对象操作**全部**复用生产实现（``AliyunOssStorage`` / ``FilesystemStorageDouble``），
  并经生产解析路径 ``build_storage_port`` 选择，绝不另写 SDK put/get/exists/delete。
- 输出净化：结果行只含固定 token 与 ``keyDigest``；失败错误行 message 先剔除
  bucket/endpoint/region/完整 key/AK/SK/STS 形态子串再输出。
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 允许以脚本方式从源码树直接运行（venv editable 安装时此行无害）。
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mvp_worker.handlers.dshared.dconfig import DConfig  # noqa: E402
from mvp_worker.handlers.dshared.providers import (  # noqa: E402
    ProviderConfigError,
    build_storage_port,
)
from mvp_worker.media.storage import (  # noqa: E402
    OSS_ACCESS_KEY_ID_ENV,
    OSS_ACCESS_KEY_SECRET_ENV,
    OSS_BUCKET_ENV,
    OSS_ENDPOINT_ENV,
    OSS_REGION_ENV,
    OSS_SECURITY_TOKEN_ENV,
    STORAGE_PROVIDER_ALIYUN_OSS,
    STORAGE_PROVIDER_DOUBLE,
    STORAGE_PROVIDER_ENV,
)

SIDE = "python"
LIVE_SMOKE_ENV = "MVP_OSS_LIVE_SMOKE"
CONTENT_TYPE = "application/octet-stream"
PURPOSE = "assessment_result"
DEFAULT_CONTENT_BYTES = 256

_MISSING = object()

# 契约 §1：对象键形态 <env>/assessment_result/<uuid>（恰 3 段）。
KEY_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]{0,31}/assessment_result/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# 契约 §4：固定 reason token（绝不拼接值）。
REASON_NOT_OPTED_IN = "not-opted-in"
REASON_MISSING_CONFIG_KEY = "missing-config-key"
REASON_INVALID_OBJECT_KEY = "invalid-object-key"
REASON_BYTES_MISMATCH = "bytes-mismatch"
REASON_SHA_MISMATCH = "sha-mismatch"
REASON_ABSENT_CONFIRMED = "absent-confirmed"
REASON_STILL_EXISTS = "still-exists"
REASON_NO_LIVE_BUCKET = "no-live-bucket"
REASON_ADAPTER_ERROR = "adapter-error"
# verify 阶段对象缺失的专用 token（orchestrator 裁定，两侧统一）：adapter-error 会掩盖
# "对象确定不存在"这一事实，absent-confirmed 只用于 confirm-absent 的成功语义。
REASON_OBJECT_MISSING = "object-missing"

# 契约 §5：live 三重门必填配置键（只报键名）。
_OSS_REQUIRED_KEYS = (OSS_BUCKET_ENV, OSS_ACCESS_KEY_ID_ENV, OSS_ACCESS_KEY_SECRET_ENV)
_OSS_SECRET_ENVS = (
    OSS_BUCKET_ENV,
    OSS_ACCESS_KEY_ID_ENV,
    OSS_ACCESS_KEY_SECRET_ENV,
    OSS_SECURITY_TOKEN_ENV,
    OSS_ENDPOINT_ENV,
    OSS_REGION_ENV,
)

PHASES = ("write", "verify", "delete", "confirm-absent", "public-url-probe")


# --------------------------------------------------------------------------- 契约 §2


def smoke_bytes(seed: str, nbytes: int) -> bytes:
    """契约 §2：``SHA256(seed + ":" + str(i))`` 串联后截断（每轮 32 字节）。"""
    out = b""
    i = 0
    while len(out) < nbytes:
        out += hashlib.sha256(f"{seed}:{i}".encode("utf-8")).digest()
        i += 1
    return out[:nbytes]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_digest(object_key: str) -> str:
    """``sha256(objectKey UTF-8)`` 前 12 位；key 为空 → ``none``。"""
    if not object_key:
        return "none"
    return hashlib.sha256(object_key.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- 契约 §1


def is_valid_object_key(object_key: str) -> bool:
    """契约 §1：正则 + 显式拒绝（``..`` / 前导或尾随 ``/`` / 段数≠3 / purpose）。"""
    if not object_key:
        return False
    if object_key.startswith("/") or object_key.endswith("/"):
        return False
    if ".." in object_key:
        return False
    parts = object_key.split("/")
    if len(parts) != 3:
        return False
    if parts[1] != PURPOSE:
        return False
    return bool(KEY_RE.fullmatch(object_key))


def _key_environment(object_key: str) -> str:
    parts = object_key.split("/")
    return parts[0] if parts and parts[0] else "dev"


# --------------------------------------------------------------------------- 净化


def _scrub(message: str, secrets: list[str]) -> str:
    """剔除 bucket/endpoint/region/完整 key/AK/SK/STS 与任何 ``LTAI`` 形态子串。"""
    out = message
    for value in sorted((s for s in secrets if s), key=len, reverse=True):
        out = out.replace(value, "<redacted>")
    out = re.sub(r"LTAI[A-Za-z0-9_.\-]+", "<redacted>", out)
    return out


def _secrets(context_key: str) -> list[str]:
    return [context_key] + [os.environ.get(name, "") for name in _OSS_SECRET_ENVS]


def _sanitized_error_line(phase: str, exc: BaseException, context_key: str) -> str:
    return (
        f"[oss-smoke-error] side={SIDE} phase={phase}"
        f" exception={type(exc).__name__}"
        f" message={_scrub(str(exc), _secrets(context_key))}"
    )


def _sdk_identifiers(exc: BaseException) -> tuple[str, str]:
    """从生产映射异常链取非秘密的 ``code``/``requestId``；取不到 → ``none``。"""
    cause: BaseException | None = exc.__cause__
    code = "none"
    request_id = "none"
    if cause is not None:
        raw_code = getattr(cause, "code", "") or ""
        raw_rid = getattr(cause, "request_id", "") or ""
        if raw_code:
            code = str(raw_code)
        if raw_rid:
            request_id = str(raw_rid)
    return code, request_id


# --------------------------------------------------------------------------- 输出


@dataclass(frozen=True)
class SmokeResult:
    exit_code: int
    lines: list[str]
    mode: str
    phase: str
    step: str
    result: str
    reason: str
    nbytes: int = -1
    sha12: str = "none"
    key_digest_value: str = "none"


def format_result_line(
    *,
    mode: str,
    phase: str,
    step: str,
    result: str,
    reason: str,
    code: str = "none",
    request_id: str = "none",
    nbytes: int = -1,
    sha12: str = "none",
    object_key: str = "",
) -> str:
    return (
        f"[oss-smoke] side={SIDE} mode={mode} phase={phase} step={step}"
        f" result={result} reason={reason} code={code} requestId={request_id}"
        f" bytes={nbytes} sha256={sha12} keyDigest={key_digest(object_key)}"
        f" purpose={PURPOSE}"
    )


def parse_result_line(line: str) -> dict[str, str]:
    """把结果行解析为 ``k=v`` 字典（供测试与驱动校验）。"""
    prefix = "[oss-smoke] "
    payload = line[len(prefix):] if line.startswith(prefix) else line
    tokens: dict[str, str] = {}
    for chunk in payload.split(" "):
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            tokens[key] = value
    return tokens


def _result(
    *,
    mode: str,
    phase: str,
    step: str,
    result: str,
    reason: str,
    exit_code: int,
    code: str = "none",
    request_id: str = "none",
    nbytes: int = -1,
    sha12: str = "none",
    object_key: str = "",
    error: BaseException | None = None,
) -> SmokeResult:
    lines = [
        format_result_line(
            mode=mode,
            phase=phase,
            step=step,
            result=result,
            reason=reason,
            code=code,
            request_id=request_id,
            nbytes=nbytes,
            sha12=sha12,
            object_key=object_key,
        )
    ]
    if error is not None:
        lines.append(_sanitized_error_line(phase, error, object_key))
    return SmokeResult(
        exit_code=exit_code,
        lines=lines,
        mode=mode,
        phase=phase,
        step=step,
        result=result,
        reason=reason,
        nbytes=nbytes,
        sha12=sha12,
        key_digest_value=key_digest(object_key),
    )


def _ok(mode: str, phase: str, *, nbytes: int = -1, sha12: str = "none", reason: str = "none", object_key: str = "") -> SmokeResult:
    return _result(mode=mode, phase=phase, step=phase, result="ok", reason=reason, exit_code=0, nbytes=nbytes, sha12=sha12, object_key=object_key)


def _fail(mode: str, phase: str, *, step: str, reason: str, nbytes: int = -1, sha12: str = "none", object_key: str = "", error: BaseException | None = None, code: str = "none", request_id: str = "none") -> SmokeResult:
    return _result(mode=mode, phase=phase, step=step, result="fail", reason=reason, exit_code=1, nbytes=nbytes, sha12=sha12, object_key=object_key, error=error, code=code, request_id=request_id)


# --------------------------------------------------------------------------- 契约 §5


def live_opt_in() -> bool:
    return os.environ.get(LIVE_SMOKE_ENV, "").strip().lower() == "true"


def check_live_gates() -> tuple[str, list[str]] | None:
    """三重门的**纯判定**（不联网、不构建端口）。

    返回 ``None`` = 全部通过；否则返回 ``(step_token, missing_key_names)``。
    判定顺序按契约 §5：① provider ② 凭据键 ③ 显式开关。
    """
    provider = os.environ.get(STORAGE_PROVIDER_ENV, STORAGE_PROVIDER_DOUBLE)
    if provider != STORAGE_PROVIDER_ALIYUN_OSS:
        return ("live-provider-not-aliyun-oss", [])
    missing = [name for name in _OSS_REQUIRED_KEYS if not os.environ.get(name, "").strip()]
    if missing:
        return ("missing-config-key", missing)
    if not live_opt_in():
        return ("live-opt-in-missing", [])
    return None


# --------------------------------------------------------------------------- 端口


def build_port(*, mode: str, double_root: str | None, environment: str) -> Any:
    """经生产解析路径构建端口（绝不绕过 provider 选择）。

    - ``double``：``DConfig`` 强制 provider=double → ``FilesystemStorageDouble(double_root)``
      （仍走 ``build_storage_port``，含生产 fail-closed 守卫）；
    - ``live``：``DConfig.from_env()`` 原样 → ``AliyunOssStorage``（缺键只报键名）。
    """
    cfg = DConfig.from_env()
    if mode == "double":
        cfg = dataclasses.replace(cfg, storage_provider=STORAGE_PROVIDER_DOUBLE)
        return build_storage_port(cfg, environment=environment, dev_dir=double_root)
    return build_storage_port(cfg, environment=environment, dev_dir=None)


# --------------------------------------------------------------------------- 阶段


def run_phase(
    *,
    mode: str,
    phase: str,
    object_key: str,
    content_seed: str,
    content_bytes: int,
    double_root: str | None,
) -> SmokeResult:
    # 契约 §3：public-url-probe 由 Java 侧实现；Python 侧只报 skipped，绝不发 HTTP。
    if phase == "public-url-probe":
        return _result(
            mode=mode,
            phase=phase,
            step="public-url-probe-owned-by-java",
            result="skipped",
            reason=REASON_NO_LIVE_BUCKET,
            exit_code=0,
            object_key=object_key,
        )

    if content_bytes < 0:
        return _fail(mode, phase, step=phase, reason=REASON_ADAPTER_ERROR, object_key=object_key)

    # --- 选择/构建端口（生产解析路径） ---
    if mode == "double":
        # 契约 §5 末段：double 模式发现 live opt-in → abort。
        if live_opt_in():
            return _fail(
                mode, phase,
                step="double-mode-refuses-live-opt-in",
                reason=REASON_NOT_OPTED_IN,
                object_key=object_key,
            )
        if not double_root:
            return _fail(
                mode, phase, step="double-root-required",
                reason=REASON_MISSING_CONFIG_KEY, object_key=object_key,
            )
        if not is_valid_object_key(object_key):
            return _fail(mode, phase, step="object-key-validation", reason=REASON_INVALID_OBJECT_KEY, object_key=object_key)
        try:
            port = build_port(mode="double", double_root=double_root, environment=_key_environment(object_key))
        except Exception as exc:  # noqa: BLE001
            return _fail(mode, phase, step="build-port", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc)
    elif mode == "live":
        gates = check_live_gates()
        if gates is not None:
            step, missing = gates
            if missing:
                exc = ProviderConfigError("missing config keys: " + ", ".join(missing))
                return _fail(mode, phase, step=step, reason=REASON_MISSING_CONFIG_KEY, object_key=object_key, error=exc)
            return _fail(mode, phase, step=step, reason=REASON_NOT_OPTED_IN, object_key=object_key)
        if not is_valid_object_key(object_key):
            return _fail(mode, phase, step="object-key-validation", reason=REASON_INVALID_OBJECT_KEY, object_key=object_key)
        try:
            port = build_port(mode="live", double_root=None, environment=_key_environment(object_key))
        except Exception as exc:  # noqa: BLE001
            return _fail(mode, phase, step="build-port", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    # --- 阶段分发 ---
    return _dispatch(port, mode=mode, phase=phase, object_key=object_key, content_seed=content_seed, content_bytes=content_bytes)


def _dispatch(port: Any, *, mode: str, phase: str, object_key: str, content_seed: str, content_bytes: int) -> SmokeResult:
    if phase == "write":
        data = smoke_bytes(content_seed, content_bytes)
        try:
            port.put(object_key, data, content_type=CONTENT_TYPE)
        except Exception as exc:  # noqa: BLE001
            code, rid = _sdk_identifiers(exc)
            return _fail(mode, phase, step="write", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc, code=code, request_id=rid)
        return _ok(mode, phase, nbytes=len(data), sha12=sha256_hex(data)[:12], object_key=object_key)

    if phase == "verify":
        try:
            present = bool(port.exists(object_key))
        except Exception as exc:  # noqa: BLE001
            code, rid = _sdk_identifiers(exc)
            return _fail(mode, phase, step="verify-exists", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc, code=code, request_id=rid)
        if not present:
            # verify 阶段对象缺失 ⇒ 失败，用专用 token object-missing（orchestrator 裁定，
            # 两侧统一）：adapter-error 会掩盖"对象确定不存在"这一确定事实。
            return _fail(mode, phase, step="verify-exists", reason=REASON_OBJECT_MISSING, object_key=object_key)
        expected = smoke_bytes(content_seed, content_bytes)
        try:
            actual = port.get(object_key)
        except Exception as exc:  # noqa: BLE001
            code, rid = _sdk_identifiers(exc)
            return _fail(mode, phase, step="verify-get", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc, code=code, request_id=rid)
        actual_sha = sha256_hex(actual)
        if len(actual) != len(expected):
            return _fail(mode, phase, step="verify-compare", reason=REASON_BYTES_MISMATCH, nbytes=len(actual), sha12=actual_sha[:12], object_key=object_key)
        if actual_sha != sha256_hex(expected):
            return _fail(mode, phase, step="verify-compare", reason=REASON_SHA_MISMATCH, nbytes=len(actual), sha12=actual_sha[:12], object_key=object_key)
        return _ok(mode, phase, nbytes=len(actual), sha12=actual_sha[:12], object_key=object_key)

    if phase == "delete":
        try:
            port.delete(object_key)  # 只删这一个精确键（契约 §8）
        except Exception as exc:  # noqa: BLE001
            code, rid = _sdk_identifiers(exc)
            return _fail(mode, phase, step="delete", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc, code=code, request_id=rid)
        return _ok(mode, phase, object_key=object_key)

    if phase == "confirm-absent":
        try:
            present = bool(port.exists(object_key))
        except Exception as exc:  # noqa: BLE001
            code, rid = _sdk_identifiers(exc)
            return _fail(mode, phase, step="confirm-absent", reason=REASON_ADAPTER_ERROR, object_key=object_key, error=exc, code=code, request_id=rid)
        if present:
            return _fail(mode, phase, step="confirm-absent", reason=REASON_STILL_EXISTS, object_key=object_key)
        return _ok(mode, phase, reason=REASON_ABSENT_CONFIRMED, object_key=object_key)

    raise ValueError(f"unknown phase: {phase!r}")


# --------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oss_live_smoke.py",
        description=(
            "B 真实 OSS 跨语言 smoke —— Python 侧阶段运行器。"
            "输出行契约见 .coordination/B-work/oss-live-smoke/contract.md §4。"
        ),
        epilog=(
            "注意：--config 在 Python 侧被忽略（仅 Java 侧读取私有 YAML）；"
            "Python 只读环境变量 MVP_D_STORAGE_PROVIDER / MVP_A_STORAGE_OSS_* / "
            "MVP_OSS_LIVE_SMOKE，因此不会因此报错。"
        ),
    )
    parser.add_argument("--mode", choices=("live", "double"), required=True)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--object-key", default="")
    parser.add_argument("--content-seed", default="")
    parser.add_argument("--content-bytes", type=int, default=DEFAULT_CONTENT_BYTES)
    parser.add_argument("--double-root", default=None)
    parser.add_argument("--config", default=None, help="Python 侧忽略（改读环境变量）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.config:
        print(
            "[oss-smoke-note] side=python note=config-ignored-python-reads-env",
            file=sys.stderr,
        )
    outcome = run_phase(
        mode=args.mode,
        phase=args.phase,
        object_key=args.object_key,
        content_seed=args.content_seed,
        content_bytes=args.content_bytes,
        double_root=args.double_root,
    )
    for line in outcome.lines:
        print(line)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
