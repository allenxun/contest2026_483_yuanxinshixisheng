from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence, Tuple


IntentStatus = Literal["confident", "needs_clarification", "oos"]
ClarificationKind = Literal["intent_disambiguation", "missing_input"]
TargetType = Literal["knowledge", "tool", "chat"]


@dataclass(frozen=True)
class IntentActionDefinition:
    """One deterministic action attached to a registered business intent."""

    action_id: str
    action_type: TargetType
    target_name: str = ""
    depends_on: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IntentDefinition:
    """A registered business capability presented to the intent LLM."""

    intent_id: str
    name: str
    description: str
    target_type: TargetType = "knowledge"
    target_name: str = ""
    include_when: Tuple[str, ...] = ()
    exclude_when: Tuple[str, ...] = ()
    positive_examples: Tuple[str, ...] = ()
    hard_negative_examples: Tuple[str, ...] = ()
    required_slots: Tuple[str, ...] = ()
    allowed_roles: Tuple[str, ...] = ()
    risk_level: Literal["low", "medium", "high"] = "low"
    actions: Tuple[IntentActionDefinition, ...] = ()

    def is_allowed(self, business_type: str) -> bool:
        return not self.allowed_roles or business_type in self.allowed_roles

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IntentDefinition":
        def strings(key: str) -> Tuple[str, ...]:
            raw = value.get(key) or ()
            return tuple(str(item) for item in raw if str(item).strip())

        target = value.get("target") or {}
        if not isinstance(target, Mapping):
            target = {}
        raw_actions = value.get("actions") or ()
        actions: list[IntentActionDefinition] = []
        if isinstance(raw_actions, Sequence) and not isinstance(raw_actions, (str, bytes)):
            for index, action in enumerate(raw_actions, start=1):
                if not isinstance(action, Mapping):
                    continue
                action_type = str(action.get("type") or "").strip()
                actions.append(IntentActionDefinition(
                    action_id=str(action.get("id") or f"action_{index}").strip(),
                    action_type=action_type,
                    target_name=str(action.get("target") or action.get("name") or "").strip(),
                    depends_on=tuple(str(item) for item in action.get("depends_on", ()) if item),
                ))
        return cls(
            intent_id=str(value["intent_id"]).strip(),
            name=str(value.get("name") or value["intent_id"]).strip(),
            description=str(value.get("description") or "").strip(),
            target_type=str(target.get("type") or value.get("target_type") or "knowledge"),
            target_name=str(target.get("name") or value.get("target_name") or "").strip(),
            include_when=strings("include_when"),
            exclude_when=strings("exclude_when"),
            positive_examples=strings("positive_examples"),
            hard_negative_examples=strings("hard_negative_examples"),
            required_slots=strings("required_slots"),
            allowed_roles=strings("allowed_roles"),
            risk_level=str(value.get("risk_level") or "low"),
            actions=tuple(actions),
        )


@dataclass(frozen=True)
class IntentExample:
    """A human-verified Q2Q example."""

    query: str
    intent_ids: Tuple[str, ...]
    business_type: str = ""
    example_id: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IntentExample":
        raw_ids = value.get("intent_ids") or [value.get("intent_id")]
        return cls(
            query=str(value["query"]).strip(),
            intent_ids=tuple(str(item).strip() for item in raw_ids if item),
            business_type=str(value.get("business_type") or "").strip(),
            example_id=str(value.get("example_id") or "").strip(),
        )


@dataclass(frozen=True)
class Q2QMatch:
    query: str
    intent_ids: Tuple[str, ...]
    score: float
    example_id: str = ""


@dataclass(frozen=True)
class IntentHypothesis:
    intent_id: str
    supporting_evidence: str = ""
    missing_evidence: str = ""


@dataclass(frozen=True)
class ClarificationResult:
    question: str
    expected_information: Tuple[str, ...] = ()
    candidate_intent_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IntentFrame:
    normalized_user_goal: str
    hypotheses: Tuple[IntentHypothesis, ...] = ()
    confirmed_slots: Mapping[str, Any] = field(default_factory=dict)
    missing_slots: Tuple[str, ...] = ()
    standalone_query: str = ""
    underlying_goal: str = ""
    information_needs: Tuple[str, ...] = ()
    retrieval_queries: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IntentRecognitionResult:
    status: IntentStatus
    frame: IntentFrame
    clarification: ClarificationResult | None = None
    clarification_kind: ClarificationKind | None = None
    oos_summary: str = ""
    candidate_intent_ids: Tuple[str, ...] = ()
    q2q_matches: Tuple[Q2QMatch, ...] = ()
    reason_summary: str = ""
    raw_response: str = ""

    @property
    def intent_ids(self) -> Tuple[str, ...]:
        return tuple(item.intent_id for item in self.frame.hypotheses)

    @property
    def can_route(self) -> bool:
        return self.status == "confident" and bool(self.frame.hypotheses)


def validate_catalog(definitions: Sequence[IntentDefinition]) -> None:
    ids = [item.intent_id for item in definitions]
    if any(not intent_id for intent_id in ids):
        raise ValueError("intent_id must not be empty")
    if len(ids) != len(set(ids)):
        raise ValueError("intent_id must be unique")
    for item in definitions:
        if item.target_type not in {"knowledge", "tool", "chat"}:
            raise ValueError(f"invalid target_type for {item.intent_id}")
        if item.risk_level not in {"low", "medium", "high"}:
            raise ValueError(f"invalid risk_level for {item.intent_id}")
        action_ids = [action.action_id for action in item.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError(f"duplicate action_id for {item.intent_id}")
        for action in item.actions:
            if action.action_type not in {"knowledge", "tool", "chat"}:
                raise ValueError(f"invalid action_type for {item.intent_id}:{action.action_id}")
            unknown = set(action.depends_on).difference(action_ids)
            if unknown:
                raise ValueError(
                    f"unknown action dependency for {item.intent_id}:{action.action_id}: {sorted(unknown)}"
                )
