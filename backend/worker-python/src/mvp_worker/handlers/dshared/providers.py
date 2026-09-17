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
import json
import os
import socket
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, NoReturn, Optional, Protocol, runtime_checkable
from urllib.parse import quote, urlencode

from . import dliveness, weijing_mapping
from .constants import REQUIRED_VIEWS_ALL
from .dconfig import (
    DEFAULT_PLAN_CAPABILITY_BASELINE,
    DConfig,
    FACE_SERVICE_BASE_URL_ENV,
    FACE_SERVICE_NAMESPACE_ENV,
    FACE_SERVICE_TOKEN_FILE_ENV,
    ProviderConfigError,
    production_environment_signals,
)
from .dtokenfile import read_token_file
from .dskin_mock import (
    V3_SKIN_MOCK_GROUPS,
    V3_SKIN_MOCK_MODEL_VERSION,
)
from .dtransport import (
    FaceServiceHttpError,
    FaceServiceTimeout,
    FaceServiceTransport,
    FaceServiceTransportError,
    StdlibHttpTransport,
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
    """适配器尚未真实激活（无授权凭据/未过 PoC/自动登记门未开）→ 可重试，不伪造结果。"""


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
    #: 可选 V3 三组评分载荷（``pores``/``spots``/``surface_gloss``，all-or-none）。
    #: 默认 ``None`` = 不携带（既有替身/流程行为不变）。真实 provider 未来可填充。
    v3_groups: Optional[dict[str, Any]] = None


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
        v3_groups: Optional[dict[str, Any]] = None,
        model_version: Optional[str] = None,
    ) -> None:
        self._conclusion = conclusion
        self._metrics = metrics
        self._description = description
        self._result_images = result_images
        self._invalid = invalid
        self._faults = _FaultInjector(faults)
        # 构造期即深拷贝：调用方事后改动**传入的 dict** 不得影响后续结果
        # （返回结果另经 analyze 内的逐调用深拷贝隔离）。
        self._v3_groups = (
            json.loads(json.dumps(v3_groups)) if v3_groups is not None else None
        )
        if model_version is not None:
            self.model_version = model_version
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
        # 每次调用返回独立深拷贝（调用方/发布方改动互不影响；构造期已另做一次深拷贝）。
        v3_groups = (
            json.loads(json.dumps(self._v3_groups)) if self._v3_groups is not None else None
        )
        return SkinAnalysisResult(
            conclusion=self._conclusion,
            metrics=metrics,
            description=self._description,
            result_images=result_images,
            model_version=self.model_version,
            v3_groups=v3_groups,
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


# ---------------------------------------------------------------- insightface boundary


class InsightFaceAdapter:
    """face-service（insightface）HTTP 边界 —— phase 2 真实绑定冻结合同。

    权威来源：``backend/handoffs/B-face-service-worker-contract.md``（合同，最终代码
    SHA ``bec9eb97``）。最终架构裁定：Worker 仍是身份协调者——``assessment_analyze``
    的 quality/same_person/search_1n + member/identity 决策与 ``identity_enroll`` 的
    register/query/``face_subject_ref``/member 绑定全部保留，本类只做协议映射。

    **能力边界（必须明示）**：本类的人脸结论是**照片比对，无防翻拍能力**；服务端
    ``liveness.supported`` **恒 false**，相似度**不是**活体证明（合同 §7）。本类**永不**
    发送 ``require_liveness``（见 :mod:`dliveness`），**永不**产出“liveness passed”，
    也**永不**因服务诚实报告 ``supported=false`` 而判失败。

    **硬性纪律**：真实服务故障**绝不**回退 ``FaceDouble`` 成功；``ProviderNotActivated``
    用于“未授权/未过 PoC/自动登记门未开”，绝不伪造结果；出站请求**绝不**携带客户端
    阈值或 ``on_exists``；异常/日志**绝不**含 token、图片字节、embedding 或
    namespace/subject_id/correlation_id 取值。

    phase 2 绑定决策（逐条对应合同 §8）：

    - ``quality``：逐视角（``REQUIRED_VIEWS_ALL`` 规范序）各调一次 ``POST /v1/quality``；
      全部 ``quality.min_acceptable=true`` → ``accepted``，否则 ``needs_retake``（不合格
      视角元组，规范序）。**确定性图像内容 400**（``NO_FACE`` /
      ``MULTI_FACES_AMBIGUOUS`` / ``IMAGE_DECODE_FAILED``）按“该视角不合格”处理 → 补拍
      （总协调裁定 2026-09-17；见 ``_QUALITY_CONTENT_FAILURE_CODES``）。其余失败仍抛错：
      传输/超时/5xx/其它 4xx/结构非法 2xx → ``ProviderUnavailable``，鉴权 →
      ``ProviderConfigError``；**瞬时优先**——任一视角抛出失败即中止整个 op（不在其它
      视角状态未知时得出 needs_retake）。绝不把失败当合格（合同 §3/§8 + 裁定）。
    - ``same_person``：**front 锚定的两两比较**（front-vs-left、front-vs-right 两次
      ``POST /v1/compare``）。选择该策略而非 left-vs-right 的理由：把共同参考帧
      （front）作为比较锚点，使“三视角同人”退化为两个共享锚点的独立比较，避免在缺少
      共同锚点时比较两帧侧脸；也是合同 §3 建议的“对着主视角比”。两次都 must-run，
      任一调用失败 → ``ProviderUnavailable``；全部 ``matched=true`` → ``True``，任一
      ``false`` → ``False``（合同 §8）。
    - ``search_1n``：``POST /v1/namespaces/{ns}/search``（用 front 主参考视角，合同 §3），
      ``decision`` ∈ {matched,uncertain,reliable_new} **直接**作为 ``classification``
      （服务端用 ``uncertain``+``ambiguous=true`` 表达歧义，不产出 ``ambiguous``，
      合同 §4.2）；``matched`` → ``face_subject_ref=subject_id``；4xx 参数/鉴权类 →
      ``ProviderConfigError``，5xx/429/504/``MODEL_*``/``STORE_UNAVAILABLE``/超时/传输 →
      ``ProviderUnavailable``（合同 §8）。
    - ``register_person``：**自动登记门**（``MVP_D_FACE_SERVICE_AUTO_ENROLL``，默认
      false；合同 §4.2 裁定 2）关闭时**零网络**抛 ``ProviderNotActivated``。开启时
      ``POST /v1/namespaces/{ns}/subjects``（``subject_id=entity_id``，带
      ``correlation_id``/``provider_request_id``；不传 ``on_exists``/``require_liveness``）；
      201/200 → ``success``、409 → ``failed``、客户端超时 → ``timeout``、
      5xx/``MODEL_*``/``STORE_UNAVAILABLE`` → ``unknown``、其它 4xx → ``failed``
      （合同 §6.1/§8）。
    - ``query_registration``：``GET /v1/namespaces/{ns}/registrations/{correlation_id}``
      （带 ``provider_request_id``/``entity_id`` 加强校验）；``status=registered`` →
      ``registered``、``not_found`` → ``not_found``、传输失败/无法解析/5xx → ``unknown``
      （``unknown`` 是**客户端**状态，服务端绝不产出，合同 §6.2/§8）。**404
      ``NAMESPACE_NOT_FOUND`` → ``not_found``**：合同 §6.2 明确对账查询针对的是**已经
      发起过**的登记，其 namespace 必然已存在，故 404 是“你查错了地方”的**确定性否定**
      ——该 namespace 内确无此登记，语义等价于 ``not_found``（两者在
      ``identity_enroll._reconcile`` 都走 ``ENROLLMENT_RECONCILE_PENDING`` 可重试）。
    """

    provider_name = "insightface"
    #: 服务在 ``model_version`` 中报告真实值；此处稳定占位（不在调用前猜测取值）。
    model_version = "insightface-face-service"

    #: 冻结合同 §4.2 的三值判定词表。
    _SEARCH_DECISIONS = frozenset({"matched", "uncertain", "reliable_new"})
    #: 合同 §4.3 冻结的响应键（除 matched 专有的 subject_id/similarity 外全部必在）。
    _SEARCH_FROZEN_KEYS = (
        "decision",
        "ambiguous",
        "quality",
        "reasons",
        "subject_count",
        "top_k",
        "policy_version",
        "model_version",
        "library_revision",
        "request_id",
    )
    #: 合同 §8：search 的 4xx **参数类** → 配置型终态（不可重试）；鉴权另行处理。
    _SEARCH_CONFIG_CODES = frozenset(
        {"INVALID_REQUEST", "IMAGE_DECODE_FAILED", "UNSUPPORTED_MEDIA_TYPE", "IMAGE_TOO_LARGE"}
    )
    #: 合同 §6.1：登记时这些码 → ``unknown``（随后对账）。
    _REGISTER_UNKNOWN_CODES = frozenset(
        {"MODEL_UNAVAILABLE", "MODEL_NOT_LOADED", "STORE_UNAVAILABLE"}
    )
    #: **总协调裁定 2026-09-17**：quality 阶段的**确定性图像内容** 400 码。
    #:
    #: 相同字节恒得相同 400（非瞬时），故该视角按“不合格”处理（等价
    #: ``min_acceptable=false``），最终由 handler 落**补拍**而非重试后 FAILED：
    #: ``assessment_analyze.py:268-274``（``_bounded_views`` 规范化 → 非 accepted →
    #: ``_retake_result(QUALITY_REJECTED)``）。
    #:
    #: 现场证据：``.mvp-d-runtime/live-8010/evidence.md``（真实 buffalo_l 对无脸照片
    #: 返回 400 ``NO_FACE``）。这是对合同 §8 字面「任一视角调用失败 → ProviderUnavailable」
    #: 的**经授权细化**（合同文件不由 D 修改；修订稿见交付报告）。
    #:
    #: 仅限 quality 阶段：``same_person`` / ``search_1n`` 的映射保持不变（不扩大范围）。
    _QUALITY_CONTENT_FAILURE_CODES = frozenset(
        {"NO_FACE", "MULTI_FACES_AMBIGUOUS", "IMAGE_DECODE_FAILED"}
    )

    def __init__(self, cfg: DConfig, transport: FaceServiceTransport) -> None:
        self._cfg = cfg
        self._transport = transport
        self._namespace = cfg.face_service_namespace.strip()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.b64encode(bytes(data)).decode("ascii")

    def _image_payload(self, data: bytes) -> dict[str, Any]:
        """单图请求体：``image_base64`` + 空活体参数（**永不**请求活体）。"""
        payload: dict[str, Any] = {"image_base64": self._b64(data)}
        payload.update(dliveness.adapter_liveness_request_params())
        return payload

    @staticmethod
    def _missing_view(op: str, view: str) -> NoReturn:
        raise ProviderUnavailable(f"insightface {op}: required view {view!r} missing")

    @staticmethod
    def _invalid_2xx(op: str, detail: str) -> NoReturn:
        raise ProviderUnavailable(f"insightface {op}: invalid 2xx response ({detail})")

    @staticmethod
    def _raise_unavailable(op: str, exc: BaseException) -> NoReturn:
        extra = ""
        if isinstance(exc, FaceServiceHttpError):
            extra = f", status={exc.status}, code={exc.code or 'unclassified'}"
        raise ProviderUnavailable(
            f"insightface {op} unavailable ({type(exc).__name__}{extra})"
        ) from exc

    @staticmethod
    def _raise_auth_config(op: str, exc: BaseException) -> NoReturn:
        # 只点名配置键，绝不回显 token/取值。
        raise ProviderConfigError(
            f"insightface {op}: authentication/config rejected; check "
            f"{FACE_SERVICE_TOKEN_FILE_ENV} (token file must match the service)"
        ) from exc

    @staticmethod
    def _raise_shape_config(op: str, exc: FaceServiceHttpError) -> NoReturn:
        raise ProviderConfigError(
            f"insightface {op}: request shape rejected "
            f"(status={exc.status}, code={exc.code or 'unclassified'})"
        ) from exc

    def _handle_http_error_strict_unavailable(
        self, op: str, exc: FaceServiceHttpError
    ) -> NoReturn:
        """quality/same_person：鉴权 → 配置型终态；其余（含 4xx）→ 可重试不可用。"""
        if exc.is_auth:
            self._raise_auth_config(op, exc)
        self._raise_unavailable(op, exc)

    # ------------------------------------------------------------ quality
    def quality(self, images: dict[str, bytes]) -> QualityResult:
        # 先做入参完整性校验（零网络 fail-closed），再逐视角调用。
        for view in REQUIRED_VIEWS_ALL:
            if images.get(view) is None:
                self._missing_view("quality", view)
        failing: list[str] = []
        for view in REQUIRED_VIEWS_ALL:
            if not self._quality_view_acceptable(view, images[view]):
                failing.append(view)
        if failing:
            return QualityResult("needs_retake", tuple(failing))
        return QualityResult("accepted", ())

    def _quality_view_acceptable(self, view: str, data: bytes) -> bool:
        try:
            result = self._transport.request(
                "POST", "/v1/quality", json_body=self._image_payload(data)
            )
        except FaceServiceHttpError as exc:
            if exc.is_auth:
                # 鉴权失败优先：配置型终态（即使同时是内容码也不可能，401 不含内容码）。
                self._raise_auth_config("quality", exc)
            if exc.code in self._QUALITY_CONTENT_FAILURE_CODES:
                # 确定性图像内容问题（同字节恒同 400）→ 该视角视为不合格，交补拍；
                # **绝不**当成合格，也**不**在此抛错。
                # 注意瞬时优先：本函数返回 False 后 quality() 会继续检查后续视角，
                # 若任一视角抛出任何其它失败，异常会向上传播并中止整个 quality()
                # （不会在“有视角状态未知”时得出 needs_retake；瞬时故障解除后重试收敛）。
                return False
            # 其它 4xx（INVALID_REQUEST/UNSUPPORTED_MEDIA_TYPE/IMAGE_TOO_LARGE…）与 5xx
            # 仍按既有语义抛可重试不可用。
            self._raise_unavailable("quality", exc)
        except FaceServiceTransportError as exc:
            self._raise_unavailable("quality", exc)
        body = result.json
        faces = body.get("faces") if isinstance(body, Mapping) else None
        if not isinstance(faces, list) or not faces:
            self._invalid_2xx("quality", "no faces in response")
        # 服务端 `largest_face_index` 恒为 `_largest_index(detections)`（api.py:531-556）：
        # 非空 faces 下必为范围内的 int。**绝不**静默修复非法值（Oracle BLOCKER 3）。
        index = body.get("largest_face_index")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not (0 <= index < len(faces))
        ):
            self._invalid_2xx("quality", "largest_face_index missing/invalid/out-of-range")
        face = faces[index]
        quality_block = face.get("quality") if isinstance(face, Mapping) else None
        min_acceptable = (
            quality_block.get("min_acceptable")
            if isinstance(quality_block, Mapping)
            else None
        )
        if not isinstance(min_acceptable, bool):
            self._invalid_2xx("quality", "min_acceptable missing/invalid")
        return bool(min_acceptable)

    # ------------------------------------------------------------ same_person
    def same_person(self, images: dict[str, bytes]) -> SamePersonResult:
        # 先做入参完整性校验（零网络 fail-closed），再调用两次比较。
        for view in REQUIRED_VIEWS_ALL:
            if images.get(view) is None:
                self._missing_view("same_person", view)
        front = images["front"]
        # 两次比较都执行：任一调用失败必须抛出（优先于 matched 结果），故不短路。
        matched = [
            self._compare("same_person", front, images[other], other)
            for other in ("left", "right")
        ]
        return SamePersonResult(all(matched))

    def _compare(self, op: str, image_a: Optional[bytes], image_b: Optional[bytes], view: str) -> bool:
        if image_b is None:
            self._missing_view(op, view)
        payload: dict[str, Any] = {
            "image_a_base64": self._b64(image_a),  # type: ignore[arg-type]
            "image_b_base64": self._b64(image_b),
        }
        payload.update(dliveness.adapter_liveness_request_params())
        try:
            result = self._transport.request("POST", "/v1/compare", json_body=payload)
        except FaceServiceHttpError as exc:
            self._handle_http_error_strict_unavailable(op, exc)
        except FaceServiceTransportError as exc:
            self._raise_unavailable(op, exc)
        body = result.json
        matched = body.get("matched") if isinstance(body, Mapping) else None
        if not isinstance(matched, bool):
            self._invalid_2xx(op, "matched missing/invalid")
        return bool(matched)

    # ------------------------------------------------------------ search_1n
    def search_1n(self, namespace: str, images: dict[str, bytes]) -> SearchResult:
        front = images.get("front")
        if front is None:
            self._missing_view("search_1n", "front")
        path = f"/v1/namespaces/{quote(namespace, safe='')}/search"
        try:
            result = self._transport.request(
                "POST", path, json_body=self._image_payload(front)
            )
        except FaceServiceHttpError as exc:
            if exc.is_auth:
                self._raise_auth_config("search_1n", exc)
            if exc.code in self._SEARCH_CONFIG_CODES:
                self._raise_shape_config("search_1n", exc)
            self._raise_unavailable("search_1n", exc)
        except FaceServiceTransportError as exc:
            self._raise_unavailable("search_1n", exc)
        body = result.json
        decision = self._validate_search_body(body)
        if decision == "matched":
            return SearchResult("matched", body["subject_id"])
        return SearchResult(decision)

    def _validate_search_body(self, body: Any) -> str:
        if not isinstance(body, Mapping):
            self._invalid_2xx("search_1n", "body is not an object")
        for key in self._SEARCH_FROZEN_KEYS:
            if key not in body:
                self._invalid_2xx("search_1n", f"missing frozen key {key!r}")
        decision = body.get("decision")
        if decision not in self._SEARCH_DECISIONS:
            self._invalid_2xx("search_1n", "decision outside frozen vocabulary")
        if not isinstance(body.get("ambiguous"), bool):
            self._invalid_2xx("search_1n", "ambiguous is not a bool")
        if not isinstance(body.get("reasons"), list):
            self._invalid_2xx("search_1n", "reasons is not a list")
        for int_key in ("subject_count", "top_k", "library_revision"):
            value = body.get(int_key)
            if not isinstance(value, int) or isinstance(value, bool):
                self._invalid_2xx("search_1n", f"{int_key} is not an int")
        for str_key in ("policy_version", "model_version", "request_id"):
            if not isinstance(body.get(str_key), str):
                self._invalid_2xx("search_1n", f"{str_key} is not a string")
        if not isinstance(body.get("quality"), Mapping):
            self._invalid_2xx("search_1n", "quality is not an object")
        if decision == "matched":
            subject_id = body.get("subject_id")
            if not isinstance(subject_id, str) or not subject_id:
                self._invalid_2xx("search_1n", "matched without subject_id")
            similarity = body.get("similarity")
            if isinstance(similarity, bool) or not isinstance(similarity, (int, float)):
                self._invalid_2xx("search_1n", "matched without similarity")
        elif "subject_id" in body:
            self._invalid_2xx("search_1n", "non-matched decision carries subject_id")
        return str(decision)

    # ------------------------------------------------------------ register_person
    def register_person(
        self,
        namespace: str,
        entity_id: str,
        images: dict[str, bytes],
        correlation_id: str,
        provider_request_id: str,
    ) -> RegisterResult:
        # 自动登记门：PoC/标定/活体未验证前**绝不真实自动建档**（合同 §4.2 裁定 2；
        # ``后端详细设计-V1-MVP.md:663``）。关闭时在**任何 HTTP 之前**拒绝，零网络。
        if not self._cfg.face_service_auto_enroll:
            raise ProviderNotActivated(
                "insightface auto-enroll gate closed: PoC / threshold calibration / "
                "liveness gate not verified (contract §4.2 ruling 2; 后端详细设计:663)"
            )
        front = images.get("front")
        if front is None:
            self._missing_view("register_person", "front")
        payload = self._image_payload(front)
        payload["subject_id"] = entity_id
        payload["correlation_id"] = correlation_id
        payload["provider_request_id"] = provider_request_id
        path = f"/v1/namespaces/{quote(namespace, safe='')}/subjects"
        try:
            result = self._transport.request("POST", path, json_body=payload)
        except FaceServiceHttpError as exc:
            if exc.is_auth:
                self._raise_auth_config("register_person", exc)
            if exc.status == 409 or exc.code == "SUBJECT_ALREADY_EXISTS":
                return RegisterResult("failed")
            if (
                exc.retryable
                or exc.status >= 500
                or exc.code in self._REGISTER_UNKNOWN_CODES
            ):
                return RegisterResult("unknown")
            return RegisterResult("failed")
        except FaceServiceTimeout:
            # 客户端超时：服务端可能已成功 → 交给既有对账（同 entity_id，不盲重试）。
            return RegisterResult("timeout")
        except FaceServiceTransportError:
            return RegisterResult("unknown")
        # 2xx：合同 §6.1 的成功状态**只有** 200/201（api.py:742
        # ``status_code=201 if result.created else 200``）。其它 2xx（202/204/…）无法
        # 证明“同一次逻辑登记已创建” → unknown（交对账），绝不 success。
        if result.status not in (200, 201):
            return RegisterResult("unknown")
        if not self._register_confirmed(
            result.json, status=result.status, entity_id=entity_id, namespace=namespace
        ):
            return RegisterResult("unknown")
        return RegisterResult("success")

    @staticmethod
    def _register_confirmed(
        body: Any, *, status: int, entity_id: str, namespace: str
    ) -> bool:
        """校验登记响应是否为冻结合同 §6.1 形状（api.py:726-742 逐键取证）。

        - 状态已在调用点限定为 200/201；``created``/``replayed`` 必须与状态构成
          **服务端可达的**三元组（ground truth）：
          * ``201`` ⇔ ``created=True ∧ replayed=False``（store.py:514-577 新建，
            ``replayed`` 默认 False；api.py:742 201 iff created）、
          * ``200`` ⇔ ``created=False ∧ replayed=True``（store.py:462-491 幂等重放；
            Worker 路径**从不**发送 ``on_exists``，故唯一可达的 200 就是重放——
            overwrite 的 ``created=False,replayed=False`` 只在显式 ``on_exists=overwrite``
            时出现，Worker 永不使用）。
          这是**方向安全**的收紧：不符 → ``unknown`` → 既有对账（``query_registration``），
          绝不放行未确认的 success。
        - ``subject_id`` 非空字符串且**精确等于** ``entity_id``；``namespace`` 非空字符串且
          **精确等于**本次请求的 namespace（防止把另一个 namespace 的记录当成本次成功）；
        - 除 ``registered_at``（可空列，api.py 直接外发 ``record.registered_at``）外，
          其余键都是服务端**恒有类型**的值，逐键要求；
        - body 非 Mapping / 缺键 / 类型或取值不符 → 一律 unknown（force reconcile）。
        """
        if not isinstance(body, Mapping):
            return False
        required = (
            "subject_id",
            "namespace",
            "created",
            "created_at",
            "updated_at",
            "embedding_dim",
            "model_version",
            "quality",
            "library_revision",
            "replayed",
            "registered_at",
            "request_id",
        )
        for key in required:
            if key not in body:
                return False
        subject_id = body.get("subject_id")
        if not isinstance(subject_id, str) or not subject_id or subject_id != entity_id:
            return False
        echoed_namespace = body.get("namespace")
        if (
            not isinstance(echoed_namespace, str)
            or not echoed_namespace
            or echoed_namespace != namespace
        ):
            return False
        created = body.get("created")
        replayed = body.get("replayed")
        if not isinstance(created, bool) or not isinstance(replayed, bool):
            return False
        if status == 201:
            if not (created is True and replayed is False):
                return False
        else:  # status == 200 (调用点已限定)
            if not (created is False and replayed is True):
                return False
        for str_key in ("created_at", "updated_at", "model_version", "request_id"):
            value = body.get(str_key)
            if not isinstance(value, str) or not value:
                return False
        for int_key in ("embedding_dim", "library_revision"):
            value = body.get(int_key)
            if not isinstance(value, int) or isinstance(value, bool):
                return False
        if not isinstance(body.get("quality"), Mapping):
            return False
        registered_at = body.get("registered_at")
        if registered_at is not None and (
            not isinstance(registered_at, str) or not registered_at
        ):
            return False
        return True

    # ------------------------------------------------------------ query_registration
    def query_registration(
        self,
        correlation_id: str,
        provider_request_id: str,
        *,
        namespace: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> RegistrationQueryResult:
        if not isinstance(namespace, str) or not namespace.strip():
            raise ProviderConfigError(
                "insightface query_registration requires a namespace "
                "(reconciliation path is namespace-scoped)"
            )
        path = (
            f"/v1/namespaces/{quote(namespace, safe='')}"
            f"/registrations/{quote(correlation_id, safe='')}"
        )
        query: dict[str, str] = {}
        if provider_request_id:
            query["provider_request_id"] = provider_request_id
        if entity_id:
            query["entity_id"] = entity_id
        if query:
            path = f"{path}?{urlencode(query)}"
        try:
            result = self._transport.request("GET", path)
        except FaceServiceHttpError as exc:
            if exc.is_auth:
                self._raise_auth_config("query_registration", exc)
            if exc.status == 404 or exc.code == "NAMESPACE_NOT_FOUND":
                # 合同 §6.2：对账针对已发起的登记，namespace 必然已存在 ⇒ 404 是确定性
                # 否定（该 namespace 内确无此登记）→ not_found；与 unknown 在
                # identity_enroll._reconcile 中同样走 ENROLLMENT_RECONCILE_PENDING。
                return RegistrationQueryResult("not_found")
            return RegistrationQueryResult("unknown")
        except FaceServiceTransportError:
            return RegistrationQueryResult("unknown")
        # B 的对账路由**只以 HTTP 200 返回**（api.py:805-852：命中/未命中都是 200）。
        # 其它 2xx（201/202/204/206/299…）不是本合同的可达成功形态 → unknown，
        # 绝不把它当作权威确认（否则 registered 会经 identity_enroll.py:183-220 建成员）。
        if result.status != 200:
            return RegistrationQueryResult("unknown")
        body = result.json
        if not isinstance(body, Mapping):
            return RegistrationQueryResult("unknown")
        status = body.get("status")
        if status == "registered":
            if not self._registration_confirmed(
                body,
                correlation_id=correlation_id,
                provider_request_id=provider_request_id,
                entity_id=entity_id,
            ):
                return RegistrationQueryResult("unknown")
            return RegistrationQueryResult("registered")
        if status == "not_found":
            # 合同 §6.2 的 not_found 形状仅 ``{status, request_id}``；只需 status 字符串。
            return RegistrationQueryResult("not_found")
        return RegistrationQueryResult("unknown")

    @staticmethod
    def _registration_confirmed(
        body: Mapping[str, Any],
        *,
        correlation_id: str,
        provider_request_id: str,
        entity_id: Optional[str],
    ) -> bool:
        """校验 ``registered`` 响应是否为冻结合同 §6.2 形状（api.py:844-852 逐键取证）。

        **必须精确回显本次登记的标识**，否则不得当作确认：

        - ``subject_id`` 非空字符串，且当 ``entity_id`` 提供时必须**精确相等**
          （frozen handler 恒提供 ``entity_id``；不等即可能是另一个主体的登记）；
        - ``correlation_id`` 非空字符串且**精确等于**请求的 ``correlation_id``；
        - ``provider_request_id``：请求提供时必须是字符串且**精确相等**；服务端可发
          null（nullable 列），但 null 不等于请求值 ⇒ 不符即 unknown；
        - ``registered_at`` 可空（nullable 列）；``library_revision`` 为 int；
          ``request_id`` 非空字符串；缺任一冻结键 → unknown。
        """
        required = (
            "status",
            "subject_id",
            "correlation_id",
            "provider_request_id",
            "registered_at",
            "library_revision",
            "request_id",
        )
        for key in required:
            if key not in body:
                return False
        subject_id = body.get("subject_id")
        if not isinstance(subject_id, str) or not subject_id:
            return False
        if entity_id is not None and subject_id != entity_id:
            return False
        echoed_correlation = body.get("correlation_id")
        if not isinstance(echoed_correlation, str) or echoed_correlation != correlation_id:
            return False
        echoed_request = body.get("provider_request_id")
        if provider_request_id:
            if not isinstance(echoed_request, str) or echoed_request != provider_request_id:
                return False
        elif echoed_request is not None and not isinstance(echoed_request, str):
            return False
        registered_at = body.get("registered_at")
        if registered_at is not None and (
            not isinstance(registered_at, str) or not registered_at
        ):
            return False
        revision = body.get("library_revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            return False
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return False
        return True


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


# ---------------------------------------------------------------- llm_rag plan adapter

#: 终态 problem+json 码（无论 retryable 标记）。
_PLAN_PROBLEM_TERMINAL_CODES = frozenset(
    {"AI_UNAUTHORIZED", "AI_REQUEST_INVALID", "AI_PAYLOAD_TOO_LARGE"}
)
#: 依 body retryable 标记分类的码。
_PLAN_PROBLEM_FLAGGED_CODES = frozenset(
    {"AI_SERVICE_UNAVAILABLE", "AI_UPSTREAM_TIMEOUT", "AI_INTERNAL_ERROR"}
)

class LLMRagPlanAdapter:
    """真实 AI 方案适配器：weijing assess（shuiguang_cloud_v1）。

    契约来源：``.mvp-d-runtime/ai-plan-discovery.md`` §2.1/§7（部署代码 + 用户授权
    合同草稿样本，均已核实）。仅按实证契约组装请求/分类响应；**无 mock 回退**。

    **persistence-free**（oracle Fix 1）：适配器只抛类型化异常，绝不写 DB、绝不携带
    business_tx；终态落库由 plan_generate 经既有 fenced ``_terminal`` 机制执行（带
    plan_id + generation_revision 守卫），故陈旧代次的终态回调 0 行 → StaleGeneration
    → 整体回滚（不误写新一代 T06）。
    """

    provider_name = "llm_rag"
    # response assessment.plan.knowledge_version 是真实值，但仅在响应后可得；快照在
    # 调用前冻结且要求非空，故需要一个稳定非空占位（真实值写入候选 model_version）。
    model_version = "weijing-shuiguang_cloud_v1"

    def __init__(self, cfg: DConfig) -> None:
        self._cfg = cfg

    # ------------------------------------------------------------ generate
    def generate(
        self, report_context: dict[str, Any], input_snapshot: dict[str, Any]
    ) -> PlanCandidate:
        # build_request 只抛类型化异常（MappingNotApproved / RawDetectionContractViolation）。
        body = weijing_mapping.build_request(
            report_context,
            input_snapshot,
            request_mapping=self._cfg.llm_rag_request_mapping,
        )

        status, raw = self._post(body)
        if 200 <= status < 300:
            payload = self._parse_json(raw)
            weijing_mapping.validate_envelope(payload)
            assessment = payload["assessment"]
            weijing_mapping.validate_assessment(assessment)
            # 受理 ≠ 完成：结构合法后仍需批准输出映射才可能 ready（当前未批准）。
            return weijing_mapping.plan_to_candidate(
                assessment, output_mapping=self._cfg.llm_rag_output_mapping
            )
        self._raise_problem(status, raw)
        raise AssertionError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------ helpers
    def _post(self, body: dict[str, Any]) -> tuple[int, bytes]:
        base = (self._cfg.llm_rag_base_url or "").rstrip("/")
        url = base + "/internal/v1/weijing/reports/assess"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers = {
            "X-Service-Name": "medical-platform",
            "X-API-Key": self._cfg.llm_rag_api_key,
            "X-Request-Id": str(uuid.uuid4()),
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Protocol-Version": "1.0",
            "traceparent": "00-" + uuid.uuid4().hex + "-" + uuid.uuid4().hex[:16] + "-01",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        request = urllib.request.Request(
            url, data=data, method="POST", headers=request_headers
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._cfg.llm_rag_timeout_seconds
            ) as resp:
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            # 传输错误（拒绝/超时/DNS）→ 可重试；绝不回退 mock。
            raise ProviderUnavailable("weijing assess transport unavailable") from exc

    @staticmethod
    def _parse_json(raw: bytes) -> Any:
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise weijing_mapping.ResponseContractViolation(
                "weijing 2xx body is not valid JSON"
            ) from exc

    @staticmethod
    def _raise_problem(status: int, raw: bytes) -> None:
        problem: Optional[dict[str, Any]] = None
        try:
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                problem = parsed
        except Exception:  # noqa: BLE001
            problem = None
        if problem is None:
            # 不可解析 problem → 短暂（有界尝试）；绝不谎报终态。
            raise ProviderUnavailable(
                f"weijing assess problem body unparseable (status={status})"
            )
        code = problem.get("code")
        retryable = problem.get("retryable")
        if code in _PLAN_PROBLEM_TERMINAL_CODES:
            if code == "AI_UNAUTHORIZED":
                raise weijing_mapping.PlanProviderConfigRequired(
                    f"weijing assess auth/config rejected: {code}"
                )
            raise weijing_mapping.ResponseContractViolation(
                f"weijing assess rejected: {code}"
            )
        if code in _PLAN_PROBLEM_FLAGGED_CODES:
            if retryable is True:
                raise ProviderUnavailable(f"weijing assess transient: {code}")
            raise weijing_mapping.ResponseContractViolation(
                f"weijing assess non-retryable: {code}"
            )
        # 未知 code：保守按 retryable 标记；缺标记 → 终态。
        if retryable is True:
            raise ProviderUnavailable(f"weijing assess transient: {code}")
        raise weijing_mapping.ResponseContractViolation(
            f"weijing assess rejected: {code}"
        )


# ---------------------------------------------------------------- factory


def _forbid_double_in_production(environment: str, provider: str) -> None:
    if environment == "production" and provider == "double":
        raise ProviderConfigError(
            "double provider is forbidden in production (fail-closed)"
        )


def _forbid_face_double_in_production(environment: str) -> None:
    """face 替身生产 fail-closed（explicit production **或**任一生产信号）。

    对齐 ``_forbid_storage_double_in_production``：除字面 ``production/prod`` 外，还须
    拦截 ``production_environment_signals()`` 命中的混合/矛盾 profile，确保替身只在
    dev/test 出现。选择 ``insightface`` 时不适用（它是真实 provider）；insightface 服务
    失败按冻结合同映射为 ``ProviderUnavailable``（可重试）/``ProviderConfigError``
    （配置型终态），**绝不**回退本替身。
    """
    normalized = environment.strip().lower()
    if normalized in ("production", "prod"):
        raise ProviderConfigError(
            "double face provider is forbidden in production (fail-closed)"
        )
    signals = production_environment_signals()
    if signals:
        raise ProviderConfigError(
            "double face provider is forbidden in production (fail-closed;"
            f" signals: {signals})"
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


def _insightface_required_keys(cfg: DConfig) -> list[str]:
    """insightface 必填项：缺失时错误消息只列**键名**，绝不回显取值。"""
    missing: list[str] = []
    if not cfg.face_service_base_url.strip():
        missing.append(FACE_SERVICE_BASE_URL_ENV)
    if not cfg.face_service_namespace.strip():
        missing.append(FACE_SERVICE_NAMESPACE_ENV)
    if not cfg.face_service_token_file.strip():
        missing.append(FACE_SERVICE_TOKEN_FILE_ENV)
    return missing


def _insightface_from_config(cfg: DConfig) -> InsightFaceAdapter:
    """构造 insightface 适配器：缺配置/非法 token 文件 → 构建期 ProviderConfigError。

    - 必填项（``MVP_D_FACE_SERVICE_BASE_URL`` / ``_NAMESPACE`` / ``_TOKEN_FILE``）缺失
      → 只报键名；
    - token 文件在**传输构造时读取一次**（``read_token_file``；0600 普通文件、空/纯空白
      拒绝；消息只含路径，绝不含取值），**不做进程级缓存**；
    - 真实 stdlib 传输（:class:`StdlibHttpTransport`，connect/read 分别超时）；
    - insightface 是真实 provider，生产允许；服务失败在运行期按冻结合同映射
      （``ProviderUnavailable`` 可重试 / ``ProviderConfigError`` 配置型终态），
      **绝不** double fallback（face 替身的生产拒绝另见
      :func:`_forbid_face_double_in_production`）。
    """
    missing = _insightface_required_keys(cfg)
    if missing:
        raise ProviderConfigError(
            "insightface face provider requires non-empty config: " + ", ".join(missing)
        )
    token = read_token_file(cfg.face_service_token_file)
    transport = StdlibHttpTransport(
        base_url=cfg.face_service_base_url.strip(),
        token=token,
        connect_timeout_ms=cfg.face_service_connect_timeout_ms,
        read_timeout_ms=cfg.face_service_read_timeout_ms,
    )
    return InsightFaceAdapter(cfg, transport)


def build_face_port(cfg: DConfig, *, environment: str) -> FacePort:
    provider = cfg.face_provider
    if provider == "double":
        _forbid_face_double_in_production(environment)
        return _face_double_from_config(cfg)
    if provider == "aliyun_face":
        return AliyunFaceAdapter(cfg)
    if provider == "insightface":
        return _insightface_from_config(cfg)
    raise ProviderConfigError(f"unknown face provider: {provider}")


def _skin_double_from_config(cfg: DConfig) -> SkinDouble:
    """按 env 装配 skin 替身；``MVP_D_SKIN_DOUBLE_HOLD=true`` 为**进程级 hold**。

    hold 复用既有可重试失败语义（``ProviderUnavailable`` → handler 映射为可重试
    ``DEPENDENCY_UNAVAILABLE``，job 退避重排队）：旧分析停在可释放态，不 sleep、
    不改 DB、不改业务判定。端口无 task/照片版本入参，故只能进程级（E 用
    ``worker_once(env_extra=...)`` 逐次控制时机）。

    ``MVP_D_SKIN_DOUBLE_INVALID``：返回违反既有指标白名单/基线的指标 → handler 经
    既有 ``_ContractViolation`` 落 **PROVIDER_CONTRACT_VIOLATION** 终态（确定性，1 次）。

    ``MVP_D_SKIN_V3_MOCK=true``（仅 dev/test）：替身额外携带 V3 三组 mock
    （:mod:`dskin_mock`，派生自用户样本、**非算法证据**），并以含 ``mock`` 的
    ``model_version`` 明确标记；生产信号下本开关被既有守卫拒绝启动（fail-closed）。
    hold 与 V3 mock 同时开启时 **hold 优先**（仍注入可重试失败，不掩盖故障语义）。
    """
    invalid = None if cfg.skin_double_invalid == "none" else cfg.skin_double_invalid
    if cfg.skin_double_hold:
        return SkinDouble(
            invalid=invalid,
            faults={"analyze": [ProviderUnavailable("analyze hold: injected retryable hold")]},
        )
    if cfg.skin_v3_mock:
        return SkinDouble(
            invalid=invalid,
            v3_groups=V3_SKIN_MOCK_GROUPS,
            model_version=V3_SKIN_MOCK_MODEL_VERSION,
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


def _llm_rag_plan_from_config(cfg: DConfig) -> LLMRagPlanAdapter:
    """llm_rag 构造：缺 BASE_URL/API_KEY → ProviderConfigError（消息只含**键名**）。"""
    missing: list[str] = []
    if not cfg.llm_rag_base_url.strip():
        missing.append("MVP_D_LLM_RAG_BASE_URL")
    if not cfg.llm_rag_api_key.strip():
        missing.append("MVP_D_LLM_RAG_API_KEY")
    if missing:
        raise ProviderConfigError(
            "llm_rag plan provider requires non-empty config: " + ", ".join(missing)
        )
    return LLMRagPlanAdapter(cfg)


def build_plan_port(cfg: DConfig, *, environment: str) -> PlanPort:
    provider = cfg.plan_provider
    if provider == "double":
        _forbid_double_in_production(environment, provider)
        return _plan_double_from_config(cfg)
    if provider == "aliyun_llm":
        return AliyunPlanAdapter(cfg)
    if provider == "llm_rag":
        return _llm_rag_plan_from_config(cfg)
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
