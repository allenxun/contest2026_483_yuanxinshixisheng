from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rag.intent.models import IntentRecognitionResult


@dataclass(frozen=True)
class OOSLogRecord:
    query: str
    oos_summary: str
    business_type: str = ""
    history_summary: str = ""
    metadata: Mapping[str, Any] | None = None
    created_at: str = ""

# OOS 记录的追加写入（JSONL 格式，用于后续聚类分析）
class JSONLOOSStore:
    """Append-only OOS evidence for later clustering and human review."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: OOSLogRecord) -> None:
        value = asdict(record)
        if not value["created_at"]:
            value["created_at"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

# 面向应用的入口，包装 recognizer + OOS 日志
class IntentService:
    """Application-facing intent entry point with conservative OOS retention."""

    def __init__(
        self,
        recognizer,
        *,
        oos_store: JSONLOOSStore | None = None,
        sanitizer: Callable[[str], str] | None = None,
    ):
        self.recognizer = recognizer
        self.oos_store = oos_store
        self.sanitizer = sanitizer or (lambda value: value)

    def recognize(
        self,
        query: str,
        *,
        history: Sequence[tuple[str, str]] = (),
        business_type: str = "",
        pending_context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> IntentRecognitionResult:
        result = self.recognizer.recognize(
            query,
            history=history,
            business_type=business_type,
            pending_context=pending_context,
        )
        if result.status == "oos" and self.oos_store is not None:
            history_summary = "\n".join(
                f"{role}: {content}" for role, content in list(history)[-4:]
            )
            self.oos_store.append(OOSLogRecord(
                query=self.sanitizer(query),
                oos_summary=self.sanitizer(result.oos_summary),
                business_type=business_type,
                history_summary=self.sanitizer(history_summary),
                metadata=dict(metadata or {}),
            ))
        return result


def build_pending_context(result: IntentRecognitionResult) -> dict[str, Any]:
    """Serialize clarification state for the next recognition turn."""
    clarification = getattr(result, "clarification", None)
    if clarification is None:
        return {}
    frame = result.frame
    return {
        "status": result.status,
        "clarification_kind": result.clarification_kind,
        "normalized_user_goal": frame.normalized_user_goal,
        "underlying_goal": frame.underlying_goal,
        "information_needs": list(frame.information_needs),
        "candidate_intent_ids": list(clarification.candidate_intent_ids),
        "expected_information": list(clarification.expected_information),
        "confirmed_slots": dict(frame.confirmed_slots),
        "missing_slots": list(frame.missing_slots),
    }
