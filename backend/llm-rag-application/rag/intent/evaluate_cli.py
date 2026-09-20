from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from rag.intent.evaluation import (
    IntentCaseResult,
    IntentEvaluationReport,
    diagnostic_issue_reasons,
    diagnostic_ok,
    product_issue_reasons,
    product_ok,
    routing_issue_reasons,
    routing_ok,
)

_HEADLINE = (
    ("status_accuracy", "状态是否判对"),
    ("intent_exact_match", "意图是否选对"),
    ("oos_f1", "OOS F1"),
    ("premature_route_rate", "过早路由率"),
)
_PRODUCT = (
    ("follow_up_resolution", "补一句后能否恢复"),
    ("clarification_information_coverage", "澄清是否问到标注槽"),
)
_DIAGNOSTIC = (
    ("q2q_candidate_recall", "Q2Q 是否召回期望意图"),
    ("goal_keyword_retention", "目标句是否留实体"),
    ("query_keyword_retention", "检索问题是否留实体"),
    ("information_need_structure", "信息需求结构是否对齐"),
    ("clarification_kind_accuracy", "追问原因是否判对"),
    ("extraneous_companion_intent_rate", "伴随闲聊标签占比"),
)

# 场景标签映射（用于报告分组统计）
_SCENARIO_LABELS = {
    "implicit_intent": "隐含意图/模糊查询",
    "tool_call": "工具调用意图识别",
    "oos_test": "越界操作拒答",
    "complex_query": "复杂多步查询",
    "explicit_query": "显式直接查询",
    "multi_turn": "多轮连续追问",
    "irrelevant_retrieval": "是否检索无关内容",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag.intent.evaluate_cli",
        description="Evaluate intent recognition against a frozen JSONL case set.",
    )
    parser.add_argument("--catalog", required=True, help="Path to intent catalog YAML")
    parser.add_argument("--examples", required=True, help="Path to Q2Q examples YAML")
    parser.add_argument("--cases", required=True, help="Path to evaluation JSONL")
    parser.add_argument("--output", help="Optional JSON report path")
    return parser


def _issue_payload(item: IntentCaseResult, reasons: Sequence[str], layer: str) -> dict[str, Any]:
    clarification = item.result.clarification
    return {
        "case_id": item.case_id,
        "layer": layer,
        "tags": list(item.tags),
        "reasons": list(reasons),
        "expected_status": item.expected_status,
        "predicted_status": item.predicted_status,
        "expected_clarification_kind": item.expected_clarification_kind,
        "predicted_clarification_kind": item.predicted_clarification_kind,
        "expected_intent_ids": list(item.expected_intent_ids),
        "predicted_intent_ids": list(item.predicted_intent_ids),
        "extraneous_companion_intent": item.extraneous_companion_intent,
        "q2q_match_intent_ids": list(item.q2q_match_intent_ids),
        "q2q_match_scores": list(item.q2q_match_scores),
        "candidate_intent_ids": list(item.candidate_intent_ids),
        "missing_slots": list(item.missing_slots),
        "predicted_expected_information": list(clarification.expected_information) if clarification else [],
        "information_needs": list(item.information_needs),
        "retrieval_queries": list(item.retrieval_queries),
        "follow_up_status": item.follow_up_status,
        "follow_up_intent_ids": list(item.follow_up_intent_ids),
    }


def build_headline(summary: dict[str, Any], routing_failure_count: int) -> dict[str, Any]:
    return {
        "case_count": summary["case_count"],
        "routing_failure_count": routing_failure_count,
        "metrics": [
            {"key": key, "label": label, "value": summary[key]}
            for key, label in _HEADLINE
        ],
        "product_metrics": [
            {"key": key, "label": label, "value": summary[key]}
            for key, label in _PRODUCT
        ],
        "diagnostic_metrics": [
            {"key": key, "label": label, "value": summary[key]}
            for key, label in _DIAGNOSTIC
        ],
        "note": "工具调用类意图仅评测意图识别能力，不要求实际工具执行。路由失败只计状态、意图和禁选意图。",
    }


