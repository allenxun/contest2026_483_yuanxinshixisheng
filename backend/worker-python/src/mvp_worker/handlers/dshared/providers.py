"""供应商端口 + 可控替身 + 阿里云形状边界 + 工厂（生产 fail-closed）。

设计要点（DD 9.3 / 人脸调研 §4）：

- 端口是 Protocol：``FacePort`` / ``SkinPort`` / ``PlanPort``；handler 只依赖端口，
  测试注入 ``*Double``，生产由阿里云适配器替换。
- 替身确定性、可注错（fault injection），只产生合成数据，绝不产生虚假业务因果。
- 工厂从 env 解析（``MVP_D_*_PROVIDER``）；``environment == 'production'`` 且解析为
  ``double`` 时**立即抛错**，替身永不进生产。
- 阿里云适配器实现了与调研文档一致的**方法边界与配置读取**，但在没有总协调授权
  凭据 + PoC 时每个调用都抛 :class:`ProviderNotActivated`（映射为可重试
  DEPENDENCY_UNAVAILABLE），**不伪造结果、不产生虚假业务效果**。
"""
from __future__ import annotations

import base64
import hashlib
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from .dconfig import (
    DEFAULT_PLAN_CAPABILITY_BASELINE,
    DConfig,
    ProviderConfigError,
    production_environment_signals,
)
from ...media.storage import (
    AliyunOssStorage,
    FilesystemStorageDouble,
    OSS_ACCESS_KEY_ID_ENV,
    OSS_ACCESS_KEY_SECRET_ENV,
    OSS_BUCKET_ENV,
    OSS_PUBLIC_ENDPOINT_ENV,
    OSS_SERVER_ENDPOINT_ENV,
    STORAGE_PROVIDER_ALIYUN_OSS,
    STORAGE_PROVIDER_DOUBLE,
)

# ---------------------------------------------------------------- errors


class ProviderUnavailable(RuntimeError):
    """瞬时依赖不可用（网络/超时/5xx）→ handler 映射为可重试失败。"""


class ProviderNotActivated(ProviderUnavailable):
    """适配器尚未真实激活（无授权凭据/未过 PoC）→ 可重试，不伪造结果。"""


# ``ProviderConfigError`` 定义在 ``dconfig``（避免循环依赖），此处重导出以保证既有
# ``from ...providers import ProviderConfigError`` 不变。

# ---------------------------------------------------------------- result values


@dataclass(frozen=True)
class QualityResult:
    status: str  # accepted | needs_retake
    required_views: tuple[str, ...] = ()


@dataclass(frozen=True)
class SamePersonResult:
    ok: bool


@dataclass(frozen=True)
class SearchResult:
    classification: str  # matched | uncertain | ambiguous | reliable_new
    face_subject_ref: Optional[str] = None


@dataclass(frozen=True)
class RegisterResult:
    status: str  # success | timeout | unknown | failed


@dataclass(frozen=True)
class RegistrationQueryResult:
    status: str  # registered | not_found | unknown


@dataclass(frozen=True)
class SkinAnalysisResult:
    conclusion: str
    metrics: list[dict[str, Any]]
    description: str
    result_images: list[dict[str, Any]]  # {ref, bytes|provider_uri, caption}
    model_version: str


@dataclass
class PlanCandidate:
    description: str
    steps: list[dict[str, Any]]
    target_count: Any  # 故意宽松：由 handler 严格校验（可能注入非法形状）
    model_version: str


# ---------------------------------------------------------------- ports


