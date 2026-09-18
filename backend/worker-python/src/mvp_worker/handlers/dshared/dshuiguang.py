"""真实 **shuiguang-test** HTTP 皮肤评分适配器（非 dermavision；非旧 ``shuiguang_cloud_v1`` 计划路径）。

绑定的外部契约（supervisor 从 shuiguang-test ``d7c84c18`` 核实，**不猜测**）：

- ``POST /api/score-jobs``（HTTP 202）body ``{task_id, images:[{image_id, path}], mirrored:false}``；
  ``images`` **恰三张**（``front``/``left``/``right``），``path`` 为相对 ``INPUT_ROOT`` 的
  共享挂载文件路径。**每一次 POST 都会入队一个新任务并返回新的 ``queue_id``**——即使
  ``task_id`` 与输入完全相同；且每个排队任务在**执行时**才读取共享文件
  （``safe_inputs`` 先于任何既有 job/结果判定）。因此每次 POST 都使用独立输入目录；
  只在该 ``queue_id`` 明确终态后删除其独占目录，不会饿死兄弟条目。
  （API 的 job/结果幂等语义属算法侧、本项目**未核实**——仅确认 ``safe_inputs`` 的读取
  时序，不得依赖其余语义。）
- ``GET /api/score-jobs/{queue_id}``：``pending``/``started``/``progress`` 为进行中；
  **成功** response body 直接是恰三组 ``pores``/``spots``/``surface_gloss``；
  **失败** ``{status:"failed", error:{code,message}}``。

设计要点：

- ``task_id`` 仍由内容派生（160-bit 截断摘要）；暂存目录改为每次 POST 独立的
  ``{INPUT_ROOT}/sg-stage-<uuid>/{view}.{ext}``。目录 0700 / 文件 0600，提交前持久化
  ``submitting`` manifest，取得 queue_id 后更新为 ``queued``。
- 成功体用 :func:`dshared.dv3.validate_v3_skin_groups` **同一严格语义**校验（防御式；
  handler 发布前还会再校验一次）。
- ``metrics=[]``、``result_images=[]``、``conclusion``/``description=""``——**绝不伪造**
  旧指标/结果图/叙述/四区。
- 明确成功/失败终态可清理本次独占目录；轮询超时、网络故障、崩溃时保留。
  独立 reaper 只重查持久化 queue_id 并在远端确认终态后精确清理，绝不按 TTL 猜删。
  POST 已受理但回包丢失时只有 ``submitting`` manifest，现有 GET-by-queue_id 无法
  确认消费结束，必须由算法侧增加幂等请求标识/查询合同或人工对账；在此之前仍不可
  正式激活 provider。reaper 需按部署要求周期运行。
- 日志/异常只含键名与已消毒的 ``code``/``score_source``；**绝不**输出 token、图像字节、
  暂存路径或 ``message`` 原文。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import stat
import sys
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
_STAGE_RE = re.compile(r"^sg-stage-[0-9a-f]{32}$")
_MANIFEST = ".submission.json"
_REAPER_CURSOR = ".reap-cursor"


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
    ``__context__`` 均不携带任何路径。无法确认远端终态时暂存保留供对账。
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
        stage_dir, rel = self._stage(images, task_id)
        queue_id, score_source = self._submit(task_id, rel)
        manifest_error = False
        try:
            self._write_manifest(stage_dir, task_id, queue_id)
        except OSError:
            # POST 已受理；没有持久 queue_id 的目录不能安全清理。
            manifest_error = True
        if manifest_error:
            raise ShuiguangStagingError(
                "shuiguang queue ownership persist failed; check " + SHUIGUANG_INPUT_ROOT_ENV
            ) from None
        groups = self._poll(queue_id, on_terminal=lambda: self._remove_stage(stage_dir))
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

    def _stage(self, images: dict[str, bytes], task_id: str) -> tuple[Path, list[tuple[str, str]]]:
        stage_id = "sg-stage-" + uuid.uuid4().hex
        job_dir = self._root / stage_id
        rel: list[tuple[str, str]] = []
        tmp_names: list[Path] = []
        failure: Optional[OSError] = None
        created = False
        try:
            job_dir.mkdir(mode=self._dir_mode, exist_ok=False)
            created = True
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
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, target)  # 原子；保留 0600 模式
                tmp_names.remove(tmp)
                rel.append((view, f"{stage_id}/{view}.{ext}"))
            self._write_manifest(job_dir, task_id, None)
        except OSError as exc:
            failure = exc
        if failure is not None:
            # 尚未 POST，整个独立目录只归本次调用所有。
            for tmp in tmp_names:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            if created:
                self._remove_stage(job_dir)
            # 关键：已退出 except 块（sys.exc_info 清空）→ raise 无隐式 __context__；
            # ``from None`` 再清 __cause__。消息只含键名，绝不含路径。
            raise ShuiguangStagingError(
                "shuiguang staging failed; check " + SHUIGUANG_INPUT_ROOT_ENV
            ) from None
        return job_dir, rel

    def _write_manifest(self, stage_dir: Path, task_id: str, queue_id: Optional[str]) -> None:
        body = {"schema_version": 1, "stage_id": stage_dir.name, "task_id": task_id,
                "state": "queued" if queue_id is not None else "submitting",
                "queue_id": queue_id}
        tmp = stage_dir / (".submission." + uuid.uuid4().hex + ".tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, self._file_mode)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(body, fh, separators=(",", ":"))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, stage_dir / _MANIFEST)
            dir_fd = os.open(stage_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    @staticmethod
    def _remove_stage(stage_dir: Path) -> bool:
        """仅删独立 stage 目录；失败留给 reaper，不能令成功报告重试。"""
        if not _STAGE_RE.fullmatch(stage_dir.name):
            return False
        try:
            if not stage_dir.exists():
                return True
            if not stat.S_ISDIR(stage_dir.lstat().st_mode):
                return False
            shutil.rmtree(stage_dir)
            return True
        except OSError:
            return False

    @staticmethod
    def _terminal(status: int, payload: Any) -> bool:
        return status == 200 and isinstance(payload, dict) and (
            set(payload) == set(V3_SKIN_GROUP_KEYS) or payload.get("status") == "failed"
        )

    def reap_staged(self, *, limit: int = 32) -> dict[str, int]:
        """重查已持久化 queue_id；只删远端明确终态的独立目录。"""
        if not 1 <= limit <= 1000:
            raise ValueError("reaper limit out of range")
        counts = {"checked": 0, "removed": 0, "unresolved": 0}
        candidates = sorted(
            path for path in self._root.iterdir()
            if _STAGE_RE.fullmatch(path.name) and not path.is_symlink() and path.is_dir()
        )
        if not candidates:
            return counts
        try:
            cursor = (self._root / _REAPER_CURSOR).read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            cursor = ""
        start = next((i for i, path in enumerate(candidates) if path.name > cursor), 0)
        last_name = ""
        for offset in range(min(limit, len(candidates))):
            stage_dir = candidates[(start + offset) % len(candidates)]
            last_name = stage_dir.name
            counts["checked"] += 1
            try:
                manifest_path = stage_dir / _MANIFEST
                manifest_stat = manifest_path.lstat()
                if not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_size > 4096:
                    raise ValueError("manifest too large")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                counts["unresolved"] += 1
                continue
            if not isinstance(manifest, dict) or manifest.get("stage_id") != stage_dir.name:
                counts["unresolved"] += 1
                continue
            queue_id = manifest.get("queue_id")
            if manifest.get("state") != "queued" or not isinstance(queue_id, str) or not queue_id:
                counts["unresolved"] += 1
                continue
            try:
                status, payload = self._do_request(
                    "GET", "/api/score-jobs/" + quote(queue_id, safe=""), None
                )
            except ProviderUnavailable:
                counts["unresolved"] += 1
                continue
            if self._terminal(status, payload) and self._remove_stage(stage_dir):
                counts["removed"] += 1
            else:
                counts["unresolved"] += 1
        # 持久轮转，避免永久 pending/unknown 目录占满每轮预算，饿死后面的终态目录。
        cursor_tmp = self._root / (".reap-cursor." + uuid.uuid4().hex + ".tmp")
        try:
            fd = os.open(cursor_tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, self._file_mode)
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(last_name + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(cursor_tmp, self._root / _REAPER_CURSOR)
        except OSError:
            pass  # 游标损坏只影响公平性，下轮仍按远端状态安全判定
        finally:
            try:
                os.unlink(cursor_tmp)
            except FileNotFoundError:
                pass
        return counts

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

    def _poll(
        self, queue_id: str, *, on_terminal: Optional[Callable[[], Any]] = None
    ) -> dict[str, Any]:
        path = "/api/score-jobs/" + quote(queue_id, safe="")
        deadline = self._clock() + self._poll_max
        while True:
            if self._clock() > deadline:
                raise ProviderUnavailable("shuiguang poll budget exceeded")
            status, payload = self._do_request("GET", path, None)
            if status != 200 or not isinstance(payload, dict):
                raise ProviderUnavailable(f"shuiguang status query failed (status={status})")
            if set(payload) == set(V3_SKIN_GROUP_KEYS):
                if on_terminal is not None:
                    on_terminal()
                validated = validate_v3_skin_groups(payload)
                assert validated is not None  # payload 非 None → 规范化必为 dict
                return validated  # 同冻严格语义；违约→V3SkinViolation
            state = payload.get("status")
            if state == "failed":
                if on_terminal is not None:
                    on_terminal()
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


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "--reap":
        raise SystemExit("usage: python -m mvp_worker.handlers.dshared.dshuiguang --reap")
    summary = build_shuiguang_skin_port(DConfig.from_env()).reap_staged()
    print("shuiguang_reap checked={checked} removed={removed} unresolved={unresolved}".format(**summary))
