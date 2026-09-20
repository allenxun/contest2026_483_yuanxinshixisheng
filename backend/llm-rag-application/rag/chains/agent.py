from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from langchain_core.documents import Document

from rag.chains.query_router import PlannedTask, TaskPlan
from rag.tools.base import ToolContext, ToolResult
from rag.tools.executor import ToolExecutor


@dataclass
class TaskExecutionResult:
    task_id: str
    task_type: str
    status: str
    documents: list[Document] = field(default_factory=list)
    data: Any = None
    error: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    plan: TaskPlan
    task_results: dict[str, TaskExecutionResult]
    documents: list[Document]
    tool_results: list[ToolResult]

    @property
    def used_external_context(self) -> bool:
        return bool(self.documents or self.tool_results)


KnowledgeRunner = Callable[[PlannedTask], Awaitable[TaskExecutionResult]]


class AgentChain:
    """Execute a validated task DAG, parallelizing only ready tasks."""

    def __init__(self, knowledge_runner: KnowledgeRunner, tool_executor: ToolExecutor):
        self.knowledge_runner = knowledge_runner
        self.tool_executor = tool_executor

    async def _execute_task(
        self,
        task: PlannedTask,
        *,
        allowed_tools: frozenset[str],
        tool_context: ToolContext,
        completed: dict[str, TaskExecutionResult],
    ) -> TaskExecutionResult:
        failed_dependencies = [
            dependency
            for dependency in task.depends_on
            if completed[dependency].status not in {"success", "empty"}
        ]
        if failed_dependencies:
            return TaskExecutionResult(
                task.task_id,
                task.task_type,
                "blocked",
                error=f"Dependency failed: {', '.join(failed_dependencies)}",
            )
        if task.task_type == "chat":
            return TaskExecutionResult(task.task_id, "chat", "success")
        if task.task_type == "knowledge":
            return await self.knowledge_runner(task)

        dependency_tool_results = {
            task_id: ToolResult(
                tool_name=str(result.diagnostics.get("tool_name") or ""),
                status=result.status,
                data=result.data,
                error=result.error,
                task_id=task_id,
            )
            for task_id, result in completed.items()
            if task_id in task.depends_on and result.task_type == "tool"
        }
        result = await self.tool_executor.execute(
            task_id=task.task_id,
            tool_name=task.tool_name,
            arguments=task.arguments,
            allowed_tools=allowed_tools,
            context=tool_context,
            dependency_results=dependency_tool_results,
        )
        return TaskExecutionResult(
            task.task_id,
            "tool",
            result.status,
            data=result.data,
            error=result.error,
            diagnostics={"tool_name": result.tool_name},
        )

    async def run(
        self,
        plan: TaskPlan,
        *,
        allowed_tools: frozenset[str],
        tool_context: ToolContext,
    ) -> AgentResult:
        completed: dict[str, TaskExecutionResult] = {}
        pending = {task.task_id: task for task in plan.tasks}

        while pending:
            ready = [
                task
                for task in pending.values()
                if set(task.depends_on).issubset(completed)
            ]
            if not ready:
                # analyze_tasks rejects cycles, so reaching this branch means a
                # caller constructed a TaskPlan without validation.
                for task in pending.values():
                    completed[task.task_id] = TaskExecutionResult(
                        task.task_id, task.task_type, "blocked", error="Unresolved dependency"
                    )
                break
            outputs = await asyncio.gather(*[
                self._execute_task(
                    task,
                    allowed_tools=allowed_tools,
                    tool_context=tool_context,
                    completed=completed,
                )
                for task in ready
            ])
            for task, output in zip(ready, outputs):
                completed[task.task_id] = output
                pending.pop(task.task_id, None)

        documents: list[Document] = []
        tool_results: list[ToolResult] = []
        for result in completed.values():
            documents.extend(result.documents)
            if result.task_type == "tool":
                tool_results.append(ToolResult(
                    tool_name=str(result.diagnostics.get("tool_name") or ""),
                    status=result.status,
                    data=result.data,
                    error=result.error,
                    task_id=result.task_id,
                ))
        return AgentResult(plan, completed, documents, tool_results)
