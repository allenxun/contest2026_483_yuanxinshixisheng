from __future__ import annotations

from pathlib import Path

import yaml

from rag.business.config import BusinessConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "conf" / "business_types.yaml"


class BusinessRegistry:
    """Load business capability declarations from a small, reviewable YAML file."""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        self._configs = self._load()

    def _load(self) -> dict[str, BusinessConfig]:
        with self.config_path.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream) or {}
        configs = {}
        for name, item in (raw.get("business_types") or {}).items():
            item = item or {}
            configs[name] = BusinessConfig(
                business_type=name,
                display_name=str(item.get("display_name") or name),
                knowledge_bases=tuple(str(value) for value in item.get("knowledge_bases", [])),
                tools=tuple(str(value) for value in item.get("tools", [])),
                answer_policy=str(item.get("answer_policy") or "").strip(),
                show_sources=bool(item.get("show_sources", False)),
            )
        if "customer" not in configs:
            raise ValueError("business_types.yaml must define the customer identity")
        return configs

    def get(self, business_type: str) -> BusinessConfig:
        try:
            return self._configs[business_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported business type: {business_type}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._configs)

    @staticmethod
    def filter_knowledge_bases(
        config: BusinessConfig,
        requested_names: list[str] | tuple[str, ...],
    ) -> tuple[str, ...]:
        requested = tuple(dict.fromkeys(name for name in requested_names if name))
        if "*" in config.knowledge_bases:
            return requested
        allowed = set(config.knowledge_bases)
        return tuple(name for name in requested if name in allowed)


business_registry = BusinessRegistry()
