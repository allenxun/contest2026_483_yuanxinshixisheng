# -*- coding: utf-8 -*-
"""E 独立 A 基线验收驱动：参数化隔离资源 + 真实 Java/Python/PG。

只读被测代码（不执行 A 的 backend/tests/run-acceptance.sh 或 deploy/dev 固定端口脚本），
E 自建 PG 容器 mvp-e-pg@127.0.0.1:55433、Java@18081、worker 健康@18082。
证据写 backend/acceptance/reports/（gitignored）与
backend/acceptance/evidence/A-baseline-<UTC日期>/（随代码提交）。
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import time
import uuid

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]        # backend/acceptance
REPO = ROOT.parents[1]                                     # repo root
JAVA_DIR = REPO / "backend" / "web-java"
WORKER_DIR = REPO / "backend" / "worker-python"
CONTRACTS = REPO / "backend" / "contracts"
VENV = ROOT / ".venv-driver"
PY = VENV / "bin" / "python"
PYTEST = VENV / "bin" / "pytest"

PG_CONTAINER = "mvp-e-pg"
PG_IMAGE = "postgres:16"
PG_HOST_PORT = 55433
PG_USER = "postgres"
PG_PASSWORD = "mvp_e_local"
PG_DB = "mvp_e_dev"
APP_PORT = 18081
WORKER_HEALTH_PORT = 18082
APP_BASE = f"http://127.0.0.1:{APP_PORT}"
WORKER_BASE = f"http://127.0.0.1:{WORKER_HEALTH_PORT}"

DATE_UTC = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
RUN_ID = "E-AB-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
REPORTS = ROOT / "reports" / RUN_ID
EVID = ROOT / "evidence" / f"A-baseline-{DATE_UTC}"
LOGS = EVID / "logs"

# 固定命名空间（与 Java/Python 一致：Uuid5.FIXED_NS）
FIXED_NS = uuid.UUID("f988d041-6031-5120-8075-f90b6b05553e")
SUFFIX = uuid.uuid4().hex[:8]


class Results:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, cid: str, title: str, status: str, command: str = "",
            rc: int | str = "", excerpt: str = "", doubles: str = "",
            blocked: str = "") -> None:
        if blocked:
            excerpt = blocked
        self.rows.append({"id": cid, "title": title, "status": status, "command": command,
                          "rc": rc, "excerpt": " ".join((excerpt or "").split())[:400],
                          "doubles": doubles or "doubles_pass"})
        mark = {"PASS": "PASS", "FAIL": "FAIL", "BLOCKED": "BLOCKED", "INFO": "INFO"}[status]
        print(f"[{mark:7}] {cid:8} {title}")

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r["status"] == status)


R = Results()


def run(cmd, cwd=None, env=None, timeout=900, log_name=None):
    """运行命令，输出写入 reports/<RUN_ID>/<log_name>。返回 CompletedProcess。"""
    full_env = {**os.environ, **(env or {})}
    cp = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=full_env, timeout=timeout,
                        capture_output=True, text=True)
    if log_name:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / log_name).write_text(
            f"$ {' '.join(map(str, cmd))}\n\n[stdout]\n{cp.stdout}\n\n[stderr]\n{cp.stderr}\n",
            encoding="utf-8")
    return cp


def psql(sql: str, db: str = PG_DB, tuples_only: bool = True, check: bool = False):
    args = ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", PG_USER, "-d", db,
            "-v", "ON_ERROR_STOP=1"]
    if tuples_only:
        args += ["-tA"]
    args += ["-c", sql]
    cp = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if check and cp.returncode != 0:
        raise RuntimeError(f"psql failed: {cp.stderr.strip()[:300]}")
    return cp


def sql_scalar(sql: str, db: str = PG_DB) -> str:
    cp = psql(sql, db=db)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def wait_http(url: str, timeout_s: int = 120, expect: int = 200) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            r = requests.get(url, timeout=3, proxies=None)
            if r.status_code == expect:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def check_ports() -> dict[str, bool]:
    """启动前检查全部三端口（E 专用）。"""
    return {str(p): port_free(p) for p in (PG_HOST_PORT, APP_PORT, WORKER_HEALTH_PORT)}


LOCK_FILE = ROOT / "reports" / ".a-baseline.lock"


def acquire_single_instance_lock() -> tuple[bool, str]:
    """E 入口单实例锁：lockfile + PID 活性。返回 (ok, reason)。"""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        parts = LOCK_FILE.read_text(encoding="utf-8").split()
        pid = int(parts[0]) if parts and parts[0].isdigit() else None
        if pid and pathlib.Path(f"/proc/{pid}").exists():
            return False, f"另一 E a-baseline 运行中（pid={pid}，lock={LOCK_FILE}）"
        LOCK_FILE.unlink(missing_ok=True)  # 陈旧锁：持有进程已死
    LOCK_FILE.write_text(f"{os.getpid()} {RUN_ID}\n", encoding="utf-8")
    return True, ""


def release_single_instance_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def container_owned_by_run() -> bool:
    """容器是否带本次 run 标签（清理所有权保护）。"""
    cp = subprocess.run(["docker", "inspect", "--format",
                         '{{index .Config.Labels "mvp.e.run"}}', PG_CONTAINER],
                        capture_output=True, text=True)
    return cp.returncode == 0 and cp.stdout.strip() == RUN_ID


def remove_container() -> None:
    """只清理本 run 创建的容器（label 归属校验；不属于本 run 则拒绝删除）。"""
    if container_owned_by_run():
        subprocess.run(["docker", "rm", "-f", "-v", PG_CONTAINER], capture_output=True, text=True)
    elif container_exists():
        raise RuntimeError(f"容器 {PG_CONTAINER} 不属于本 run({RUN_ID})，拒绝清理")


def container_exists() -> bool:
    cp = subprocess.run(["docker", "inspect", "--format", "{{.Name}}", PG_CONTAINER],
                        capture_output=True, text=True)
    return cp.returncode == 0


def start_pg() -> subprocess.CompletedProcess:
    if container_exists():
        raise RuntimeError(f"容器 {PG_CONTAINER} 已存在且非本 run 所有；拒绝启动/覆盖")
    return run(["docker", "run", "-d", "--name", PG_CONTAINER,
                "--label", f"mvp.e.run={RUN_ID}",
                "-e", f"POSTGRES_PASSWORD={PG_PASSWORD}", "-e", f"POSTGRES_DB={PG_DB}",
                "-p", f"127.0.0.1:{PG_HOST_PORT}:5432", PG_IMAGE], log_name="pg-run.log")


def wait_pg(timeout_s: int = 90) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        cp = psql("SELECT 1", db="postgres")
        if cp.returncode == 0:
            return True
        time.sleep(2)
    return False


def recreate_db() -> None:
    psql(f"DROP DATABASE IF EXISTS {PG_DB} WITH (FORCE)", db="postgres")
    psql(f"CREATE DATABASE {PG_DB}", db="postgres", check=True)


JAVA_ENV = {
    "SERVER_PORT": str(APP_PORT),
    "SPRING_PROFILES_ACTIVE": "dev",
    "SPRING_DATASOURCE_URL": f"jdbc:postgresql://127.0.0.1:{PG_HOST_PORT}/{PG_DB}",
    "SPRING_DATASOURCE_USERNAME": PG_USER,
    "SPRING_DATASOURCE_PASSWORD": PG_PASSWORD,
    "APP_STORAGE_DEV_DIR": str(REPORTS / "storage"),
    "APP_MEDIA_ACCESS_MODE": "deny-all",
}

JAVA_PROC: subprocess.Popen | None = None
WORKER_PROC: subprocess.Popen | None = None


def java_jar() -> pathlib.Path:
    jars = sorted((JAVA_DIR / "target").glob("web-java-*.jar"))
    jars = [j for j in jars if "sources" not in j.name and "javadoc" not in j.name]
    return jars[0]


def wait_java_ready(timeout_s: int = 150) -> bool:
    """健康判定绑定本 run 的 Java 子进程：进程死亡立即判定失败（不误报 UP）。"""
    end = time.time() + timeout_s
    while time.time() < end:
        if JAVA_PROC is None or JAVA_PROC.poll() is not None:
            return False
        try:
            r = requests.get(f"{APP_BASE}/actuator/health", timeout=3, proxies=None)
            if r.status_code == 200 and '"status":"UP"' in r.text:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_java(extra_env=None, log_name="java-app-1.log", wait=True):
    global JAVA_PROC
    (REPORTS / "storage").mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **JAVA_ENV, **(extra_env or {})}
    logf = open(REPORTS / log_name, "w", encoding="utf-8")
    JAVA_PROC = subprocess.Popen(["java", "-jar", str(java_jar())], cwd=str(JAVA_DIR), env=env,
                                 stdout=logf, stderr=subprocess.STDOUT)
    if wait:
        return wait_java_ready()
    return True


def java_alive() -> bool:
    return JAVA_PROC is not None and JAVA_PROC.poll() is None


def stop_java(timeout_s: int = 40) -> None:
    global JAVA_PROC
    if JAVA_PROC is None:
        return
    if JAVA_PROC.poll() is None:
        JAVA_PROC.send_signal(signal.SIGTERM)
        try:
            JAVA_PROC.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            JAVA_PROC.kill()
            JAVA_PROC.wait(timeout=10)
    JAVA_PROC = None


WORKER_ENV = {
    "MVP_WORKER_PG_DSN": f"postgresql://{PG_USER}:{PG_PASSWORD}@127.0.0.1:{PG_HOST_PORT}/{PG_DB}",
    "MVP_WORKER_HEALTH_HOST": "127.0.0.1",
    "MVP_WORKER_HEALTH_PORT": str(WORKER_HEALTH_PORT),
    "MVP_CONTRACTS_DIR": str(CONTRACTS),
    "MVP_A_STORAGE_DEV_DIR": str(REPORTS / "storage"),
    "PYTHONPATH": str(WORKER_DIR / "src"),
}


def start_worker():
    global WORKER_PROC
    logf = open(REPORTS / "worker-loop.log", "w", encoding="utf-8")
    WORKER_PROC = subprocess.Popen([str(PY), "-m", "mvp_worker"], cwd=str(WORKER_DIR),
                                   env={**os.environ, **WORKER_ENV},
                                   stdout=logf, stderr=subprocess.STDOUT)
    return WORKER_PROC


def stop_worker(timeout_s: int = 40) -> None:
    global WORKER_PROC
    if WORKER_PROC is None:
        return
    if WORKER_PROC.poll() is None:
        WORKER_PROC.send_signal(signal.SIGTERM)
        try:
            WORKER_PROC.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            WORKER_PROC.kill()
            WORKER_PROC.wait(timeout=10)
    WORKER_PROC = None


def worker_once(env_extra=None, timeout=180):
    return run([str(PY), "-m", "mvp_worker", "--once"], cwd=WORKER_DIR,
               env={**WORKER_ENV, **(env_extra or {})}, timeout=timeout,
               log_name="worker-once.log")


def worker_cli(arg: str, env_extra=None, timeout=120):
    return run([str(PY), "-m", "mvp_worker", arg], cwd=WORKER_DIR,
               env={**WORKER_ENV, **(env_extra or {})}, timeout=timeout,
               log_name=f"worker-{arg.strip('-')}.log")


_SESSION = requests.Session()
_SESSION.trust_env = False


def http(method: str, path: str, token: str | None = None, body=None, headers=None
         ) -> tuple[int, dict, dict[str, str]]:
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = _SESSION.request(method, f"{APP_BASE}{path}", headers=h,
                         data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                         timeout=20)
    try:
        parsed = r.json()
    except Exception:
        parsed = {"_raw": r.text[:200]}
    return r.status_code, parsed, dict(r.headers)


def evidence_text(name: str, content: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / name).write_text(content, encoding="utf-8")
