from functools import lru_cache
from pathlib import Path

import yaml


CATALOG_PATH = Path(__file__).resolve().parents[2] / "conf" / "weijing" / "catalog.yaml"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError("微晶规则目录未就绪")
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("ingredients"):
        raise ValueError("微晶规则目录无效")
    return data


def knowledge_version() -> str:
    return str(load_catalog().get("knowledge_version") or "1.0")


def ingredient_record(ingredient_id: str) -> dict:
    record = load_catalog()["ingredients"].get(ingredient_id)
    if not record:
        raise KeyError(ingredient_id)
    return record
