"""Small Notion REST client focused on read-only RAG ingestion."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import httpx


NOTION_API_BASE = "https://api.notion.com/v1"


@dataclass(frozen=True)
class NotionPage:
    page_id: str
    title: str
    url: str
    last_edited_time: str
    markdown: str


def normalize_notion_id(value: str) -> str:
    """Accept a UUID or a normal Notion page URL and return a dashed UUID."""
    candidate = value.strip()
    if "://" in candidate:
        candidate = urlparse(candidate).path.rstrip("/").split("/")[-1]
    match = re.search(r"([0-9a-fA-F]{32})(?:$|[?-])", candidate.replace("-", ""))
    if not match:
        compact = re.sub(r"[^0-9a-fA-F]", "", candidate)
    else:
        compact = match.group(1)
    if len(compact) != 32:
        raise ValueError(f"无法识别 Notion 页面 ID：{value}")
    return f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}".lower()


def _plain_text(rich_text: Iterable[dict]) -> str:
    return "".join(item.get("plain_text", "") for item in rich_text or [])


class NotionClient:
    def __init__(
        self,
        token: str,
        api_version: str = "2026-03-11",
        timeout: float = 30.0,
        max_retries: int = 4,
    ):
        if not token:
            raise ValueError("未配置 APP_NOTION_TOKEN")
        self.max_retries = max_retries
        self.client = httpx.Client(
            base_url=NOTION_API_BASE,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
            },
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(self.max_retries + 1):
            response = self.client.request(method, path, **kwargs)
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response.json()
            if attempt == self.max_retries:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(2**attempt, 8)
            time.sleep(delay)
        raise RuntimeError("Notion API request failed")

    def retrieve_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{normalize_notion_id(page_id)}")

    def discover_pages(self) -> list[str]:
        """Discover every page currently shared with this Notion connection."""
        cursor = None
        page_ids: list[str] = []
        while True:
            body = {
                "page_size": 100,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "ascending", "timestamp": "last_edited_time"},
            }
            if cursor:
                body["start_cursor"] = cursor
            payload = self._request("POST", "/search", json=body)
            page_ids.extend(
                page["id"]
                for page in payload.get("results", [])
                if page.get("object") == "page" and not page.get("in_trash", False)
            )
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
        return page_ids

    def iter_block_children(self, block_id: str):
        cursor = None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            payload = self._request(
                "GET", f"/blocks/{normalize_notion_id(block_id)}/children", params=params
            )
            yield from payload.get("results", [])
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")

    @staticmethod
    def page_title(page: dict) -> str:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                title = _plain_text(prop.get("title", []))
                if title:
                    return title
        return "Untitled"

    def _block_markdown(self, block: dict, depth: int) -> str:
        block_type = block.get("type", "unsupported")
        value = block.get(block_type, {})
        text = _plain_text(value.get("rich_text", []))
        indent = "  " * depth
        if block_type.startswith("heading_"):
            level = block_type.rsplit("_", 1)[-1]
            return f"{'#' * int(level)} {text}" if text else ""
        if block_type == "bulleted_list_item":
            return f"{indent}- {text}"
        if block_type == "numbered_list_item":
            return f"{indent}1. {text}"
        if block_type == "to_do":
            return f"{indent}- [{'x' if value.get('checked') else ' '}] {text}"
        if block_type in {"quote", "callout"}:
            return f"> {text}"
        if block_type == "code":
            return f"```{value.get('language', '')}\n{text}\n```"
        if block_type == "equation":
            return f"$${value.get('expression', '')}$$"
        if block_type == "divider":
            return "---"
        if block_type == "table_row":
            cells = [_plain_text(cell) for cell in value.get("cells", [])]
            return "| " + " | ".join(cells) + " |"
        if block_type in {"bookmark", "embed", "link_preview"}:
            url = value.get("url", "")
            return f"[{url}]({url})" if url else ""
        if block_type == "image":
            # Notion returns a short-lived, heavily signed object-storage URL.
            # Without image understanding/OCR it carries no searchable meaning
            # and can become a very large standalone chunk, so omit it entirely.
            return ""
        if block_type in {"video", "audio", "file", "pdf"}:
            file_value = value.get(value.get("type", ""), {})
            url = file_value.get("url", "")
            caption = _plain_text(value.get("caption", [])) or block_type
            return f"[{caption}]({url})" if url else f"[{caption}]"
        if block_type == "child_page":
            return f"## {value.get('title', 'Untitled')}"
        if block_type == "unsupported":
            return f"[Unsupported Notion block: {value.get('block_type', 'unknown')}]"
        return text

    def render_blocks(self, block_id: str, depth: int = 0) -> tuple[str, list[str]]:
        lines: list[str] = []
        child_page_ids: list[str] = []
        for block in self.iter_block_children(block_id):
            block_type = block.get("type", "unsupported")
            line = self._block_markdown(block, depth)
            if line:
                lines.append(line)
            if block_type == "child_page":
                child_page_ids.append(block["id"])
            elif block.get("has_children"):
                nested, nested_pages = self.render_blocks(block["id"], depth + 1)
                if nested:
                    if block_type == "table":
                        row_lines = [
                            row for row in nested.splitlines() if row.strip()
                        ]
                        if row_lines:
                            column_count = max(1, row_lines[0].count("|") - 1)
                            separator = (
                                "| " + " | ".join(["---"] * column_count) + " |"
                            )
                            table_config = block.get("table", {})
                            if table_config.get("has_column_header"):
                                nested = "\n".join(
                                    [row_lines[0], separator, *row_lines[1:]]
                                )
                            else:
                                generated_header = (
                                    "| "
                                    + " | ".join(
                                        f"列{index}"
                                        for index in range(1, column_count + 1)
                                    )
                                    + " |"
                                )
                                nested = "\n".join(
                                    [generated_header, separator, *row_lines]
                                )
                    lines.append(nested)
                child_page_ids.extend(nested_pages)
        return "\n\n".join(lines), child_page_ids

    def fetch_page(self, page_id: str) -> tuple[NotionPage, list[str]]:
        normalized_id = normalize_notion_id(page_id)
        page = self.retrieve_page(normalized_id)
        title = self.page_title(page)
        body, child_page_ids = self.render_blocks(normalized_id)
        markdown = f"# {title}\n\n{body}".strip() + "\n"
        return NotionPage(
            page_id=normalized_id,
            title=title,
            url=page.get("url", ""),
            last_edited_time=page.get("last_edited_time", ""),
            markdown=markdown,
        ), child_page_ids

    def fetch_pages(self, page_ids: list[str] | None = None, recursive: bool = True) -> list[NotionPage]:
        seeds = page_ids or self.discover_pages()
        queue = [normalize_notion_id(page_id) for page_id in seeds]
        visited: set[str] = set()
        pages: list[NotionPage] = []
        while queue:
            page_id = queue.pop(0)
            if page_id in visited:
                continue
            visited.add(page_id)
            page, child_page_ids = self.fetch_page(page_id)
            pages.append(page)
            if recursive:
                queue.extend(normalize_notion_id(item) for item in child_page_ids)
        return pages
