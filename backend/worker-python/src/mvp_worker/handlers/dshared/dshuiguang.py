"""真实 **shuiguang-test** HTTP 皮肤评分适配器（非 dermavision；非旧 ``shuiguang_cloud_v1`` 计划路径）。

绑定的外部契约（supervisor 从 shuiguang-test ``d7c84c18`` 源码核实，并于 2026-09-18 在
test.gpu2 上对**真实运行服务**活体取证，**不猜测**）：

- ``POST /api/score-jobs``（HTTP 202）body ``{task_id, images:[{image_id, path}], mirrored:false}``；
  ``images`` **恰三张**（``front``/``left``/``right``），``path`` 为相对 ``INPUT_ROOT`` 的共享
  挂载路径。每次 POST 都 ``.delay()`` 一个**新 Celery 任务**、返回**新 ``queue_id``**（UUID）；
  每个排队任务在**执行时**才读共享文件（``safe_inputs`` **先于**任何既有 job/结果判定），
  故删除目录会饿死同目录上仍在排队的兄弟条目（``INVALID_INPUT``）。
- ``task_id`` 是算法侧的**持久幂等键**（``contracts.AnalyzeRequest.task_id`` 字段描述：
  "同ID同输入幂等返回，不同输入拒绝"）。``service_scores.execute_scores`` 以
  ``request.model_dump()``（**含每张图的 ``path``**）+ 三图 sha256 + ``VERSION`` + 预处理模式
  + 参考文件 sha256 计算指纹，持久化于 ``RUNTIME/score_jobs/{task_id}/request.json``：
  指纹相同且已有 ``result.json`` → **直接返回缓存结果**（幂等重放，不重跑 GPU）；
  指纹不同 → ``TASK_ID_CONFLICT``；有 ``request.json`` 无 ``result.json``（服务端曾硬崩溃）→
  ``INTERRUPTED``。后两者对同一 ``task_id`` **永久成立**。
  ⇒ **暂存路径必须由内容确定**。活体实证（test.gpu2，远端 ``request.json`` 取证）：改用
  "每次 POST 独占 uuid 目录"后，同内容第二次提交因 ``path`` 变化 → 指纹不符 → 真实服务
  返回 ``TASK_ID_CONFLICT``，重试永不可能成功。该设计已回退。
- ``GET /api/score-jobs/{queue_id}``：``queue_id`` 非 UUID → HTTP 400；``pending``/``started``/
  ``progress`` 为进行中；**成功** body 直接是恰三组 ``pores``/``spots``/``surface_gloss``；
  **失败** ``{status:"failed", error:{code,message}}``（Celery 异常统一 ``WORKER_FAILED``）。
  失败体经 Celery 结果层以 **HTTP 200** 返回。
- 算法侧真实码（``service.py``/``service_scores.py`` 核实）：``INVALID_INPUT``（绝对路径/``..``/
  缺文件/>25MB/非 RGB JPEG-PNG/像素超限）、``DUPLICATE_IMAGES``、``BUSY``（同 task_id 锁竞争）、
  ``INPUT_CHANGED``、``ORIENTATION_UNCERTAIN``、``ANALYSIS_FAILED``、``MODEL_ASSET_INVALID``、
  ``DIAGNOSTIC_MODE_REQUIRED``、``SCORING_REFERENCE_NOT_READY``、``TASK_ID_CONFLICT``、
  ``INTERRUPTED``。

设计要点：

- ``task_id`` 由内容派生（``sha256`` 的 160-bit 截断，43 字符 ≤64、字符集合规）；
  ``image_id`` = ``{task_id}-{view}``；暂存 ``{INPUT_ROOT}/{task_id}/{view}.{ext}``——三者
  **全部由内容确定**，故同内容重提的请求逐字节相同 → 命中算法侧幂等重放（免重跑 GPU，
  也让 ack 丢失后的重试安全）。目录 0700 / 文件 0600（chmod 显式设置，免 umask），
  临时文件 + ``os.replace`` 原子落盘。
- 成功体用 :func:`dshared.dv3.validate_v3_skin_groups` **同一严格语义**校验（防御式；
  handler 发布前还会再校验一次）。
- ``metrics=[]``、``result_images=[]``、``conclusion``/``description=""``——**绝不伪造**
  旧指标/结果图/叙述/四区。
- **生命周期**：同内容的多次提交共享同一目录，每次提交在 ``.submissions/{nonce}.json``
  留下**一条独立所有权记录**（POST 前 ``submitting``，拿到 ack 后原子升级为 ``queued``+
  queue_id；O_EXCL 独占创建 → 无读改写、无需跨进程锁）。清理分两级：
  ①**就地清理**——``analyze`` 确认回收结果后，若所有权日志中**恰有本次这一条**记录
  （唯一所有者，常态），立即删除目录，图片零滞留；②**独立 reaper 兜底**——存在其它记录
  （同内容兄弟提交、历史未决）时 ``analyze`` **绝不删**，仅当该目录**全部**记录都是
  ``queued`` 且**每个** queue_id 都被远端确认终态时才精确删除；存在 ``submitting``、记录
  缺失/不可读、或任一 queue 未终态 → ``unresolved`` 保留。**绝不按 TTL 猜删**（判据始终
  是显式所有权 + 远端终态，不是时间）。持久轮转游标防止永久未决目录饿死后面的可清理目录；
  reaper 需按部署周期运行（test.gpu2 上为 15 分钟 systemd timer）。
  **已知边界（未解决）**：算法侧 Celery ``result_expires=86400``，超过 24 小时后 queue_id
  永远只返回 ``PENDING``，该目录将**无限期保留**（``unresolved``）。需要一个经批准的重
  留上限或算法侧按 task_id 查询合同来收口；在此之前只能靠监控 ``unresolved`` 计数告警。
- 仍阻断激活（需算法侧合同）：①POST 已受理但 ack 丢失 → 记录停在 ``submitting``，现有
  GET-by-queue_id 无法确认消费结束；②``TASK_ID_CONFLICT``/``INTERRUPTED`` 会让内容派生的
  ``task_id`` **永久不可用**，需算法侧提供 task_id 重置或版本化命名空间。二者解决前
  provider 不得正式激活。
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
_STAGE_RE = re.compile(r"^sg-[0-9a-f]{40}$")  # = derive_task_id 输出：内容确定目录名
_SUBMISSIONS = ".submissions"  # 每次提交一条所有权记录（O_EXCL 追加，无需跨进程锁）
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
    """确定性输入/绑定问题 → 终态 ``PROVIDER_CONTRACT_VIOLATION``。

    覆盖：缺视图/超限/非 JPEG-PNG/重复三图；以及算法侧对同一 ``task_id`` **永久**成立的
    ``TASK_ID_CONFLICT``（指纹已绑定其他输入或评分版本）与 ``INTERRUPTED``（服务端上次
    执行硬崩溃、未写 result.json）——两者重试必然重现，故终态而非可重试。
    """


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
        stage_dir, rel, nonce = self._stage(images, task_id)
        queue_id, score_source = self._submit(task_id, rel)
        record_error = False
        try:
            self._record_submission(stage_dir, nonce, queue_id)
        except OSError:
            # POST 已受理；记录停在 submitting → reaper 永久保留该目录供对账，绝不猜删。
            record_error = True
        if record_error:
            raise ShuiguangStagingError(
                "shuiguang queue ownership persist failed; check " + SHUIGUANG_INPUT_ROOT_ENV
            ) from None
        groups = self._poll(queue_id)
        # 已确认回收结果：若本次是该目录的**唯一所有者**（所有权日志只有本条记录）→ 就地
        # 清理，图片零滞留。存在其它记录（同内容兄弟提交/历史未决）时**绝不删**——排队任务
        # 在执行时才读图，删了会饿死兄弟；这种情况一律交给 reaper 按"全部 queue 终态"判定。
        self._cleanup_if_sole_owner(stage_dir, nonce)
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

    def _stage(
        self, images: dict[str, bytes], task_id: str
    ) -> tuple[Path, list[tuple[str, str]], str]:
        """内容确定暂存 ``{root}/{task_id}/{view}.{ext}``；返回 (目录, 相对路径, 本次 nonce)。

        路径**必须由内容确定**：算法侧把每张图的 ``path`` 计入 ``task_id`` 指纹，任何每次
        提交都变化的路径都会让同内容重提退化为 ``TASK_ID_CONFLICT``（活体实证），并白白
        丢掉算法侧的幂等结果缓存。
        """
        job_dir = self._root / task_id
        rel: list[tuple[str, str]] = []
        tmp_names: list[Path] = []
        failure: Optional[OSError] = None
        try:
            job_dir.mkdir(parents=True, exist_ok=True)  # 同内容兄弟提交共享此目录
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
                os.replace(tmp, target)  # 原子；并发同内容双方均呈现完整同字节
                tmp_names.remove(tmp)
                rel.append((view, f"{task_id}/{view}.{ext}"))
        except OSError as exc:
            failure = exc
        if failure is not None:
            # 目录可能已被兄弟提交创建/共享：**只删本次调用追踪的临时文件**，绝不删目录
            # 或既有目标（可能正被已排队的算法 job 读取）。
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
        nonce = uuid.uuid4().hex
        # POST **之前**落盘 submitting 记录：reaper 见 submitting 一律保留（POST 在途/ack 丢失）。
        self._record_submission(job_dir, nonce, None)
        return job_dir, rel, nonce

    def _record_submission(self, stage_dir: Path, nonce: str, queue_id: Optional[str]) -> None:
        """写入/升级一条所有权记录 ``.submissions/{nonce}.json``。

        每次提交一个独立文件（O_EXCL 独占创建）→ 无读改写、无需跨进程锁；升级为
        ``queued`` 时用 temp + ``os.replace`` 原子替换，读者只会看到完整旧值或完整新值。
        """
        journal = stage_dir / _SUBMISSIONS
        journal.mkdir(exist_ok=True)
        os.chmod(journal, self._dir_mode)  # 免 umask
        body = {"schema_version": 2,
                "state": "queued" if queue_id is not None else "submitting",
                "queue_id": queue_id}
        tmp = journal / (nonce + "." + uuid.uuid4().hex + ".tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, self._file_mode)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(body, fh, separators=(",", ":"))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, journal / (nonce + ".json"))
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def _cleanup_if_sole_owner(self, stage_dir: Path, nonce: str) -> None:
        """结果已确认回收后，**仅当本次是目录唯一所有者**时就地清理暂存图片。

        判据是显式的所有权日志（``.submissions/`` 下恰有一条、且就是本次 nonce），不是从
        当前照片推断——推断式清理已被 Oracle 第二轮实证为破坏性（会删掉新活跃 job 的暂存）。
        存在任何其它记录时不删：同内容兄弟提交共享此目录，而算法侧排队任务在**执行时**才
        读图（``safe_inputs`` 先于幂等判定），删了会让兄弟拿到 ``INVALID_INPUT``。这些情况
        由 reaper 按"全部 queue_id 均远端终态"统一清理。

        清理失败**绝不影响已成功的结果**（不可让报告重试），残留由 reaper 兜底。

        残余竞态（已评估为良性）：判据检查与 ``rmtree`` 之间若恰好有兄弟提交追加记录，该
        兄弟会在执行时读不到图 → 算法返回 ``INVALID_INPUT`` → 本项目判为**可重试** → 重试
        重新暂存（路径由内容确定，故直接命中算法侧幂等缓存，免重跑 GPU）→ 自愈。既不产生
        错误结果，也不丢数据。
        """
        try:
            records = [
                item.name for item in (stage_dir / _SUBMISSIONS).iterdir()
                if item.suffix == ".json"
            ]
        except OSError:
            return  # 日志不可读 → 无法证明唯一所有权 → 保留，交 reaper
        if records != [nonce + ".json"]:
            return
        self._remove_stage(stage_dir)

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
        """重查每个目录内**全部**所有权记录；只在所有 queue_id 都远端终态后删除。"""
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
            if self._all_entries_terminal(stage_dir) and self._remove_stage(stage_dir):
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

    def _all_entries_terminal(self, stage_dir: Path) -> bool:
        """目录内**每一条**记录都是 ``queued`` 且其 queue_id 被远端确认终态 → True。

        同内容的多次提交共享此目录，每次 POST 又是独立 queue 条目、在执行时才读图；因此
        只要有一条 ``submitting``（POST 在途/ack 丢失）或任一 queue 未终态，删除就会饿死
        兄弟条目 → 一律 False 保留。记录缺失/不可读同样 False（无法证明远端已消费完）。
        """
        journal = stage_dir / _SUBMISSIONS
        try:
            entries = sorted(p for p in journal.iterdir() if p.suffix == ".json")
        except OSError:
            return False
        if not entries:
            return False
        queue_ids: list[str] = []
        for entry in entries:
            try:
                st = entry.lstat()
                if not stat.S_ISREG(st.st_mode) or st.st_size > 4096:
                    return False
                record = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                return False
            if not isinstance(record, dict) or record.get("state") != "queued":
                return False
            queue_id = record.get("queue_id")
            if not isinstance(queue_id, str) or not queue_id:
                return False
            queue_ids.append(queue_id)
        for queue_id in queue_ids:
            try:
                status, payload = self._do_request(
                    "GET", "/api/score-jobs/" + quote(queue_id, safe=""), None
                )
            except ProviderUnavailable:
                return False
            if not self._terminal(status, payload):
                return False
        return True

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
        if code == "TASK_ID_CONFLICT":
            # 算法侧 request.json 已绑定不同指纹（含 path/VERSION/参考 sha）→ 对内容派生的
            # 同一 task_id **永久**成立；重试必然再冲突 → 终态，绝不制造重试风暴。
            raise ShuiguangInputViolation(
                "shuiguang task_id is bound to a different input fingerprint (TASK_ID_CONFLICT)"
            )
        if code == "INTERRUPTED":
            # 服务端上次执行硬崩溃且未写 result.json → 同 task_id 永久 INTERRUPTED → 终态。
            raise ShuiguangInputViolation(
                "shuiguang task_id was interrupted server-side and requires a new id (INTERRUPTED)"
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
