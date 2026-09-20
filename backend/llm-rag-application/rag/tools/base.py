from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool = True
    requires_confirmation: bool = False
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class ToolContext:
    user_id: str
    business_type: str
    organization_id: str | None


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    status: str
    data: Any = None
    error: str = ""
    task_id: str = ""


class BaseTool(ABC):
    definition: ToolDefinition

    @abstractmethod
    def invoke(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        dependency_results: dict[str, ToolResult] | None = None,
    ) -> Any:
        """Invoke a trusted adapter. Implementations must not trust LLM arguments."""
        raise NotImplementedError