def format_console_report(
    headline: Mapping[str, Any],
    routing_failures: Sequence[Mapping[str, Any]],
    output_path: str = "",
    tag_slices: Mapping[str, Mapping[str, Any]] | None = None,
    product_issues: Sequence[Mapping[str, Any]] = (),
    diagnostics: Sequence[Mapping[str, Any]] = (),
) -> str:
    lines = [
        (
            f"评测 {int(headline['case_count'])} 条，"
            f"路由失败 {int(headline['routing_failure_count'])} 条"
        ),
        "",
        "主指标：",
    ]
    for item in headline["metrics"]:
        lines.append(f"  {item['label']}  {_pct(item['value'])}")
    if headline.get("product_metrics"):
        lines.append("")
        lines.append("产品指标：")
        for item in headline["product_metrics"]:
            lines.append(f"  {item['label']}  {_pct(item['value'])}")
    if headline.get("diagnostic_metrics"):
        lines.append("")
        lines.append("诊断指标（不计入路由失败）：")
        for item in headline["diagnostic_metrics"]:
            lines.append(f"  {item['label']}  {_pct(item['value'])}")

    if tag_slices:
        lines.append("")
        lines.append("场景分组统计：")
        for tag, metrics in sorted(tag_slices.items()):
            if tag.startswith("scenario:"):
                scenario_name = tag.split(":", 1)[1]
                label = _SCENARIO_LABELS.get(scenario_name, scenario_name)
                case_count = int(metrics.get("case_count", 0))
                status_acc = metrics.get("status_accuracy", 0)
                intent_acc = metrics.get("intent_exact_match", 0)
                lines.append(
                    f"  {label}: {case_count}条 | 状态准确率 {_pct(status_acc)} | 意图准确率 {_pct(intent_acc)}"
                )

    if routing_failures:
        lines.append("")
        lines.append("路由失败样本（完整字段见 JSON）")
        for item in routing_failures:
            reasons = "、".join(item.get("reasons") or [])
            lines.append(
                f"- {item['case_id']}  {item.get('expected_status')}→{item.get('predicted_status')}  {reasons}"
            )
    lines.append("")
    lines.append(
        f"产品问题 {len(product_issues)} 条，诊断问题 {len(diagnostics)} 条（不计入路由失败，详见 JSON）"
    )
    if headline.get("note"):
        lines.append(f"说明：{headline['note']}")
    if output_path:
        lines.append(f"详细报告：{output_path}")
    else:
        lines.append("未指定 --output，详细 JSON 未保存")
    return "\n".join(lines)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _report_payload(
    report: IntentEvaluationReport,
    *,
    run: dict[str, Any],
) -> dict[str, Any]:
    routing_failures = [
        _issue_payload(item, routing_issue_reasons(item), "routing")
        for item in report.cases
        if not routing_ok(item)
    ]
    product_issues = [
        _issue_payload(item, product_issue_reasons(item), "product")
        for item in report.cases
        if not product_ok(item)
    ]
    diagnostics = [
        _issue_payload(item, diagnostic_issue_reasons(item), "diagnostic")
        for item in report.cases
        if not diagnostic_ok(item)
    ]
    summary = report.summary()
    return {
        "headline": build_headline(summary, len(routing_failures)),
        "run": run,
        "summary": summary,
        "tag_slices": dict(report.tag_slices),
        "routing_failures": routing_failures,
        "product_issues": product_issues,
        "diagnostics": diagnostics,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from rag.common.configuration import settings
    from rag.connector.base import embedding_model, router_llm
    from rag.intent.catalog import load_intent_definitions, load_intent_examples
    from rag.intent.evaluation import evaluate_intent_recognizer, load_evaluation_cases
    from rag.intent.q2q import Q2QIndex
    from rag.intent.recognizer import IntentRecognizer

    definitions = load_intent_definitions(args.catalog)
    examples = load_intent_examples(args.examples)
    cases = load_evaluation_cases(args.cases)
    recognizer = IntentRecognizer(
        llm=router_llm,
        definitions=definitions,
        q2q_index=Q2QIndex(embedding_model, examples),
    )
    report = evaluate_intent_recognizer(recognizer, cases)
    payload = _report_payload(
        report,
        run={
            "router_model": settings.router_llm.model_name,
            "q2q_top_k": recognizer.q2q_top_k,
            "q2q_min_score": recognizer.q2q_min_score,
            "candidate_limit": recognizer.candidate_limit,
            "catalog": str(Path(args.catalog)),
            "examples": str(Path(args.examples)),
            "cases": str(Path(args.cases)),
        },
    )
    output_path = ""
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        output_path = str(destination)
    print(
        format_console_report(
            payload["headline"],
            payload["routing_failures"],
            output_path,
            payload.get("tag_slices"),
            payload.get("product_issues") or (),
            payload.get("diagnostics") or (),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())