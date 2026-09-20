from __future__ import annotations

import asyncio
import inspect
from typing import Any

from rag.tools.base import ToolContext, ToolResult
from rag.tools.registry import ToolRegistry


def _validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    required = schema.get("required", [])
    missing = [name for name in required if arguments.get(name) in (None, "")]
    if missing:
        return f"Missing required tool arguments: {', '.join(missing)}"
    properties = schema.get("properties", {})
    unknown = set(arguments).difference(properties) if properties else set()
    if unknown:
        return f"Unknown tool arguments: {', '.join(sorted(unknown))}"
    return None


class ToolExecutor:
    """Second authorization boundary between an LLM plan and business APIs."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(
        self,
        *,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_tools: set[str] | frozenset[str],
        context: ToolContext,
        dependency_results: dict[str, ToolResult] | None = None,
        confirmed: bool = False,
    ) -> ToolResult:
        if tool_name not in allowed_tools:
            return ToolResult(tool_name, "forbidden", error="Tool is not allowed", task_id=task_id)
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(tool_name, "unavailable", error="Tool adapter is not configured", task_id=task_id)
        definition = tool.definition
        if definition.requires_confirmation and not confirmed:
            return ToolResult(tool_name, "confirmation_required", task_id=task_id)
        error = _validate_arguments(arguments, definition.input_schema)
        if error:
            return ToolResult(tool_name, "invalid_arguments", error=error, task_id=task_id)

        try:
            if inspect.iscoroutinefunction(tool.invoke):
                result = await asyncio.wait_for(
                    tool.invoke(arguments, context, dependency_results or {}),
                    timeout=definition.timeout_seconds,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        tool.invoke,
                        arguments,
                        context,
                        dependency_results or {},
                    ),
                    timeout=definition.timeout_seconds,
                )
            return ToolResult(tool_name, "success", data=result, task_id=task_id)
        except asyncio.TimeoutError:
            return ToolResult(tool_name, "timeout", error="Tool execution timed out", task_id=task_id)
        except Exception as exc:
            return ToolResult(tool_name, "error", error=str(exc), task_id=task_id)