@runtime_checkable
class FacePort(Protocol):
    provider_name: str
    model_version: str

    def quality(self, images: dict[str, bytes]) -> QualityResult: ...
    def same_person(self, images: dict[str, bytes]) -> SamePersonResult: ...
    def search_1n(self, namespace: str, images: dict[str, bytes]) -> SearchResult: ...
    def register_person(
        self,
        namespace: str,
        entity_id: str,
        images: dict[str, bytes],
        correlation_id: str,
        provider_request_id: str,
    ) -> RegisterResult: ...
    def query_registration(
        self,
        correlation_id: str,
        provider_request_id: str,
        *,
        namespace: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> RegistrationQueryResult: ...


@runtime_checkable
class SkinPort(Protocol):
    provider_name: str
    model_version: str

    def analyze(self, images: dict[str, bytes]) -> SkinAnalysisResult: ...


@runtime_checkable
class PlanPort(Protocol):
    provider_name: str
    model_version: str

    def generate(
        self, report_context: dict[str, Any], input_snapshot: dict[str, Any]
    ) -> PlanCandidate: ...


# ---------------------------------------------------------------- fault helper


class _FaultInjector:
    """按方法名预置异常队列：测试可让第 N 次外部调用抛指定异常。"""

    def __init__(self, faults: Optional[dict[str, list[BaseException]]] = None) -> None:
        self._faults: dict[str, list[BaseException]] = {
            k: list(v) for k, v in (faults or {}).items()
        }

    def maybe_raise(self, method: str) -> None:
        pending = self._faults.get(method)
        if pending:
            raise pending.pop(0)


# ---------------------------------------------------------------- doubles

_ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def default_late_barrier_dir() -> str:
    """``LateReturnBarrier`` **显式构造**时的目录缺省（仅供测试/手工构造使用）。

    注意：env 装配路径（``DConfig.double_late_barrier_dir``）在
    ``MVP_D_DOUBLE_LATE_BARRIER=true`` 时**强制要求非空独立目录**，绝不会走到本回退；
    因此不存在"两个并行运行共享默认临时目录"的串扰路径。
    """
    return os.path.join(tempfile.gettempdir(), "mvp-double-late-barrier")


class LateReturnBarrier:
    """文件式、一次性、有界的"先算后等"barrier（仅测试注入；默认关闭）。

    用于 SC-02-09「旧结果迟到」：命中标记的**首次** provider 调用先把旧结果算好，
    再阻塞等待释放；释放后返回**入 barrier 前算好的旧结果**（不重算）。后续命中
    标记的调用（如接管者 B）看到 ``consumed`` 立即返回，故 B 不被阻塞。

    - 命中标记来自**输入照片内容**的 sha256（不改端口签名）；
    - 状态只在文件（``consumed`` / ``released``），不写任何 DB 业务表；
    - 有界：等待上限 ``timeout_seconds``、百毫秒轮询；超时清理并抛既有
      :class:`ProviderUnavailable`（走既有可重试路径），绝不永久挂起；
    - 释放/超时后清理本目录内 sentinel，不留残留影响后续测试。
    """

    _CONSUMED = "consumed"
    _RELEASED = "released"
    _POLL_SECONDS = 0.1

    def __init__(self, *, directory: str, marker_sha256: str, timeout_seconds: int) -> None:
        self._dir = Path(directory or default_late_barrier_dir())
        self._marker = marker_sha256.strip().lower()
        self._timeout = float(timeout_seconds)

    def matches(self, images: Mapping[str, bytes]) -> bool:
        if not self._marker:
            return False
        for data in images.values():
            if isinstance(data, (bytes, bytearray)):
                if hashlib.sha256(bytes(data)).hexdigest() == self._marker:
                    return True
        return False

    def compute_then_wait(self, images: Mapping[str, bytes], result: Any) -> Any:
        """返回调用方**已算好**的旧结果；命中且首次时先等后返回，超时抛错。"""
        if not self.matches(images):
            return result
        self._dir.mkdir(parents=True, exist_ok=True)
        consumed = self._dir / self._CONSUMED
        try:
            fd = os.open(str(consumed), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            return result  # 已被消费：接管者/后续调用不阻塞
        released = self._dir / self._RELEASED
        deadline = time.monotonic() + self._timeout
        try:
            while True:
                if released.exists():
                    return result
                if time.monotonic() >= deadline:
                    raise ProviderUnavailable(
                        "late-return barrier timed out waiting for release sentinel"
                    )
                time.sleep(self._POLL_SECONDS)
        finally:
            for path in (consumed, released):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass


class FaceDouble:
    """确定性人脸替身；测试可注入 search 分类、登记/对账行为与瞬时异常。"""

    provider_name = "double"
    model_version = "face-double-1"

    def __init__(
        self,
        *,
        search: str = "reliable_new",
        face_subject_ref: Optional[str] = None,
        same_person: bool = True,
        quality: str = "accepted",
        required_views: Optional[tuple[str, ...]] = None,
        register: str = "success",
        query: str = "registered",
        faults: Optional[dict[str, list[BaseException]]] = None,
        barrier: Optional[LateReturnBarrier] = None,
    ) -> None:
        self._search = search
        self._face_subject_ref = face_subject_ref
        self._same_person = same_person
        self._quality = quality
        self._required_views = required_views
        self._register = register
        self._query = query
        self._faults = _FaultInjector(faults)
        self._barrier = barrier
        self.calls: dict[str, int] = {}
        self.registered: dict[str, str] = {}

    def _tick(self, method: str) -> None:
        self.calls[method] = self.calls.get(method, 0) + 1

    def quality(self, images: dict[str, bytes]) -> QualityResult:
        self._tick("quality")
        self._faults.maybe_raise("quality")
        if self._quality == "needs_retake":
            views = tuple(self._required_views) if self._required_views else ("front",)
            result = QualityResult("needs_retake", views)
        else:
            result = QualityResult("accepted", ())
        if self._barrier is not None:
            # 先算后等：result 已在入 barrier 前算出，释放后原样返回（不重算）。
            result = self._barrier.compute_then_wait(images, result)
        return result

    def same_person(self, images: dict[str, bytes]) -> SamePersonResult:
        self._tick("same_person")
        self._faults.maybe_raise("same_person")
        return SamePersonResult(bool(self._same_person))

    def search_1n(self, namespace: str, images: dict[str, bytes]) -> SearchResult:
        self._tick("search_1n")
        self._faults.maybe_raise("search_1n")
        if namespace in self.registered:
            return SearchResult("matched", self.registered[namespace])
        if self._search == "dependency_failed":
            raise ProviderUnavailable("face search unavailable")
        if self._search == "matched":
            return SearchResult("matched", self._face_subject_ref)
        return SearchResult(self._search)

    def register_person(
        self,
        namespace: str,
        entity_id: str,
        images: dict[str, bytes],
        correlation_id: str,
        provider_request_id: str,
    ) -> RegisterResult:
        self._tick("register_person")
        self._faults.maybe_raise("register_person")
        if self._register == "success":
            self.registered[namespace] = entity_id
            return RegisterResult("success")
        if self._register == "timeout":
            return RegisterResult("timeout")
        if self._register == "unknown":
            return RegisterResult("unknown")
        return RegisterResult("failed")

    def query_registration(
        self,
        correlation_id: str,
        provider_request_id: str,
        *,
        namespace: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> RegistrationQueryResult:
        self._tick("query_registration")
        self._faults.maybe_raise("query_registration")
        if self._query == "registered":
            if namespace is not None and entity_id is not None:
                self.registered[namespace] = entity_id
            return RegistrationQueryResult("registered")
        if self._query == "not_found":
            return RegistrationQueryResult("not_found")
        return RegistrationQueryResult("unknown")


class SkinDouble:
    """确定性测肤替身；默认产出与受控指标基线一致的结果，可注入契约违约形状。"""

    provider_name = "double"
    model_version = "skin-double-1"

    def __init__(
        self,
        *,
        conclusion: str = "balanced",
        metrics: Optional[list[dict[str, Any]]] = None,
        description: str = "double skin analysis",
        result_images: Optional[list[dict[str, Any]]] = None,
        invalid: Optional[str] = None,
        faults: Optional[dict[str, list[BaseException]]] = None,
    ) -> None:
        self._conclusion = conclusion
        self._metrics = metrics
        self._description = description
        self._result_images = result_images
        self._invalid = invalid
        self._faults = _FaultInjector(faults)
        self.calls: dict[str, int] = {}

    def analyze(self, images: dict[str, bytes]) -> SkinAnalysisResult:
        self.calls["analyze"] = self.calls.get("analyze", 0) + 1
        self._faults.maybe_raise("analyze")
        metrics = (
            [dict(m) for m in self._metrics]
            if self._metrics is not None
            else [
                {"name": "moisture", "value": 55.0, "unit": "percent"},
                {"name": "oiliness", "value": 42.0, "unit": "percent"},
                {"name": "smoothness", "value": 70.0, "unit": "score"},
            ]
        )
        result_images = (
            [dict(i) for i in self._result_images]
            if self._result_images is not None
            else [
                {"ref": "skin-result-1", "bytes": _ONE_PX_PNG, "caption": "结果图 1"},
                {"ref": "skin-result-2", "bytes": _ONE_PX_PNG, "caption": "结果图 2"},
            ]
        )
        self._apply_invalid(metrics)
        return SkinAnalysisResult(
            conclusion=self._conclusion,
            metrics=metrics,
            description=self._description,
            result_images=result_images,
            model_version=self.model_version,
        )

    def _apply_invalid(self, metrics: list[dict[str, Any]]) -> None:
        mode = self._invalid
        if mode == "unknown_metric":
            metrics.append({"name": "unapproved_metric", "value": 1.0, "unit": "score"})
        elif mode == "out_of_range":
            metrics.append({"name": "moisture", "value": 999.0, "unit": "percent"})
        elif mode == "bad_unit":
            metrics.append({"name": "moisture", "value": 50.0, "unit": "liter"})


class PlanDouble:
    """确定性方案替身；默认产出与受控能力基线一致的可验证方案。"""

    provider_name = "double"
    model_version = "plan-double-1"

    def __init__(
        self,
        *,
        target_count: Any = 30,
        steps: Optional[list[dict[str, Any]]] = None,
        description: str = "double generated care plan",
        invalid: Optional[str] = None,
        faults: Optional[dict[str, list[BaseException]]] = None,
    ) -> None:
        ranges = DEFAULT_PLAN_CAPABILITY_BASELINE["parameter_ranges"]
        self._target_count = target_count
        self._steps = steps
        self._description = description
        self._invalid = invalid
        self._ranges = ranges
        self._faults = _FaultInjector(faults)
        self.calls: dict[str, int] = {}

    def generate(
        self, report_context: dict[str, Any], input_snapshot: dict[str, Any]
    ) -> PlanCandidate:
        self.calls["generate"] = self.calls.get("generate", 0) + 1
        self._faults.maybe_raise("generate")
        steps = (
            [dict(s) for s in self._steps]
            if self._steps is not None
            else [
                {"step_id": "step-1", "region": "forehead",
                 "parameters": {"intensity": 40, "duration": 120}},
                {"step_id": "step-2", "region": "left_cheek",
                 "parameters": {"intensity": 30, "duration": 90}},
            ]
        )
        candidate = PlanCandidate(
            description=self._description,
            steps=steps,
            target_count=self._target_count,
            model_version=self.model_version,
        )
        self._apply_invalid(candidate)
        return candidate

    def _apply_invalid(self, candidate: PlanCandidate) -> None:
        mode = self._invalid
        if mode is None:
            return
        if mode == "n_zero":
            candidate.target_count = 0
        elif mode == "n_too_large":
            candidate.target_count = int(
                DEFAULT_PLAN_CAPABILITY_BASELINE["n_bounds"]["max"]
            ) + 9999
        elif mode == "n_string_garbage":
            candidate.target_count = "not-a-number"
        elif mode == "n_string_ok":
            candidate.target_count = str(candidate.target_count)
        elif mode == "empty_steps":
            candidate.steps = []
        elif mode == "unknown_region":
            candidate.steps[0]["region"] = "unapproved_region"
        elif mode == "param_out_of_range":
            candidate.steps[0]["parameters"]["intensity"] = 10_000
        elif mode == "unknown_param":
            candidate.steps[0]["parameters"]["laser_power"] = 5
        elif mode == "extra_property":
            candidate.steps[0]["extra"] = "unexpected"
        elif mode == "bad_parameters_shape":
            candidate.steps[0]["parameters"] = "not-an-object"


# ---------------------------------------------------------------- aliyun boundary


class _AliyunAdapterBase:
    """阿里云适配器公共基类：只读 env 配置，未激活时调用即拒绝。"""

    provider_name = "aliyun"

    def __init__(self, cfg: DConfig) -> None:
        self._cfg = cfg

    def _ensure_activated(self) -> None:
        cfg = self._cfg
        if not (
            cfg.aliyun_activated
            and cfg.aliyun_endpoint
            and cfg.aliyun_access_key_id
            and cfg.aliyun_access_key_secret
        ):
            raise ProviderNotActivated(
                "aliyun adapter not activated: requires coordinator-authorized "
                "credentials + PoC (env MVP_D_ALIYUN_ACTIVATED / endpoint / AK / SK)"
            )


class AliyunFaceAdapter(_AliyunAdapterBase):
    """阿里云人脸边界（方法映射见 docstring；未激活不产生任何结果）。

    - ``quality`` → 图片质量检查（SearchFace/DetectLivingFace 前置，PoC 待定）；
    - ``same_person`` → ``CompareFace``（当前照 vs 成员可信参考照）；
    - ``search_1n`` → ``SearchFace``（受控人员库范围）；
    - ``register_person`` → ``AddFaceEntity`` + ``AddFace``（EntityId 稳定引用）；
    - ``query_registration`` → 按 EntityId 查询登记可见性（对账）。
    """

    model_version = "aliyun-face-poc-pending"

    def quality(self, images: dict[str, bytes]) -> QualityResult:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun face quality not implemented")

    def same_person(self, images: dict[str, bytes]) -> SamePersonResult:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun CompareFace not implemented")

    def search_1n(self, namespace: str, images: dict[str, bytes]) -> SearchResult:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun SearchFace not implemented")

    def register_person(
        self,
        namespace: str,
        entity_id: str,
        images: dict[str, bytes],
        correlation_id: str,
        provider_request_id: str,
    ) -> RegisterResult:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun AddFaceEntity/AddFace not implemented")

    def query_registration(
        self,
        correlation_id: str,
        provider_request_id: str,
        *,
        namespace: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> RegistrationQueryResult:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun registration query not implemented")


class AliyunSkinAdapter(_AliyunAdapterBase):
    """阿里云测肤边界（真实接口待算法团队确认；未激活不产生结果）。"""

    model_version = "aliyun-skin-poc-pending"

    def analyze(self, images: dict[str, bytes]) -> SkinAnalysisResult:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun skin analysis not implemented")


class AliyunPlanAdapter(_AliyunAdapterBase):
    """阿里云/大模型方案边界（LLM 契约待验证；未激活不产生结果）。

    真实实现需向模型提交冻结报告摘要与能力快照，并要求 **严格结构化输出**，
    handler 仍会在发布前做白名单校验（永不信赖模型原始输出）。
    """

    model_version = "aliyun-llm-poc-pending"

    def generate(
        self, report_context: dict[str, Any], input_snapshot: dict[str, Any]
    ) -> PlanCandidate:
        self._ensure_activated()
        raise ProviderNotActivated("aliyun LLM plan generation not implemented")


# ---------------------------------------------------------------- factory


def _forbid_double_in_production(environment: str, provider: str) -> None:
    if environment == "production" and provider == "double":
        raise ProviderConfigError(
            "double provider is forbidden in production (fail-closed)"
        )


def _face_double_from_config(cfg: DConfig) -> FaceDouble:
    """按 env 装配 face 替身注入缝（默认值 = 当前行为；仅 double 分支读取）。

    - ``quality=needs_retake`` + ``required_views`` → 质量不合格正例；
    - ``same_person=false`` → NOT_SAME_PERSON；
    - ``search`` ∈ reliable_new/matched/uncertain/ambiguous/dependency_failed。

    - ``MVP_D_DOUBLE_LATE_BARRIER`` → 首个命中标记的 ``quality`` 调用先算后等（SC-02-09）。

    "旧分析完成时机"另见 ``_skin_double_from_config``（``MVP_D_SKIN_DOUBLE_HOLD``），
    两者关系：hold 是进程级可重试失败（无输入标记）；barrier 是输入标记驱动、
    先算后等的真实迟到返回（更贴合 SC-02-09），可并存。
    """
    barrier: Optional[LateReturnBarrier] = None
    if cfg.double_late_barrier:
        barrier = LateReturnBarrier(
            directory=cfg.double_late_barrier_dir,
            marker_sha256=cfg.double_late_barrier_sha256,
            timeout_seconds=cfg.double_late_barrier_timeout_seconds,
        )
    return FaceDouble(
        search=cfg.face_double_search,
        same_person=cfg.face_double_same_person,
        quality=cfg.face_double_quality,
        required_views=tuple(cfg.face_double_required_views),
        barrier=barrier,
    )


def _plan_double_from_config(cfg: DConfig) -> PlanDouble:
    """按 env 装配 plan 替身注入缝（默认=当前行为；非法取值已在 DConfig 校验）。"""
    mode = cfg.plan_double_mode
    if mode == "valid":
        return PlanDouble()
    if mode == "timeout":
        # 既有瞬时异常分类（非真实 sleep）→ handler 映射为可重试 DEPENDENCY_UNAVAILABLE，
        # attempt 预算耗尽后经 _transient_or_terminal 落终态 failed（确定性）。
        return PlanDouble(
            faults={"generate": [ProviderUnavailable("plan double: injected timeout")]}
        )
    if mode == "failure":
        return PlanDouble(
            faults={"generate": [RuntimeError("plan double: injected provider failure")]}
        )
    return PlanDouble(invalid=mode)  # PlanDouble 既有非法形状


def build_face_port(cfg: DConfig, *, environment: str) -> FacePort:
    provider = cfg.face_provider
    if provider == "double":
        _forbid_double_in_production(environment, provider)
        return _face_double_from_config(cfg)
    if provider == "aliyun_face":
        return AliyunFaceAdapter(cfg)
    raise ProviderConfigError(f"unknown face provider: {provider}")


def _skin_double_from_config(cfg: DConfig) -> SkinDouble:
    """按 env 装配 skin 替身；``MVP_D_SKIN_DOUBLE_HOLD=true`` 为**进程级 hold**。

    hold 复用既有可重试失败语义（``ProviderUnavailable`` → handler 映射为可重试
    ``DEPENDENCY_UNAVAILABLE``，job 退避重排队）：旧分析停在可释放态，不 sleep、
    不改 DB、不改业务判定。端口无 task/照片版本入参，故只能进程级（E 用
    ``worker_once(env_extra=...)`` 逐次控制时机）。

    ``MVP_D_SKIN_DOUBLE_INVALID``：返回违反既有指标白名单/基线的指标 → handler 经
    既有 ``_ContractViolation`` 落 **PROVIDER_CONTRACT_VIOLATION** 终态（确定性，1 次）。
    """
    invalid = None if cfg.skin_double_invalid == "none" else cfg.skin_double_invalid
    if cfg.skin_double_hold:
        return SkinDouble(
            invalid=invalid,
            faults={"analyze": [ProviderUnavailable("analyze hold: injected retryable hold")]},
        )
    return SkinDouble(invalid=invalid)


def build_skin_port(cfg: DConfig, *, environment: str) -> SkinPort:
    provider = cfg.skin_provider
    if provider == "double":
        _forbid_double_in_production(environment, provider)
        return _skin_double_from_config(cfg)
    if provider == "aliyun_skin":
        return AliyunSkinAdapter(cfg)
    raise ProviderConfigError(f"unknown skin provider: {provider}")


def build_plan_port(cfg: DConfig, *, environment: str) -> PlanPort:
    provider = cfg.plan_provider
    if provider == "double":
        _forbid_double_in_production(environment, provider)
        return _plan_double_from_config(cfg)
    if provider == "aliyun_llm":
        return AliyunPlanAdapter(cfg)
    raise ProviderConfigError(f"unknown plan provider: {provider}")


# ---------------------------------------------------------------- storage factory


def _forbid_storage_double_in_production(environment: str) -> None:
    """存储替身生产 fail-closed（对齐 ``_forbid_double_in_production`` 语义）。

    - 传入 ``environment`` 为 production/prod → 拒绝；
    - ``production_environment_signals()`` 命中也拒绝（resolved_environment /
      ``MVP_NOTIFY_ENV``/``MVP_WORKER_ENVIRONMENT``/``APP_ENV``/prod profile），
      覆盖与 Java 混合 profile 场景，避免仅凭单一 env 漏判。
    **绝不**回退到本地文件系统。
    """
    normalized = environment.strip().lower()
    if normalized in ("production", "prod"):
        raise ProviderConfigError(
            "double storage provider is forbidden in production (fail-closed)"
        )
    signals = production_environment_signals()
    if signals:
        raise ProviderConfigError(
            "double storage provider is forbidden in production (fail-closed;"
            f" signals: {signals})"
        )


def _require_oss_config(cfg: DConfig) -> None:
    """``aliyun_oss`` 必填项校验：消息只列**缺失的键名**，绝不回显任何取值。

    endpoint 拆为 server/public 两项且都必填；旧单 endpoint 键已移除，缺失时在消息中
    给出迁移提示（点名两个新键），**不读取、不 fallback** 旧键。
    """
    missing: list[str] = []
    if not cfg.oss_bucket.strip():
        missing.append(OSS_BUCKET_ENV)
    if not cfg.oss_access_key_id.strip():
        missing.append(OSS_ACCESS_KEY_ID_ENV)
    if not cfg.oss_access_key_secret.strip():
        missing.append(OSS_ACCESS_KEY_SECRET_ENV)
    missing_endpoints: list[str] = []
    if not cfg.oss_server_endpoint.strip():
        missing_endpoints.append(OSS_SERVER_ENDPOINT_ENV)
    if not cfg.oss_public_endpoint.strip():
        missing_endpoints.append(OSS_PUBLIC_ENDPOINT_ENV)
    if not missing and not missing_endpoints:
        return
    parts: list[str] = []
    if missing:
        parts.append("requires non-empty config: " + ", ".join(missing))
    if missing_endpoints:
        parts.append("requires non-empty endpoint config: " + ", ".join(missing_endpoints))
    message = "aliyun_oss storage provider " + "; ".join(parts)
    if missing_endpoints:
        message += (
            " (endpoint config was split into server/public endpoints; migrate the"
            " legacy single-endpoint setting to these two keys)"
        )
    raise ProviderConfigError(message)


def build_storage_port(
    cfg: DConfig, *, environment: str, dev_dir: str | None = None
) -> Any:
    """按 ``MVP_D_STORAGE_PROVIDER`` 选择存储实现（按服务独立，与 Java 一致选择）。

    - ``double``（默认）→ :class:`FilesystemStorageDouble`；生产拒绝；
    - ``aliyun_oss`` → :class:`AliyunOssStorage`（私有桶，真实元数据；缺字段 → 明确报错）；
    - 其它 → :class:`ProviderConfigError`。
    """
    provider = cfg.storage_provider
    if provider == STORAGE_PROVIDER_DOUBLE:
        _forbid_storage_double_in_production(environment)
        return FilesystemStorageDouble(dev_dir)
    if provider == STORAGE_PROVIDER_ALIYUN_OSS:
        _require_oss_config(cfg)
        return AliyunOssStorage(
            region=cfg.oss_region,
            server_endpoint=cfg.oss_server_endpoint.strip(),
            public_endpoint=cfg.oss_public_endpoint.strip(),
            bucket_name=cfg.oss_bucket.strip(),
            access_key_id=cfg.oss_access_key_id.strip(),
            access_key_secret=cfg.oss_access_key_secret.strip(),
            security_token=cfg.oss_security_token.strip() or None,
        )
    raise ProviderConfigError(f"unknown storage provider: {provider}")
