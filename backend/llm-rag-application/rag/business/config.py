from dataclasses import dataclass


@dataclass(frozen=True)
class BusinessConfig:
    """Capabilities and answer policy for one trusted business identity."""

    business_type: str
    display_name: str
    knowledge_bases: tuple[str, ...]
    tools: tuple[str, ...]
    answer_policy: str
    show_sources: bool
