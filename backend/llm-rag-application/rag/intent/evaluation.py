from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rag.intent.models import IntentRecognitionResult
from rag.intent.service import build_pending_context


_VALID_STATUSES = frozenset({"confident", "needs_clarification", "oos"})
_VALID_CLARIFICATION_KINDS = frozenset({"intent_disambiguation", "missing_input"})

# Gold labels in the case set may be Chinese; the recognizer emits English slot ids.
_INFO_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "retrieval_query": frozenset({"retrieval_query", "topic"}),
    "topic": frozenset({"retrieval_query", "topic"}),
    "product_name": frozenset({"product_name"}),
    "drugs": frozenset({"drugs", "interacting_drugs"}),
    "interacting_drugs": frozenset({"drugs", "interacting_drugs"}),
    "出现时间": frozenset({"出现时间", "occurrence_time"}),
    "occurrence_time": frozenset({"出现时间", "occurrence_time"}),
    "客户群体": frozenset({"客户群体", "customer_group", "customer_identifier"}),
    "customer_group": frozenset({"客户群体", "customer_group", "customer_identifier"}),
    "治疗项目": frozenset({"治疗项目", "treatment_type"}),
    "treatment_type": frozenset({"治疗项目", "treatment_type"}),
    "分析对象": frozenset({"分析对象", "analysis_dimension"}),
    "analysis_dimension": frozenset({"分析对象", "analysis_dimension"}),
    "时间范围": frozenset({"时间范围", "time_range"}),
    "time_range": frozenset({"时间范围", "time_range"}),
}


@dataclass(frozen=True)
class IntentEvaluationCase:
    case_id: str
    query: str
    expected_status: str
    expected_intent_ids: tuple[str, ...] = ()
    acceptable_intent_ids: tuple[str, ...] = ()
    forbidden_intent_ids: tuple[str, ...] = ()
    history: tuple[tuple[str, str], ...] = ()
    business_type: str = ""
    pending_context: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    source_documents: tuple[str, ...] = ()
    expected_goal_keywords: tuple[str, ...] = ()
    expected_query_keywords: tuple[str, ...] = ()
    min_information_needs: int = 0
    expected_information: tuple[str, ...] = ()
    follow_up_query: str = ""
    expected_follow_up_intent_ids: tuple[str, ...] = ()
    expected_clarification_kind: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IntentEvaluationCase":
        if not isinstance(value, Mapping):
            raise ValueError("case must be a JSON object")
        case_id = _required_str(value, "case_id")
        query = _required_str(value, "query")
        expected_status = _required_str(value, "expected_status")
        if expected_status not in _VALID_STATUSES:
            raise ValueError(f"invalid expected_status: {expected_status}")
        history = _history(value.get("history", ()))
        pending = value.get("pending_context") or {}
        if not isinstance(pending, Mapping):
            raise ValueError("pending_context must be an object")
        min_needs = value.get("min_information_needs", 0)
        if min_needs is None:
            min_needs = 0
        if not isinstance(min_needs, int) or isinstance(min_needs, bool) or min_needs < 0:
            raise ValueError("min_information_needs must be a non-negative integer")
        follow_up_query = value.get("follow_up_query") or ""
        if not isinstance(follow_up_query, str):
            raise ValueError("follow_up_query must be a string")
        expected_kind = str(value.get("expected_clarification_kind") or "").strip()
        if expected_status == "needs_clarification":
            if expected_kind not in _VALID_CLARIFICATION_KINDS:
                raise ValueError("needs_clarification requires expected_clarification_kind")
        elif expected_kind:
            raise ValueError("expected_clarification_kind is only valid for needs_clarification")
        return cls(
            case_id=case_id,
            query=query,
            expected_status=expected_status,
            expected_intent_ids=_string_tuple(value.get("expected_intent_ids"), "expected_intent_ids"),
            acceptable_intent_ids=_string_tuple(value.get("acceptable_intent_ids"), "acceptable_intent_ids"),
            forbidden_intent_ids=_string_tuple(value.get("forbidden_intent_ids"), "forbidden_intent_ids"),
            history=history,
            business_type=str(value.get("business_type") or ""),
            pending_context=dict(pending),
            tags=_string_tuple(value.get("tags"), "tags"),
            source_documents=_string_tuple(value.get("source_documents"), "source_documents"),
            expected_goal_keywords=_string_tuple(value.get("expected_goal_keywords"), "expected_goal_keywords"),
            expected_query_keywords=_string_tuple(value.get("expected_query_keywords"), "expected_query_keywords"),
            min_information_needs=min_needs,
            expected_information=_string_tuple(value.get("expected_information"), "expected_information"),
            follow_up_query=follow_up_query.strip(),
            expected_follow_up_intent_ids=_string_tuple(
                value.get("expected_follow_up_intent_ids"),
                "expected_follow_up_intent_ids",
            ),
            expected_clarification_kind=expected_kind,
        )


