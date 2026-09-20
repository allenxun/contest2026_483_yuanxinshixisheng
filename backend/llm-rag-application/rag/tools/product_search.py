"""Read-only tools for querying cosmetic and drug product tables."""
from __future__ import annotations

from typing import Any

from rag.tools.base import BaseTool, ToolContext, ToolDefinition, ToolResult


_COSMETIC_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "名称关键词"},
        "regulatory_number": {"type": "string", "description": "注册编号精确匹配"},
        "manufacturer": {"type": "string", "description": "生产企业"},
        "status": {"type": "string", "description": "产品状态"},
        "domestic_or_imported": {"type": "string", "description": "国产或进口"},
        "ordinary_or_special": {"type": "string", "description": "普通或特殊"},
        "limit": {"type": "integer", "description": "返回条数上限，1-50", "default": 10},
        "offset": {"type": "integer", "description": "偏移量", "default": 0},
    },
    "required": [],
}

_DRUG_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "名称关键词"},
        "approval_number": {"type": "string", "description": "批准文号精确匹配"},
        "manufacturer": {"type": "string", "description": "生产企业"},
        "status": {"type": "string", "description": "产品状态"},
        "domestic_or_imported": {"type": "string", "description": "国产或进口"},
        "limit": {"type": "integer", "description": "返回条数上限，1-50", "default": 10},
        "offset": {"type": "integer", "description": "偏移量", "default": 0},
    },
    "required": [],
}

_MAX_RETURN = 20


class CosmeticProductSearchTool(BaseTool):
    definition = ToolDefinition(
        name="cosmetic_product.search",
        description="查询化妆品注册备案信息，支持按注册编号、产品名称、生产企业等条件检索。",
        input_schema=_COSMETIC_SEARCH_SCHEMA,
        read_only=True,
        requires_confirmation=False,
        timeout_seconds=10.0,
    )

    def invoke(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        dependency_results: dict[str, ToolResult] | None = None,
    ) -> Any:
        from rag.connector.database.repository.product_repository import search_cosmetics

        limit = min(int(arguments.get("limit", 10)), _MAX_RETURN)
        try:
            results = search_cosmetics(
                query=arguments.get("query"),
                regulatory_number=arguments.get("regulatory_number"),
                manufacturer=arguments.get("manufacturer"),
                status=arguments.get("status"),
                domestic_or_imported=arguments.get("domestic_or_imported"),
                ordinary_or_special=arguments.get("ordinary_or_special"),
                limit=limit,
                offset=int(arguments.get("offset", 0)),
            )
        except ValueError:
            return {
                "product_type": "cosmetic",
                "count": 0,
                "message": "请提供产品名称、注册编号或生产企业中的至少一个条件",
                "results": [],
            }
        except Exception:
            return {
                "product_type": "cosmetic",
                "count": 0,
                "message": "查询产品数据时发生错误",
                "results": [],
            }

        return {
            "product_type": "cosmetic",
            "count": len(results),
            "results": results[:_MAX_RETURN],
        }


class DrugProductSearchTool(BaseTool):
    definition = ToolDefinition(
        name="drug_product.search",
        description="查询药品批准信息，支持按批准文号、通用名、生产企业等条件检索。",
        input_schema=_DRUG_SEARCH_SCHEMA,
        read_only=True,
        requires_confirmation=False,
        timeout_seconds=10.0,
    )

    def invoke(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        dependency_results: dict[str, ToolResult] | None = None,
    ) -> Any:
        from rag.connector.database.repository.product_repository import search_drugs

        limit = min(int(arguments.get("limit", 10)), _MAX_RETURN)
        try:
            results = search_drugs(
                query=arguments.get("query"),
                approval_number=arguments.get("approval_number"),
                manufacturer=arguments.get("manufacturer"),
                status=arguments.get("status"),
                domestic_or_imported=arguments.get("domestic_or_imported"),
                limit=limit,
                offset=int(arguments.get("offset", 0)),
            )
        except ValueError:
            return {
                "product_type": "drug",
                "count": 0,
                "message": "请提供药品名称、批准文号或生产企业中的至少一个条件",
                "results": [],
            }
        except Exception:
            return {
                "product_type": "drug",
                "count": 0,
                "message": "查询产品数据时发生错误",
                "results": [],
            }

        return {
            "product_type": "drug",
            "count": len(results),
            "results": results[:_MAX_RETURN],
        }
