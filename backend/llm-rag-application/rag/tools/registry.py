from __future__ import annotations

from rag.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def available_schemas(self, allowed_names) -> list[dict]:
        schemas = []
        for name in allowed_names:
            tool = self.get(name)
            if tool is None:
                continue
            definition = tool.definition
            schemas.append({
                "name": definition.name,
                "description": definition.description,
                "input_schema": definition.input_schema,
                "read_only": definition.read_only,
                "requires_confirmation": definition.requires_confirmation,
            })
        return schemas


# Adapters register here during application startup. It is intentionally empty
# until a real, authenticated business-system integration is configured.
tool_registry = ToolRegistry()
