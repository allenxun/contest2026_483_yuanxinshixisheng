from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from rag.weijing.models import (
    ConcernCode,
    RegionCode,
    RegionReading,
    SafetyProfile,
    ScoreReading,
    WeijingReport,
)
from rag.weijing.report_parser import ReportParseError

_EXCLUDED_NAMES = ("鼻部", "鼻子", "眼周")
_SAFETY_FIELDS = set(SafetyProfile.model_fields)


def report_from_payload(payload: dict) -> tuple[WeijingReport, SafetyProfile]:
    if not isinstance(payload, dict):
        raise ReportParseError("检测报告 JSON 必须是对象")
    regions_raw = _regions_blob(payload)
    if not isinstance(regions_raw, dict) or not regions_raw:
        raise ReportParseError("检测报告 JSON 缺少四区评分 regions")

    notes: list[str] = []
    excluded = [
        name for name in _EXCLUDED_NAMES
        if name in regions_raw or name in json.dumps(payload, ensure_ascii=False)
    ]
    regions: dict[RegionCode, RegionReading] = {}
    for key, value in regions_raw.items():
        if key in _EXCLUDED_NAMES:
            continue
        try:
            region = RegionCode(str(key))
        except ValueError:
            notes.append(f"忽略未识别分区 {key}")
            continue
        if not isinstance(value, dict):
            notes.append(f"{region.value} 分区数据无效")
            continue
        source = value.get("scores") if isinstance(value.get("scores"), dict) else value
        scores = {
            concern: _score_from_value(source.get(concern.value) if isinstance(source, dict) else None)
            for concern in ConcernCode
        }
        regions[region] = RegionReading(scores=scores)

    for region in RegionCode:
        if region not in regions:
            notes.append(f"缺少{region.value}区数据")

    if not regions or not any(
        reading.score is not None
        for region in regions.values()
        for reading in region.scores.values()
    ):
        raise ReportParseError("检测报告 JSON 中未找到有效的四区油脂、色斑或干燥性细纹评分")

    report_id = str(payload.get("report_id") or _nested(payload, "report", "report_id") or "").strip()
    algorithm_version = str(
        payload.get("algorithm_version") or _nested(payload, "report", "algorithm_version") or ""
    ).strip()
    assessed_at = _parse_datetime(
        payload.get("assessed_at") or _nested(payload, "report", "assessed_at")
    )
    canonical = json.dumps(
        {"report_id": report_id, "regions": regions_raw},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    report = WeijingReport(
        report_id=report_id or f"report-{digest[:24]}",
        assessed_at=assessed_at,
        algorithm_version=algorithm_version or "未提供",
        filename="structured-input.json",
        file_sha256=digest,
        regions=regions,
        excluded_regions=list(dict.fromkeys(excluded)),
        parsing_notes=notes,
    )
    return report, _safety_from_payload(payload.get("safety"))


def caller_user_id(payload: dict) -> str:
    from rag.weijing.followup import resolve_owner_id

    return resolve_owner_id(payload)


def caller_session_id(payload: dict) -> str | None:
    value = str(payload.get("session_id") or "").strip()
    return value or None


def caller_organization_id(payload: dict) -> str | None:
    value = str(payload.get("organization_id") or "").strip()
    return value or None


def _regions_blob(payload: dict) -> dict | None:
    if isinstance(payload.get("regions"), dict):
        return payload["regions"]
    report = payload.get("report")
    if isinstance(report, dict) and isinstance(report.get("regions"), dict):
        return report["regions"]
    return None


def _nested(payload: dict, *keys):
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safety_from_payload(value) -> SafetyProfile:
    if not isinstance(value, dict):
        return SafetyProfile()
    known = {key: item for key, item in value.items() if key in _SAFETY_FIELDS}
    try:
        return SafetyProfile.model_validate(known)
    except Exception:
        return SafetyProfile()


def _score_from_value(value) -> ScoreReading:
    if value is None:
        return ScoreReading(issue="missing")
    label = None
    raw = value
    if isinstance(value, dict):
        raw = value.get("score")
        label = value.get("label") or value.get("reported_label")
    if isinstance(raw, bool) or raw is None:
        return ScoreReading(reported_label=_as_label(label), issue="invalid" if raw is not None else "missing")
    if isinstance(raw, str) and not raw.strip().lstrip("-").isdigit():
        return ScoreReading(reported_label=_as_label(label), issue="invalid")
    if isinstance(raw, float) and not raw.is_integer():
        return ScoreReading(reported_label=_as_label(label), issue="invalid")
    try:
        score = int(raw)
    except (TypeError, ValueError):
        return ScoreReading(reported_label=_as_label(label), issue="invalid")
    if not 0 <= score <= 100:
        return ScoreReading(reported_label=_as_label(label), issue="invalid")
    expected = _level_label(score)
    reported = _as_label(label)
    if reported and reported != expected:
        return ScoreReading(score=score, reported_label=reported, issue="conflict")
    return ScoreReading(score=score, reported_label=reported)


def _as_label(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _level_label(score: int) -> str:
    if score >= 81:
        return "未见明显"
    if score >= 61:
        return "轻度"
    if score >= 41:
        return "中度"
    if score >= 21:
        return "较明显"
    return "显著"


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
