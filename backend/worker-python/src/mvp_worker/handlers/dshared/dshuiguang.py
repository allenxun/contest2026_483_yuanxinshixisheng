"""真实 **shuiguang-test** HTTP 皮肤评分适配器（非 dermavision；非旧 ``shuiguang_cloud_v1`` 计划路径）。

绑定的外部契约（supervisor 从 shuiguang-test ``d7c84c18`` 核实，**不猜测**）：

- ``POST /api/score-jobs``（HTTP 202）body ``{task_id, images:[{image_id, path}], mirrored:false}``；
  ``images`` **恰三张**（``front``/``left``/``right``），``path`` 为相对 ``INPUT_ROOT`` 的
  共享挂载文件路径。**每一次 POST 都会入队一个新任务并返回新的 ``queue_id``**——即使
  ``task_id`` 与输入完全相同；且每个排队任务在**执行时**才读取共享文件
  （``safe_inputs`` 先于任何既有 job/结果判定）。因此**绝不能**按单个 ``queue_id`` 的
  结果删除共享内容目录：会饿死同一内容目录上仍在排队/执行的兄弟任务。
  （API 的 job/结果幂等语义属算法侧、本项目**未核实**——仅确认 ``safe_inputs`` 的读取
  时序，不得依赖其余语义。）
- ``GET /api/score-jobs/{queue_id}``：``pending``/``started``/``progress`` 为进行中；
  **成功** response body 直接是恰三组 ``pores``/``spots``/``surface_gloss``；
  **失败** ``{status:"failed", error:{code,message}}``。

设计要点：

- ``task_id`` 由**内容**派生（``sha256`` 的 160-bit 截断前缀）→ 同字节同 id、异字节
  高概率不同 id；**碰撞抗性是概率性的**（截断摘要，非"异字节必然异 id"）。无需改
  handler 签名；暂存目录 ``{INPUT_ROOT}/{task_id}/{view}.{ext}``，临时文件 + ``os.replace``
  原子落盘，目录 0700 / 文件 0600（不受 umask 影响）。
- 成功体用 :func:`dshared.dv3.validate_v3_skin_groups` **同一严格语义**校验（防御式；
  handler 发布前还会再校验一次）。
- ``metrics=[]``、``result_images=[]``、``conclusion``/``description=""``——**绝不伪造**
  旧指标/结果图/叙述/四区。
- 生命周期（**已按真实源码更正**）：**暂存输入在任何退出路径都保留**——成功、
  确定性终态（``V3SkinViolation`` / ``ShuiguangScoringReferenceNotReady``）、可重试失败、
  轮询预算耗尽，**一律不删**。
  - 为什么不能按结果删除：每次 POST 产生**新的 queue 条目**（新 ``queue_id``），且每个
    排队任务在执行时才读共享文件——删除共享内容目录会**饿死兄弟条目**（INVALID_INPUT）；
    确定性终态删除有同样缺陷；粗粒度补偿删除还会在租约竞态/照片版本换代时误删他人
    或新代次的活跃目录。无**持久化 staging 所有权记录**前，任何删除都不安全
    （新建表/迁移属 coordination territory，本轮禁止）。
  - 保留 `_stage` 失败时**只清本次调用**记录的临时文件（可证明本调用所有，见 ``_stage``）。
- **四类残留/孤儿全部延后到"激活前置的 ops 机制"**：(a) 重试耗尽终态、(b) 照片版本换代、
  (c) 硬进程崩溃、(d) 每一次已完成结果的残留。activation 已被"共享挂载 + ops 裁定"把关；
  ops 清理契约（授权的清扫器**或**持久化 staging 所有权记录）属
  **activation-blocking 前置条件**——需另立 coordination 记录，不得用结果驱动的删除替代。
- 日志/异常只含键名与已消毒的 ``code``/``score_source``；**绝不**输出 token、图像字节、
  暂存路径或 ``message`` 原文。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
import uuid
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote, urlsplit

from .constants import REQUIRED_VIEWS_ALL
from .dconfig import (
    SHUIGUANG_BASE_URL_ENV,
    SHUIGUANG_INPUT_ROOT_ENV,
    DConfig,
    ProviderConfigError,
)
from .dskin_mock import V3_SKIN_GROUP_KEYS
from .dv3 import V3SkinViolation, validate_v3_skin_groups
from .providers import ProviderUnavailable, SkinAnalysisResult

_MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 契约上限：单图 >25MB → job 失败
_MAX_RESPONSE_BYTES = 1024 * 1024
_CODE_RE = re.compile(r"^[A-Z0-9_]{1,64}$")
_SOURCE_RE = re.compile(r"^[A-Za-z0-9._:@+\-]{1,64}$")
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def derive_task_id(images: dict[str, bytes]) -> str:
    """内容派生 task_id：``sha256`` 的 **160-bit 截断**（40 hex）。

    同字节 → 同 id（幂等）；不同字节 → **高概率**不同 id（碰撞抗性为概率性质，
    并非"异字节必然异 id"）。字符集 ``[A-Za-z0-9-]``，长度 43 ≤ 64。
    """
    h = hashlib.sha256()
    for view in REQUIRED_VIEWS_ALL:
        data = bytes(images[view])
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return "sg-" + h.hexdigest()[:40]


class ShuiguangInputViolation(RuntimeError):
    """输入确定性问题（缺视图/超限/非 JPEG-PNG/重复）→ 终态 ``PROVIDER_CONTRACT_VIOLATION``。"""


class ShuiguangScoringReferenceNotReady(RuntimeError):
    """服务端确定性状态 ``SCORING_REFERENCE_NOT_READY`` → 立即终态，**绝不伪造分数**。"""


class ShuiguangStagingError(ProviderUnavailable):
    """暂存失败（可写根上的 FS 压力/路径冲突）→ 可重试 ``DEPENDENCY_UNAVAILABLE``。

    消息**只含键名**；经"捕获后退出 except 再 raise"模式抛出，``__cause__``/
    ``__context__`` 均不携带任何路径。暂存保留供重试（同内容同 ``task_id``）。
    """


def _is_supported_image(data: bytes) -> bool:
    return data.startswith(_JPEG_MAGIC) or data.startswith(_PNG_MAGIC)


def _image_ext(data: bytes) -> str:
    return "jpg" if data.startswith(_JPEG_MAGIC) else "png"


def _sanitize_code(raw: Any) -> str:
    return raw if isinstance(raw, str) and _CODE_RE.match(raw) else "UNKNOWN"


def _sanitize_source(raw: Any) -> str:
    return raw if isinstance(raw, str) and _SOURCE_RE.match(raw) else "unknown"


class ShuiguangSkinAdapter:
    """:class:`SkinPort` 实现：真实 shuiguang HTTP 评分（stdio 依赖，无第三方）。"""

    provider_name = "shuiguang"

    def __init__(
        self,
        cfg: DConfig,
        *,
        request_fn: Optional[Callable[[str, str, Optional[dict[str, Any]]], tuple[int, Any]]] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_image_bytes: int = _MAX_IMAGE_BYTES,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        self._base_url = cfg.shuiguang_base_url.strip().rstrip("/")
        self._root = Path(cfg.shuiguang_input_root)
        self._connect_timeout = cfg.shuiguang_connect_timeout_ms / 1000.0
        self._read_timeout = cfg.shuiguang_read_timeout_ms / 1000.0
        self._poll_interval = float(cfg.shuiguang_poll_interval_seconds)
        self._poll_max = float(cfg.shuiguang_poll_max_seconds)
        self._max_image_bytes = max_image_bytes
        self._max_response_bytes = max_response_bytes
        self._dir_mode = cfg.shuiguang_stage_dir_mode
        self._file_mode = cfg.shuiguang_stage_file_mode
        self._do_request = request_fn if request_fn is not None else self._http_request
        self._sleep = sleep
        self._clock = clock
        self.model_version = "shuiguang"

    # ------------------------------------------------------------- 公共入口
    def analyze(self, images: dict[str, bytes]) -> SkinAnalysisResult:
        self._preflight(images)
        task_id = self._task_id(images)
        rel = self._stage(images, task_id)
        # 暂存输入**在所有退出路径保留**（成功/确定性终态/可重试/预算耗尽均不删）：
        # 每次 POST 都是新 queue 条目、且排队任务在执行时才读共享文件——按本次结果
        # 删除共享内容目录会饿死兄弟条目。清理延后到激活前置的 ops 所有权契约。
        queue_id, score_source = self._submit(task_id, rel)
        groups = self._poll(queue_id)
        version = f"shuiguang:{_sanitize_source(score_source)}"
        self.model_version = version
        return SkinAnalysisResult(
            conclusion="",
            metrics=[],
            description="",
            result_images=[],
            model_version=version,
            v3_groups=groups,
        )

    # ------------------------------------------------------------- 预检/派生
    def _preflight(self, images: dict[str, bytes]) -> None:
        if set(images) != set(REQUIRED_VIEWS_ALL):
            raise ShuiguangInputViolation("images must be exactly front/left/right")
        for view in REQUIRED_VIEWS_ALL:
            data = images.get(view)
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise ShuiguangInputViolation(f"{view}: empty or non-bytes image")
            if len(data) > self._max_image_bytes:
                raise ShuiguangInputViolation(f"{view}: image exceeds size cap")
            if not _is_supported_image(bytes(data)):
                raise ShuiguangInputViolation(f"{view}: unsupported media type")
        digests = {hashlib.sha256(bytes(images[v])).digest() for v in REQUIRED_VIEWS_ALL}
        if len(digests) < len(REQUIRED_VIEWS_ALL):
            raise ShuiguangInputViolation("duplicate views are not allowed")

    def _task_id(self, images: dict[str, bytes]) -> str:
        return derive_task_id(images)

    def _stage(self, images: dict[str, bytes], task_id: str) -> list[tuple[str, str]]:
        job_dir = self._root / task_id
        rel: list[tuple[str, str]] = []
        tmp_names: list[Path] = []
        failure: Optional[OSError] = None
        try:
            job_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(job_dir, self._dir_mode)  # mkdir 的 mode 会被 umask 掩码
            for view in REQUIRED_VIEWS_ALL:
                data = bytes(images[view])
                ext = _image_ext(data)
                target = job_dir / f"{view}.{ext}"
                tmp = job_dir / f".{view}.{uuid.uuid4().hex}.tmp"
                fd = os.open(
                    tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, self._file_mode
                )
                tmp_names.append(tmp)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                os.replace(tmp, target)  # 原子；保留 0600 模式
                tmp_names.remove(tmp)
                rel.append((view, f"{task_id}/{view}.{ext}"))
        except OSError as exc:
            failure = exc
        if failure is not None:
            # 只清**本次调用**的临时文件；保留既有 target（同 task_id 同字节，
            # 可能正被已排队的算法 job 读取）。绝不删上一尝试的目标文件。
            for tmp in tmp_names:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            # 关键：已退出 except 块（sys.exc_info 清空）→ raise 无隐式 __context__；
            # ``from None`` 再清 __cause__。消息只含键名，绝不含路径。
            raise ShuiguangStagingError(
                "shuiguang staging failed; check " + SHUIGUANG_INPUT_ROOT_ENV
            ) from None
        return rel

    # ------------------------------------------------------------- HTTP
    def _http_request(self, method: str, path: str, body: Optional[dict[str, Any]]) -> tuple[int, Any]:
        parsed = urlsplit(self._base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ProviderUnavailable("shuiguang base URL invalid")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        target = (parsed.path.rstrip("/") if parsed.path else "") + path
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        conn_cls = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
        try:
            conn = conn_cls(parsed.hostname, port, timeout=self._connect_timeout)
            try:
                conn.connect()
                conn.sock.settimeout(self._read_timeout)
                conn.request(method, target, body=data, headers=headers)
                resp = conn.getresponse()
                raw = resp.read(self._max_response_bytes)
                status = resp.status
            finally:
                conn.close()
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderUnavailable("shuiguang request timed out") from exc
        except (ConnectionError, OSError) as exc:
            raise ProviderUnavailable("shuiguang connection failed") from exc
        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
        return status, payload

    # ------------------------------------------------------------- 提交/轮询
    def _submit(self, task_id: str, rel: list[tuple[str, str]]) -> tuple[str, str]:
        body = {
            "task_id": task_id,
            "images": [
                {"image_id": f"{task_id}-{view}", "path": path} for view, path in rel
            ],
            "mirrored": False,
        }
        status, payload = self._do_request("POST", "/api/score-jobs", body)
        if status != 202 or not isinstance(payload, dict):
            raise ProviderUnavailable(f"shuiguang score-jobs submit failed (status={status})")
        if payload.get("task_id") != task_id:
            raise ProviderUnavailable("shuiguang task_id echo mismatch")
        queue_id = payload.get("queue_id")
        if not isinstance(queue_id, str) or not queue_id:
            raise ProviderUnavailable("shuiguang queue_id missing")
        if payload.get("status") != "queued":
            raise ProviderUnavailable("shuiguang unexpected submit status")
        if not isinstance(payload.get("score_source"), str):
            raise ProviderUnavailable("shuiguang score_source missing")
        return queue_id, payload["score_source"]

    def _poll(self, queue_id: str) -> dict[str, Any]:
        path = "/api/score-jobs/" + quote(queue_id, safe="")
        deadline = self._clock() + self._poll_max
        while True:
            if self._clock() > deadline:
                raise ProviderUnavailable("shuiguang poll budget exceeded")
            status, payload = self._do_request("GET", path, None)
            if status != 200 or not isinstance(payload, dict):
                raise ProviderUnavailable(f"shuiguang status query failed (status={status})")
            if set(payload) == set(V3_SKIN_GROUP_KEYS):
                validated = validate_v3_skin_groups(payload)
                assert validated is not None  # payload 非 None → 规范化必为 dict
                return validated  # 同冻严格语义；违约→V3SkinViolation
            state = payload.get("status")
            if state == "failed":
                self._raise_failed(payload)
            if state in ("pending", "started", "progress"):
                self._sleep(self._poll_interval)
                continue
            if state is None:
                # 无 ``status`` 键却又不是恰三组 → 声称是结果体但形状违约（确定性）：
                # 走严格校验（额外/缺失键 → V3SkinViolation 终态），绝不部分接受。
                validated = validate_v3_skin_groups(payload)
                assert validated is not None
                return validated
            # 未知 ``status`` 值：保守可重试（不因未知瞬时丢 job）。
            raise ProviderUnavailable("shuiguang malformed status body")

    def _raise_failed(self, payload: dict[str, Any]) -> None:
        err = payload.get("error")
        code = _sanitize_code(err.get("code") if isinstance(err, dict) else None)
        if code == "SCORING_REFERENCE_NOT_READY":
            raise ShuiguangScoringReferenceNotReady(
                "shuiguang scoring reference not ready (SCORING_REFERENCE_NOT_READY)"
            )
        if code == "WORKER_FAILED":
            raise ProviderUnavailable("shuiguang job failed (code=WORKER_FAILED)")
        # 未知 code：保守可重试（绝不因未知瞬时丢 job，也绝不伪造分数）。
        raise ProviderUnavailable(f"shuiguang job failed (code={code})")


def build_shuiguang_skin_port(cfg: DConfig) -> ShuiguangSkinAdapter:
    """构造真实适配器；缺 BASE_URL/INPUT_ROOT 或输入根不可写 → ``ProviderConfigError``。

    消息只含**键名**，绝不含取值；fail-closed，绝不部分激活。
    """
    missing: list[str] = []
    if not cfg.shuiguang_base_url.strip():
        missing.append(SHUIGUANG_BASE_URL_ENV)
    if not cfg.shuiguang_input_root.strip():
        missing.append(SHUIGUANG_INPUT_ROOT_ENV)
    if missing:
        raise ProviderConfigError(
            "shuiguang skin provider requires non-empty config: " + ", ".join(missing)
        )
    root = Path(cfg.shuiguang_input_root)
    if not root.is_dir() or not os.access(root, os.W_OK):
        raise ProviderConfigError(
            "shuiguang skin provider input root must be an existing writable directory: "
            + SHUIGUANG_INPUT_ROOT_ENV
        )
    return ShuiguangSkinAdapter(cfg)
