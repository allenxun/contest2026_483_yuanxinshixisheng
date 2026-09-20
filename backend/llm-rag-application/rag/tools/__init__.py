from rag.tools.base import BaseTool, ToolContext, ToolDefinition, ToolResult
from rag.tools.executor import ToolExecutor
from rag.tools.registry import ToolRegistry, tool_registry

_builtin_tools_registered = False


def register_builtin_tools() -> None:
    """Register all built-in tools into the global tool_registry.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _builtin_tools_registered
    if _builtin_tools_registered:
        return
    _builtin_tools_registered = True

    from rag.tools.product_search import CosmeticProductSearchTool, DrugProductSearchTool

    for tool_cls in (CosmeticProductSearchTool, DrugProductSearchTool):
        tool = tool_cls()
        name = tool.definition.name
        if tool_registry.get(name) is None:
            tool_registry.register(tool)


__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolDefinition",
    "ToolExecutor",
    "ToolRegistry",
    "ToolResult",
    "register_builtin_tools",
    "tool_registry",
]
