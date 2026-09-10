# -*- coding: utf-8 -*-
"""数据隔离机制与约定（只提供机制，不连接任何真实数据库）。

约定（详见 plans/isolation-and-doubles.md）：
- 每次运行生成唯一 run-id：``<前缀>-<UTC时间戳>-<随机hex>``；本次运行创建的一切
  可命名资源（手机号虚拟段、账号显示名、云台/微晶标识、OSS 前缀等）都必须带
  ``EACC_<run_id>_`` 数据前缀，使并行工作树互不污染、可按前缀清理。
- E 专用 PostgreSQL：库名必须以 ``eaccept_`` 开头、独立端口（样例 15432）、
  专用低权限账号。validate_env_safety 会拒绝疑似共享/生产库，fail-closed。
- 清理策略：优先整库 drop（测试库允许时）；否则按 run-id 前缀删除。清理入口
  cleanup_plan() 返回应执行的动作清单，由持凭据的环境执行。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
import secrets

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*-\d{8}T\d{6}Z-[0-9a-f]{8}$")
E_DB_PREFIX = "eaccept_"

ENV_BASE_URL = "E_ACCEPTANCE_BASE_URL"
ENV_RUN_PREFIX = "E_ACCEPTANCE_RUN_ID_PREFIX"
ENV_PG_HOST = "E_ACCEPTANCE_PG_HOST"
ENV_PG_PORT = "E_ACCEPTANCE_PG_PORT"
ENV_PG_DB = "E_ACCEPTANCE_PG_DATABASE"
ENV_PG_USER = "E_ACCEPTANCE_PG_USER"          # 密码只走 PGPASSWORD 等运行时凭据，不落盘
ENV_EVIDENCE_DIR = "E_ACCEPTANCE_EVIDENCE_DIR"

ALL_ENV_KEYS = (ENV_BASE_URL, ENV_RUN_PREFIX, ENV_PG_HOST, ENV_PG_PORT,
                ENV_PG_DB, ENV_PG_USER, ENV_EVIDENCE_DIR)


def new_run_id(prefix: str = "E") -> str:
    """唯一运行标识，如 E-20260910T073000Z-1f9c2a44。"""
    prefix = re.sub(r"[^A-Za-z0-9._-]", "", prefix) or "E"
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}-{secrets.token_hex(4)}"


def data_prefix(run_id: str) -> str:
    """本次运行所有可命名测试数据的统一前缀。"""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"run-id 格式非法：{run_id}")
    tag = hashlib.sha256(run_id.encode()).hexdigest()[:8]
    return f"EACC_{tag}_"


def acceptance_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    """读取 E 专用环境（缺失项报错，不给默认生产值）。"""
    env = environ if environ is not None else dict(os.environ)
    missing = [k for k in (ENV_BASE_URL, ENV_PG_DB) if not env.get(k)]
    if missing:
        raise RuntimeError(f"缺少 E 隔离环境变量：{missing}（见 config/acceptance.env.example）")
    return env


def validate_env_safety(env: dict[str, str]) -> None:
    """fail-closed 安全检查：非 E 专用库名/可疑端口直接拒绝。"""
    db = env.get(ENV_PG_DB, "")
    if not db.startswith(E_DB_PREFIX):
        raise RuntimeError(
            f"PG 库名 {db!r} 不以 {E_DB_PREFIX!r} 开头：拒绝在疑似共享/生产库上跑清理型验收")
    port = env.get(ENV_PG_PORT, "")
    if port and port == "5432":
        raise RuntimeError("拒绝默认端口 5432：每 worktree 应使用隔离端口（样例 15432）")


def cleanup_plan(run_id: str, env: dict[str, str]) -> list[str]:
    """返回清理动作清单（机制/约定层；不在此执行 SQL）。"""
    dp = data_prefix(run_id)
    return [
        f"确认 PG 库 {env[ENV_PG_DB]} 通过 validate_env_safety 后：",
        f"  方案A（推荐，测试库）：DROP DATABASE {env[ENV_PG_DB]}; 由下一次运行重建",
        f"  方案B（保留库）：按数据前缀 {dp} 删除本 run-id 创建的账号/云台/微晶/"
        f"测肤任务/方案/执行/记录/通知目标（依赖各表归属字段，级联顺序见 plans）",
        f"  OSS：删除前缀 {dp} 下对象（凭据仅存在于运行环境）",
        f"  证据归档：reports/evidence/{run_id}/ 保留，不入 Git",
    ]
