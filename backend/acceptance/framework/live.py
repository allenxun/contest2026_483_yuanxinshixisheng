# -*- coding: utf-8 -*-
"""集成轮真实场景级实测：活体服务生命周期与 B/C 黑盒辅助。

仅在 gate=open 的 matrix 运行中由 tests/scenarios/conftest.py 调用；复用
driver/infra.py 的 E 专用资源（mvp-e-pg@55433 / Java@18081 / worker@18082）。
selfcheck、c-acceptance 等模式不触发本模块。
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import pathlib
import signal
import subprocess
import time
import uuid

import requests

from driver import infra as I
from driver import c_care as CC
from driver import a_baseline as AB

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = I.APP_BASE

#: dev/test 配对/连接证明固定密钥（与 B DevProofCodec.DEV_TEST_KEY 一致）。
DEV_TEST_KEY = "mvp-b-dev-test-proof-key-v1"

#: B DevTestFaceIdentityResolver 身份命名空间默认值（app.identity.namespace:mvp-local）。
FACE_NAMESPACE = "mvp-local"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def encode_proof(payload: dict, version: str = "d1",
                 key: str = DEV_TEST_KEY) -> str:
    """生成 B dev/test 证明：``<version>.<b64url(payloadJson)>.<b64url(hmac)>``。"""
    payload_b64 = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    sig = _b64(hmac.new(key.encode(), payload_b64.encode(), hashlib.sha256).digest())
    return f"{version}.{payload_b64}.{sig}"


def pairing_proof(gimbal_id: str, account_id: str, installation_id: str, *,
                  purpose: str = "pairing", nonce: str | None = None,
                  ttl_s: int = 600, version: str = "d1") -> str:
    return encode_proof({
        "purpose": purpose, "gimbalId": gimbal_id, "accountId": account_id,
        "installationId": installation_id, "nonce": nonce or uuid.uuid4().hex,
        "exp": int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + ttl_s,
    }, version)


def app_login(tag: str | None = None) -> dict | None:
    """建立 APP 会话，phone 由 tag 的 sha256 唯一派生（不同 tag → 不同账号）。

    复用 A 的 SMS 替身（固定码 123456）；不使用 AB.login 的 hex 解析，避免
    非 hex tag（如 sc0105a/b）数字抽取相同导致账号碰撞。
    """
    tag = tag or uuid.uuid4().hex[:10]
    digits = f"{int(hashlib.sha256(tag.encode()).hexdigest(), 16) % 100000000:08d}"
    phone = f"+86138{digits}"
    installation = f"e-inst-{tag}"
    code, body, _ = I.http("POST", "/api/v1/auth/sms-challenges",
                           body={"phone": phone, "purpose": "login"})
    if code != 200:
        return None
    chal = (body.get("data") or {}).get("challengeId")
    code, body, _ = I.http("POST", "/api/v1/auth/sessions",
                           body={"challengeId": chal, "code": "123456",
                                 "installationId": installation})
    if code != 200:
        return None
    d = body["data"]
    return {"phone": phone, "accountId": d["accountId"], "installationId": installation,
            "access": d["accessToken"], "refresh": d["refreshToken"]}


def gimbal_session(gimbal_id: str, credential_version: str = "1",
                   credential: str | None = None, proof: str = "p") -> tuple[int, dict, dict]:
    return I.http("POST", "/api/v1/gimbal-sessions", body={
        "credential": credential or f"gimbal-subj-{gimbal_id}",
        "credentialVersion": credential_version, "proof": proof})


def seed_member_face(mid: str | None = None, image: bytes | None = None) -> tuple[str, bytes]:
    """植入可靠成员：identity_namespace=mvp-local、face_subject_ref=sha256(图片)。"""
    image = image if image is not None else _png()
    m = mid or str(uuid.uuid4())
    ref = hashlib.sha256(image).hexdigest()
    CC.sql("INSERT INTO members (id, identity_namespace, face_subject_ref, status) "
           f"VALUES ('{m}','{FACE_NAMESPACE}','{ref}','active')")
    return m, image


def _png() -> bytes:
    """最小合法 PNG（格式嗅探要求真实图片头）。"""
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def multipart_grant(token: str, image: bytes, *, purpose: str = "grant",
                    key: str | None = None, metadata_extra: dict | None = None):
    """M1-A01 multipart：metadata/face **两段均为文件**（B 控制器要求 getFileMap 恰两段）。"""
    md = {"capture": {"captureId": str(uuid.uuid4()),
                      "capturedAt": datetime.datetime.now(datetime.timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "clientContinuityId": "cc-grant", "purpose": purpose},
          "consentEvidenceRef": "consent-grant"}
    if metadata_extra:
        md.update(metadata_extra)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": key or str(uuid.uuid4())}
    files = {"metadata": ("metadata.json", json.dumps(md).encode(), "application/json"),
             "face": ("face.png", image, "image/png")}
    try:
        r = requests.post(I.APP_BASE + "/api/v1/member-access-grants", headers=headers,
                          files=files, timeout=30, proxies=None)
        return r.status_code, (r.json() if r.text else {})
    except Exception as exc:  # pragma: no cover
        return 0, {"exception": repr(exc)}


def gimbal_with_token() -> tuple[str, str | None]:
    """新建云台并签发设备会话；返回 (gimbalId, token)。"""
    g = CC.seed_gimbal()
    return g, CC.gimbal_token(g)


def _multipart_post(path: str, token: str, key: str, metadata: dict,
                    images: dict[str, bytes], method: str = "POST") -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": key}
    files = [("metadata", ("metadata.json", json.dumps(metadata).encode(), "application/json"))]
    for name, data in images.items():
        files.append((name, (f"{name}.png", data, "image/png")))
    try:
        r = requests.request(method, I.APP_BASE + path, headers=headers, files=files,
                             timeout=60, proxies=None)
        return r.status_code, (r.json() if r.text else {})
    except Exception as exc:  # pragma: no cover
        return 0, {"exception": repr(exc)}


def images3(seed: bytes | None = None) -> dict[str, bytes]:
    base = seed if seed is not None else _png()
    return {"front": base + b"F", "left": base + b"L", "right": base + b"R"}


def multipart_a01(token: str, key: str, *, photo_version: str = "1",
                  images: dict[str, bytes] | None = None,
                  capture_session_id: str | None = None) -> tuple[int, dict]:
    md = {"photoVersion": photo_version,
          "captureSessionId": capture_session_id or f"cs-{uuid.uuid4().hex[:8]}",
          "consentEvidenceRef": "consent-m3"}
    return _multipart_post("/api/v1/skin-assessment-tasks", token, key, md,
                           images if images is not None else images3())


def multipart_a02(token: str, key: str, task_id: str, photo_version: str,
                  metadata: dict, images: dict[str, bytes]) -> tuple[int, dict]:
    return _multipart_post(f"/api/v1/skin-assessment-tasks/{task_id}/photo-versions/"
                           f"{photo_version}", token, key, metadata, images, method="PUT")


def scanners_once(env_extra: dict | None = None):
    """手动事件发现（C8：scanner 周期未接线，集成轮以 --once 触发并披露）。"""
    return I.run([str(I.PY), "-m", "mvp_worker.scanners", "--once"], cwd=I.WORKER_DIR,
                 env={**I.WORKER_ENV, **(env_extra or {})}, timeout=180,
                 log_name="scanners-once.log")


# ---------------- 注入 seam 复验辅助（B-seam-repro handoff） ----------------
#
# 全部为测试驱动侧辅助：只组 env / 起后台 --once 进程 / 等待文件 / 读日志，
# 不写任何业务表、不伪造 DB 状态。注入旋钮本身由被测 worker/Java 读取。

def marker_image(tag: str | None = None) -> bytes:
    """最小合法 PNG + 唯一尾标记（sha256 命中 barrier 用；与 _png 头兼容）。"""
    return _png() + b"marker-" + (tag or uuid.uuid4().hex).encode() + b"-" \
        + uuid.uuid4().hex.encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def barrier_dir(tag: str) -> pathlib.Path:
    """每 RUN_ID + tag 独立的 barrier sentinel 目录（绝不共享默认临时目录）。"""
    d = I.REPORTS / f"barrier-{I.RUN_ID}-{tag}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def barrier_env(directory, marker_sha256: str, timeout_s: int = 180) -> dict:
    """SC-02-09 barried env：一次性、有界、显式 DIR/SHA256/TIMEOUT。"""
    return {
        "MVP_D_DOUBLE_LATE_BARRIER": "true",
        "MVP_D_DOUBLE_LATE_BARRIER_DIR": str(directory),
        "MVP_D_DOUBLE_LATE_BARRIER_SHA256": marker_sha256,
        "MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS": str(timeout_s),
    }


def start_bg_worker(env_extra: dict | None, log_name: str):
    """后台 `mvp_worker --once`（轻量 python 进程）；返回 (Popen, log_path)。

    仅供 SC-02-09 的 worker A/B 交错使用；调用方必须回收（stop_bg_worker）。
    """
    log = I.REPORTS / log_name
    f = open(log, "w", encoding="utf-8")
    env = {**os.environ, **I.WORKER_ENV, **(env_extra or {})}
    proc = subprocess.Popen([str(I.PY), "-m", "mvp_worker", "--once"],
                            cwd=str(I.WORKER_DIR), env=env,
                            stdout=f, stderr=subprocess.STDOUT)
    return proc, log


def stop_bg_worker(proc, timeout_s: int = 10) -> None:
    """进程卫生：kill → 有界等待 → kill -9，绝不遗留后台 worker。"""
    if proc is None:
        return
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def wait_path(path, timeout_s: float = 60.0, poll: float = 0.2) -> bool:
    """等待文件出现（barrier consumed 等）；有界轮询。"""
    end = time.time() + timeout_s
    while time.time() < end:
        if pathlib.Path(path).exists():
            return True
        time.sleep(poll)
    return pathlib.Path(path).exists()


def log_text(path) -> str:
    p = pathlib.Path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def log_has(path, substr: str) -> bool:
    return substr in log_text(path)


def sql_json(sql: str):
    """取 jsonb 列并解析为 Python 对象（列缺失/非 JSON 返回 None）。"""
    raw = I.sql_scalar(sql)
    if not raw or raw == "":
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


#: D 受控能力基线（与 worker dshared.dconfig.DEFAULT_PLAN_CAPABILITY_BASELINE 一致）。
CAP_BASELINE = {
    "capability_id": "mvp-double-capability",
    "revision": "1",
    "parameter_ranges": {
        "intensity": {"unit": "percent", "min": 0.0, "max": 100.0},
        "duration": {"unit": "second", "min": 1.0, "max": 600.0},
        "pulse_count": {"unit": "count", "min": 1.0, "max": 1000.0},
    },
    "approved_regions": ["forehead", "left_cheek", "right_cheek", "nose"],
    # C 能力校验器读取设备支持区域键为 supported_regions（冻结基线用 approved_regions）。
    "supported_regions": ["forehead", "left_cheek", "right_cheek", "nose"],
    "n_bounds": {"min": 1, "max": 100},
}


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connection_proof(serial: str, *, observer_type: str, observer_ref: str,
                     account_id: str | None = None, installation_id: str | None = None,
                     gimbal_id: str | None = None, ttl_s: int = 600) -> str:
    payload = {"purpose": "connection", "microcrystalSerial": serial,
               "observerType": observer_type, "observerRef": observer_ref,
               "exp": int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + ttl_s,
               "nonce": uuid.uuid4().hex}
    if observer_type == "app_account":
        payload["accountId"] = account_id
        payload["installationId"] = installation_id
    else:
        payload["gimbalId"] = gimbal_id
    return encode_proof(payload)


def observe_microcrystal(sess, serial: str, caps: dict, *, epoch: str | None = None,
                         seq: str = "1") -> tuple[int, dict, dict]:
    """真实 B M2-A04 观察（APP observer）；caps 覆盖 capability_id/revision/ranges/regions/n_bounds。"""
    proof = connection_proof(serial, observer_type="app_account",
                             observer_ref=f"{sess['accountId']}:{sess['installationId']}",
                             account_id=sess["accountId"],
                             installation_id=sess["installationId"])
    body = {"microcrystalSerial": serial, "connectionProof": proof,
            "capabilities": {"schemaVersion": 1, **caps},
            "observationEpoch": epoch or f"obs-{uuid.uuid4().hex[:8]}",
            "observationSeq": seq, "observedAt": utcnow_iso(),
            "state": {"mode": "idle", "source": "e_acceptance"}}
    return I.http("POST", "/api/v1/microcrystal-observations", token=sess["access"],
                  body=body, headers={"Idempotency-Key": str(uuid.uuid4())})


def get_capabilities(microcrystal_id: str, sess=None, *, proof: str | None = None,
                     token: str | None = None) -> tuple[int, dict, dict]:
    headers = {"X-Connection-Proof": proof} if proof else {}
    return I.http("GET", f"/api/v1/microcrystals/{microcrystal_id}/capabilities",
                  token=token or (sess["access"] if sess else None), headers=headers)


# ---------------- 常驻 worker（run_forever + 进程内周期扫描，C8 接线后） ----------------

RESIDENT: dict = {"proc": None, "log": None}


def start_resident_worker(env_extra: dict | None = None) -> subprocess.Popen:
    """启动常驻 worker（run_forever；进程内 incident/media.cleanup 周期扫描）。

    低内存单进程；**不得用于 --once 冒充周期**。结束须 stop_resident_worker()。
    """
    stop_resident_worker()
    log = I.REPORTS / "integration-resident-worker.log"
    f = open(log, "w", encoding="utf-8")
    env = {**os.environ, **I.WORKER_ENV, **(env_extra or {})}
    proc = subprocess.Popen([str(I.PY), "-m", "mvp_worker"], cwd=str(I.WORKER_DIR),
                            env=env, stdout=f, stderr=subprocess.STDOUT)
    RESIDENT["proc"] = proc
    RESIDENT["log"] = log
    return proc


def stop_resident_worker(timeout_s: int = 40) -> None:
    proc = RESIDENT.get("proc")
    if proc is not None and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    RESIDENT["proc"] = None


def wait_cond(sql_cond: str, timeout_s: float = 60.0, poll: float = 1.0) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if I.sql_scalar(sql_cond) == "1":
            return True
        time.sleep(poll)
    return I.sql_scalar(sql_cond) == "1"


def resident_log_has(substr: str) -> bool:
    p = RESIDENT.get("log")
    if p is None or not pathlib.Path(p).exists():
        return False
    return log_has_text(pathlib.Path(p).read_text(encoding="utf-8", errors="replace"), substr)


def log_has_text(text: str, substr: str) -> bool:
    """常驻周期判定纯函数：worker 日志是否出现某任务标记（如 incident.scan）。"""
    return substr in (text or "")


def logout_revision_ok(status: str, rev_after: int, rev_before: int,
                       invalidated_at: str, repeat_idempotent: bool) -> bool:
    """登出代次语义纯函数：status=invalid + revision 恰 +1 + invalidated_at 非空 + 重复幂等。"""
    return (status == "invalid" and int(rev_after) == int(rev_before) + 1
            and bool(invalidated_at) and bool(repeat_idempotent))


# ---------------- 活体服务生命周期 ----------------

STATE: dict[str, object] = {"started": False, "jar_built": False}


def short_sha() -> str:
    cp = subprocess.run(["git", "-C", str(I.REPO), "rev-parse", "--short=12", "HEAD"],
                        capture_output=True, text=True, timeout=30)
    return cp.stdout.strip() or "unknown"


def evidence_base() -> pathlib.Path:
    """证据根：evidence/Integration-<date>-<shortSHA>/（namespace 再补 scenarios/<SC-ID>）。"""
    d = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return I.ROOT / "evidence" / f"Integration-{d}-{short_sha()}"


def build_jar_if_needed() -> bool:
    """从**当前集成树源码**构建 web-java jar；按 HEAD SHA 打戳，HEAD 变化必重建
    （避免复用 B 集成前的陈旧 jar）。"""
    import subprocess as _sp
    head = _sp.run(["git", "-C", str(I.REPO), "rev-parse", "HEAD"],
                   capture_output=True, text=True, timeout=30).stdout.strip()
    stamp = I.JAVA_DIR / "target" / ".integration-built-sha"
    try:
        if head and stamp.read_text(encoding="utf-8").strip() == head and I.java_jar().exists():
            return True
    except Exception:
        pass
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR,
               timeout=2400, log_name="integration-mvn-package.log")
    if cp.returncode == 0 and head:
        stamp.write_text(head, encoding="utf-8")
    return cp.returncode == 0


def start_services() -> None:
    """启动 PG→Java（dev，限堆 640m）；幂等（已启动则跳过）。"""
    if STATE["started"]:
        return
    if not build_jar_if_needed():
        raise RuntimeError("web-java jar 构建失败，无法进入活体矩阵")
    ok, why = I.acquire_single_instance_lock()
    if not ok:
        raise RuntimeError(f"无法取得单实例锁：{why}")
    if I.container_exists():
        # 复用既有 E 容器（stop 保留卷；下次 docker start 复用，recreate_db 保数据新鲜）
        cp = I.run(["docker", "start", I.PG_CONTAINER], timeout=120, log_name="pg-start.log")
        if cp.returncode != 0:
            raise RuntimeError(f"PG 容器复用启动失败：{cp.stdout} {cp.stderr}")
    else:
        cp = I.start_pg()
        if cp.returncode != 0:
            raise RuntimeError(f"PG 容器启动失败：{cp.stdout} {cp.stderr}")
    if not I.wait_pg():
        raise RuntimeError("PG 未就绪")
    I.recreate_db()  # 重建 DB + 迁移（Java dev 启动时 Flyway 迁移）
    import os as _os
    jar = I.java_jar()
    logf = open(I.REPORTS / "integration-java.log", "w", encoding="utf-8")
    env = {**I.JAVA_ENV, "JAVA_TOOL_OPTIONS": "-Xmx640m -XX:MaxMetaspaceSize=256m"}
    I.JAVA_PROC = subprocess.Popen(  # type: ignore[assignment]
        ["java", "-jar", str(jar)], cwd=str(I.JAVA_DIR), env=env,
        stdout=logf, stderr=subprocess.STDOUT)
    if not I.wait_java_ready(240):
        raise RuntimeError("Java(dev) 未就绪")
    STATE["started"] = True


def stop_services() -> None:
    """停止 Java、**stop（不 rm）** PG 容器以保留卷、释放锁（文件保留）。

    总协调 §440 增量纪律：清理改为 `docker stop mvp-e-pg`，保留数据库卷；
    下轮 start_services 复用（recreate_db 保证每 run 数据新鲜）。
    """
    try:
        I.stop_java()
    finally:
        I.kill_own_java()
    try:
        if I.container_exists():
            I.run(["docker", "stop", I.PG_CONTAINER], timeout=180, log_name="pg-stop.log")
    finally:
        I.release_single_instance_lock()
    STATE["started"] = False


def java_env_with_bound_member(member_id: str | None) -> None:
    """按需以合法绑定成员重启 Java（care 准入场景）。"""
    I.stop_java()
    I.kill_own_java()
    extra = {"APP_C_FACE_BOUND_MEMBER": member_id} if member_id else {}
    if not I.start_java(extra_env=extra, log_name="integration-java-bound.log", wait=True):
        raise RuntimeError("Java(bound) 未就绪")

