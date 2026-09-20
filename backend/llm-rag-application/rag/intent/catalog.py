from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from rag.intent.models import IntentDefinition, IntentExample, validate_catalog

# 从YAML/JSON文件中加载意图定义和示例的工具函数
def _load_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif source.suffix.lower() in {".yaml", ".yml"}:
        records = yaml.safe_load(text) or []
    else:
        records = json.loads(text)
    if isinstance(records, dict):
        records = records.get("intents") or records.get("examples") or []
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError(f"{source} must contain a list of objects")
    return records

# 加载 Q2Q 标注示例
def load_intent_definitions(path: str | Path) -> tuple[IntentDefinition, ...]:
    definitions = tuple(IntentDefinition.from_mapping(item) for item in _load_records(path))
    validate_catalog(definitions)
    return definitions


def load_intent_examples(path: str | Path) -> tuple[IntentExample, ...]:
    return tuple(IntentExample.from_mapping(item) for item in _load_records(path))