@dataclass(frozen=True)
class IntentCaseResult:
    case_id: str
    expected_status: str
    predicted_status: str
    expected_intent_ids: tuple[str, ...]
    predicted_intent_ids: tuple[str, ...]
    status_correct: bool
    intents_correct: bool
    q2q_recalled_expected: bool | None
    candidate_contains_expected: bool | None
    forbidden_intent_selected: bool
    extraneous_companion_intent: bool
    expected_clarification_kind: str
    predicted_clarification_kind: str
    clarification_kind_correct: bool | None
    latency_ms: float
    candidate_intent_ids: tuple[str, ...]
    q2q_match_intent_ids: tuple[str, ...]
    q2q_match_scores: tuple[float, ...]
    missing_slots: tuple[str, ...]
    retrieval_queries: tuple[str, ...]
    information_needs: tuple[str, ...]
    goal_keywords_retained: bool | None
    query_keywords_retained: bool | None
    information_needs_ok: bool | None
    clarification_information_ok: bool | None
    follow_up_resolved: bool | None
    follow_up_status: str
    follow_up_intent_ids: tuple[str, ...]
    tags: tuple[str, ...]
    result: IntentRecognitionResult


@dataclass(frozen=True)
class IntentEvaluationReport:
    case_count: int
    status_accuracy: float
    status_macro_f1: float
    intent_exact_match: float
    oos_precision: float
    oos_recall: float
    oos_f1: float
    premature_route_rate: float
    routing_failure_rate: float
    forbidden_intent_selected_rate: float
    q2q_candidate_recall: float
    goal_keyword_retention: float
    query_keyword_retention: float
    information_need_structure: float
    clarification_information_coverage: float
    follow_up_resolution: float
    clarification_kind_accuracy: float
    extraneous_companion_intent_rate: float
    average_latency_ms: float
    status_confusion: Mapping[str, Mapping[str, int]]
    tag_slices: Mapping[str, Mapping[str, float]]
    cases: tuple[IntentCaseResult, ...]

    def summary(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("cases", None)
        return value


def load_evaluation_cases(path: str | Path) -> tuple[IntentEvaluationCase, ...]:
    source = Path(path)
    records: list[IntentEvaluationCase] = []
    for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{line_no}: invalid JSON") from exc
        try:
            records.append(IntentEvaluationCase.from_mapping(payload))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{source}:{line_no}: {exc}") from exc
    return tuple(records)


def evaluate_intent_recognizer(
    recognizer,
    cases: Sequence[IntentEvaluationCase],
) -> IntentEvaluationReport:
    outputs: list[IntentCaseResult] = []
    for case in cases:
        started = time.perf_counter()
        result = recognizer.recognize(
            case.query,
            history=case.history,
            business_type=case.business_type,
            pending_context=case.pending_context,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        outputs.append(_score_case(recognizer, case, result, latency_ms))

    statuses = ("confident", "needs_clarification", "oos")
    confusion = {
        expected: {predicted: 0 for predicted in statuses}
        for expected in statuses
    }
    for item in outputs:
        if item.expected_status in confusion and item.predicted_status in confusion[item.expected_status]:
            confusion[item.expected_status][item.predicted_status] += 1

    return IntentEvaluationReport(
        case_count=len(outputs),
        **_aggregate_metrics(outputs, confusion, statuses),
        status_confusion=confusion,
        tag_slices=_tag_slices(outputs, confusion, statuses),
        cases=tuple(outputs),
    )


def _score_case(
    recognizer,
    case: IntentEvaluationCase,
    result: IntentRecognitionResult,
    latency_ms: float,
) -> IntentCaseResult:
    expected = set(case.expected_intent_ids)
    acceptable = expected | set(case.acceptable_intent_ids)
    predicted = set(result.intent_ids)
    effective_predicted = _effective_predicted_intents(case, predicted)
    if case.expected_status == "confident":
        intents_correct = effective_predicted == expected
    elif acceptable:
        intents_correct = bool(effective_predicted) and effective_predicted.issubset(acceptable)
    else:
        intents_correct = not effective_predicted
    extraneous_companion_intent = (
        "casual_conversation" in predicted
        and "casual_conversation" not in effective_predicted
    )
    kind_correct = None
    if case.expected_clarification_kind:
        kind_correct = result.clarification_kind == case.expected_clarification_kind

    q2q_ids = _q2q_intent_ids(result)
    candidate_ids = tuple(result.candidate_intent_ids)
    q2q_recalled = None if not expected else expected.issubset(q2q_ids)
    candidate_contains = None if not expected else expected.issubset(set(candidate_ids))

    follow_up_status = ""
    follow_up_intent_ids: tuple[str, ...] = ()
    follow_up_resolved = None
    if case.follow_up_query:
        follow_up_resolved = False
        if result.status == "needs_clarification" and result.clarification is not None:
            follow_up = recognizer.recognize(
                case.follow_up_query,
                history=tuple(case.history) + (
                    ("user", case.query),
                    ("assistant", result.clarification.question),
                ),
                business_type=case.business_type,
                pending_context=build_pending_context(result),
            )
            follow_up_status = follow_up.status
            follow_up_intent_ids = follow_up.intent_ids
            follow_up_resolved = (
                follow_up.status == "confident"
                and set(follow_up.intent_ids) == set(case.expected_follow_up_intent_ids)
            )

    return IntentCaseResult(
        case_id=case.case_id,
        expected_status=case.expected_status,
        predicted_status=result.status,
        expected_intent_ids=case.expected_intent_ids,
        predicted_intent_ids=result.intent_ids,
        status_correct=result.status == case.expected_status,
        intents_correct=intents_correct,
        q2q_recalled_expected=q2q_recalled,
        candidate_contains_expected=candidate_contains,
        forbidden_intent_selected=bool(effective_predicted & set(case.forbidden_intent_ids)),
        extraneous_companion_intent=extraneous_companion_intent,
        expected_clarification_kind=case.expected_clarification_kind,
        predicted_clarification_kind=result.clarification_kind or "",
        clarification_kind_correct=kind_correct,
        latency_ms=latency_ms,
        candidate_intent_ids=candidate_ids,
        q2q_match_intent_ids=tuple(sorted(q2q_ids)),
        q2q_match_scores=tuple(match.score for match in result.q2q_matches),
        missing_slots=tuple(result.frame.missing_slots),
        retrieval_queries=tuple(result.frame.retrieval_queries),
        information_needs=tuple(result.frame.information_needs),
        goal_keywords_retained=_optional_flag(
            case.expected_goal_keywords,
            _contains_all(
                f"{result.frame.normalized_user_goal} {result.frame.underlying_goal}",
                case.expected_goal_keywords,
            ),
        ),
        query_keywords_retained=_optional_flag(
            case.expected_query_keywords,
            _contains_all(
                " ".join((result.frame.standalone_query, *result.frame.retrieval_queries)),
                case.expected_query_keywords,
            ),
        ),
        information_needs_ok=_information_needs_ok(case, result),
        clarification_information_ok=_clarification_ok(case, result),
        follow_up_resolved=follow_up_resolved,
        follow_up_status=follow_up_status,
        follow_up_intent_ids=follow_up_intent_ids,
        tags=case.tags,
        result=result,
    )


def _information_needs_ok(
    case: IntentEvaluationCase,
    result: IntentRecognitionResult,
) -> bool | None:
    if case.min_information_needs <= 0:
        return None
    needs = tuple(result.frame.information_needs)
    queries = tuple(result.frame.retrieval_queries)
    return (
        len(needs) >= case.min_information_needs
        and len(queries) >= case.min_information_needs
        and len(needs) == len(queries)
    )


def _effective_predicted_intents(case: IntentEvaluationCase, predicted: set[str]) -> set[str]:
    if case.expected_status == "oos":
        return predicted
    allowed = set(case.expected_intent_ids) | set(case.acceptable_intent_ids)
    allowed_primary = allowed - {"casual_conversation"}
    if predicted & allowed_primary:
        return predicted - {"casual_conversation"}
    return predicted


def _clarification_ok(
    case: IntentEvaluationCase,
    result: IntentRecognitionResult,
) -> bool | None:
    if not case.expected_information:
        return None
    if result.clarification is None:
        return False
    predicted = _predicted_information_types(result)
    return all(_information_type_covered(needed, predicted) for needed in case.expected_information)


def _predicted_information_types(result: IntentRecognitionResult) -> set[str]:
    clarification = result.clarification
    tokens = list(result.frame.missing_slots)
    if clarification is not None:
        tokens.extend(clarification.expected_information)
    return {_fold(token) for token in tokens if _fold(token)}


def _information_type_covered(needed: str, predicted: set[str]) -> bool:
    key = _fold(needed)
    if not key:
        return True
    if key in predicted:
        return True
    aliases = set()
    for source, targets in _INFO_TYPE_ALIASES.items():
        group = {_fold(source), *(_fold(item) for item in targets)}
        if key in group:
            aliases.update(group)
    return bool(predicted & aliases)


def routing_ok(item: IntentCaseResult) -> bool:
    return item.status_correct and item.intents_correct and not item.forbidden_intent_selected


def product_ok(item: IntentCaseResult) -> bool:
    return item.follow_up_resolved is not False and item.clarification_information_ok is not False


def diagnostic_ok(item: IntentCaseResult) -> bool:
    return (
        item.q2q_recalled_expected is not False
        and item.goal_keywords_retained is not False
        and item.query_keywords_retained is not False
        and item.information_needs_ok is not False
        and item.clarification_kind_correct is not False
        and not item.extraneous_companion_intent
    )


def routing_issue_reasons(item: IntentCaseResult) -> list[str]:
    reasons: list[str] = []
    if item.status_correct is False:
        reasons.append("status")
    if item.intents_correct is False:
        reasons.append("intent_ids")
    if item.forbidden_intent_selected:
        reasons.append("forbidden_intent_selected")
    return reasons


def product_issue_reasons(item: IntentCaseResult) -> list[str]:
    reasons: list[str] = []
    if item.clarification_information_ok is False:
        reasons.append("clarification_information")
    if item.follow_up_resolved is False:
        reasons.append("follow_up_resolution")
    return reasons


def diagnostic_issue_reasons(item: IntentCaseResult) -> list[str]:
    reasons: list[str] = []
    if item.q2q_recalled_expected is False:
        reasons.append("q2q_recall")
    if item.goal_keywords_retained is False:
        reasons.append("goal_keywords")
    if item.query_keywords_retained is False:
        reasons.append("query_keywords")
    if item.information_needs_ok is False:
        reasons.append("information_need_structure")
    if item.clarification_kind_correct is False:
        reasons.append("clarification_kind")
    if item.extraneous_companion_intent:
        reasons.append("extraneous_companion_intent")
    return reasons


def _aggregate_metrics(
    outputs: Sequence[IntentCaseResult],
    confusion: Mapping[str, Mapping[str, int]],
    statuses: Iterable[str],
) -> dict[str, float]:
    count = len(outputs)
    uncertain = [item for item in outputs if item.expected_status in {"needs_clarification", "oos"}]
    premature = sum(item.predicted_status == "confident" for item in uncertain)
    oos_tp = sum(item.expected_status == "oos" and item.predicted_status == "oos" for item in outputs)
    oos_fp = sum(item.expected_status != "oos" and item.predicted_status == "oos" for item in outputs)
    oos_fn = sum(item.expected_status == "oos" and item.predicted_status != "oos" for item in outputs)
    oos_precision = _ratio(oos_tp, oos_tp + oos_fp)
    oos_recall = _ratio(oos_tp, oos_tp + oos_fn)
    return {
        "status_accuracy": _ratio(sum(item.status_correct for item in outputs), count),
        "status_macro_f1": _macro_f1(confusion, statuses),
        "intent_exact_match": _ratio(sum(item.intents_correct for item in outputs), count),
        "oos_precision": oos_precision,
        "oos_recall": oos_recall,
        "oos_f1": _f1(oos_precision, oos_recall),
        "premature_route_rate": _ratio(premature, len(uncertain)),
        "routing_failure_rate": _ratio(sum(not routing_ok(item) for item in outputs), count),
        "forbidden_intent_selected_rate": _ratio(
            sum(item.forbidden_intent_selected for item in outputs),
            count,
        ),
        "q2q_candidate_recall": _optional_ratio(outputs, "q2q_recalled_expected"),
        "goal_keyword_retention": _optional_ratio(outputs, "goal_keywords_retained"),
        "query_keyword_retention": _optional_ratio(outputs, "query_keywords_retained"),
        "information_need_structure": _optional_ratio(outputs, "information_needs_ok"),
        "clarification_information_coverage": _optional_ratio(outputs, "clarification_information_ok"),
        "follow_up_resolution": _optional_ratio(outputs, "follow_up_resolved"),
        "clarification_kind_accuracy": _optional_ratio(outputs, "clarification_kind_correct"),
        "extraneous_companion_intent_rate": _ratio(
            sum(item.extraneous_companion_intent for item in outputs),
            count,
        ),
        "average_latency_ms": _ratio(sum(item.latency_ms for item in outputs), count),
    }


def _tag_slices(
    outputs: Sequence[IntentCaseResult],
    confusion: Mapping[str, Mapping[str, int]],
    statuses: Iterable[str],
) -> dict[str, dict[str, float]]:
    tags = sorted({tag for item in outputs for tag in item.tags})
    slices: dict[str, dict[str, float]] = {}
    for tag in tags:
        tagged = [item for item in outputs if tag in item.tags]
        tagged_confusion = {
            expected: {predicted: 0 for predicted in statuses}
            for expected in statuses
        }
        for item in tagged:
            if item.expected_status in tagged_confusion and item.predicted_status in tagged_confusion[item.expected_status]:
                tagged_confusion[item.expected_status][item.predicted_status] += 1
        slices[tag] = {
            "case_count": float(len(tagged)),
            **_aggregate_metrics(tagged, tagged_confusion, statuses),
        }
    return slices


def _q2q_intent_ids(result: IntentRecognitionResult) -> set[str]:
    ids: set[str] = set()
    for match in result.q2q_matches:
        ids.update(match.intent_ids)
    return ids


def _optional_flag(annotations: Sequence[str], value: bool) -> bool | None:
    return value if annotations else None


def _optional_ratio(items: Sequence[IntentCaseResult], attr: str) -> float:
    applicable = [item for item in items if getattr(item, attr) is not None]
    return _ratio(sum(bool(getattr(item, attr)) for item in applicable), len(applicable))


def _contains_all(haystack: str, keywords: Sequence[str]) -> bool:
    folded = _fold(haystack)
    return all(_fold(keyword) in folded for keyword in keywords if _fold(keyword))


def _fold(value: str) -> str:
    return "".join(str(value).split()).casefold()


def _required_str(value: Mapping[str, Any], field_name: str) -> str:
    if field_name not in value:
        raise ValueError(f"missing {field_name}")
    raw = value[field_name]
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return raw.strip()


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a list of strings")
    items = tuple(str(item).strip() for item in value if str(item).strip())
    if any(not isinstance(item, (str, int, float)) for item in value if item is not None and item != ""):
        raise ValueError(f"{field_name} must be a list of strings")
    return items


def _history(value: Any) -> tuple[tuple[str, str], ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("history must be a list of [role, content] pairs")
    records: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("history must be a list of [role, content] pairs")
        records.append((str(item[0]), str(item[1])))
    return tuple(records)


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _macro_f1(confusion: Mapping[str, Mapping[str, int]], statuses: Iterable[str]) -> float:
    values = []
    for status in statuses:
        tp = confusion[status][status]
        fp = sum(confusion[other][status] for other in statuses if other != status)
        fn = sum(confusion[status][other] for other in statuses if other != status)
        values.append(_f1(_ratio(tp, tp + fp), _ratio(tp, tp + fn)))
    return _ratio(sum(values), len(values))
