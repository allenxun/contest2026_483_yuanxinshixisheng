# -*- coding: utf-8 -*-
"""黑盒 HTTP 客户端封装：requests + requestId + 证据落盘设计。

只通过对外 HTTP API 观察系统行为，不做任何业务逻辑、不 import 被测实现。
证据目录约定：reports/evidence/<run-id>/<序号>-<METHOD>-<路径摘要>.json，
内容含请求（**默认脱敏**）、响应状态与响应体摘要、时间戳、requestId。
证据序列化时无条件遮蔽 Authorization / Cookie / Proxy-Authorization / X-Api-Key
（含云台/会话凭据的任何头都不落盘）；调用方 redact_headers 只能**追加**脱敏项，
不能移除默认项。真实凭据一律来自环境变量（见 config/acceptance.env.example）。
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import uuid
from typing import Any

import requests

HEADER_REQUEST_ID = "X-Request-Id"
DEFAULT_TIMEOUT_S = 10.0
USER_AGENT = "e-acceptance-blackbox/0.1"

#: 证据落盘前无条件遮蔽的请求头（小写匹配；调用方只能追加，不能移除）
DEFAULT_REDACT_HEADERS = ("authorization", "cookie", "proxy-authorization", "x-api-key")
REDACTED = "***REDACTED***"


def _path_slug(method: str, path: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", f"{method}_{path}").strip("_")[:120]


def safe_headers(headers: dict[str, str], extra_redact: tuple[str, ...] = ()) -> dict[str, str]:
    """返回可落盘的请求头：默认敏感项值替换为 ***REDACTED***，其余原样。"""
    redact = {h.lower() for h in DEFAULT_REDACT_HEADERS} | {h.lower() for h in extra_redact}
    return {k: (REDACTED if k.lower() in redact else v) for k, v in headers.items()}


class EvidenceRecorder:
    """把每次请求/响应写成 JSON 证据文件。reports/ 已在 .gitignore。"""

    def __init__(self, evidence_dir: pathlib.Path, run_id: str) -> None:
        self.dir = pathlib.Path(evidence_dir) / run_id
        self._seq = 0
        self.count = 0

    def record(self, entry: dict[str, Any]) -> pathlib.Path:
        """共同落盘边界：request_headers 一律过 safe_headers（默认凭据头无条件脱敏，
        覆盖 BlackBoxClient 与 scenario_evidence.record_raw 等所有调用路径；
        幂等，重复调用不会解除遮蔽）。"""
        self.dir.mkdir(parents=True, exist_ok=True)
        self._seq += 1
        self.count += 1
        entry = {**entry,
                 "request_headers": safe_headers(dict(entry.get("request_headers") or {}))}
        name = f"{self._seq:05d}-{_path_slug(entry['method'], entry['path'])}.json"
        p = self.dir / name
        p.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        return p


class BlackBoxClient:
    """带 requestId、超时与证据记录的薄 HTTP 客户端。

    base_url 等参数由调用方从隔离环境（isolation.acceptance_env）注入；
    本模块不读取生产配置，也不提供假 200 —— 连接失败如实抛出。
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        run_id: str = "unassigned",
        evidence_dir: pathlib.Path | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url 必须是 http(s) 地址：黑盒客户端只走 HTTP")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.run_id = run_id
        self.extra_headers = dict(extra_headers or {})
        self.recorder = EvidenceRecorder(evidence_dir, run_id) if evidence_dir else None
        self._session = requests.Session()

    def request(self, method: str, path: str, *, auth_header: str | None = None,
                redact_headers: tuple[str, ...] = (), **kwargs) -> requests.Response:
        """redact_headers 仅可追加脱敏项；默认敏感头遮蔽不可关闭。"""
        rid = kwargs.pop("request_id", None) or str(uuid.uuid4())
        override = kwargs.pop("headers", None) or {}
        headers = {"User-Agent": USER_AGENT, HEADER_REQUEST_ID: rid,
                   **self.extra_headers, **override}
        if auth_header:
            headers["Authorization"] = auth_header
        url = f"{self.base_url}{path}"
        started = time.time()
        resp = self._session.request(method, url, timeout=self.timeout_s, headers=headers, **kwargs)
        if self.recorder:
            self.recorder.record({
                "run_id": self.run_id,
                "request_id": rid,
                "method": method.upper(),
                "path": path,
                "started_at": started,
                "elapsed_ms": round((time.time() - started) * 1000, 1),
                "status": resp.status_code,
                "request_headers": safe_headers(headers, redact_headers),  # recorder 内还会幂等复核
                "request_json": kwargs.get("json"),
                "response_excerpt": resp.text[:4000],
            })
        return resp

    def get(self, path: str, **kw) -> requests.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> requests.Response:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw) -> requests.Response:
        return self.request("PUT", path, **kw)

    def delete(self, path: str, **kw) -> requests.Response:
        return self.request("DELETE", path, **kw)

    def health(self, path: str = "/healthz", **kw) -> requests.Response:
        """健康检查：路径以 A 基线交付说明为准，这里只是探测入口。"""
        return self.get(path, **kw)
