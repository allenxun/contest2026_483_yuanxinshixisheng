"""Notion-to-knowledge-base synchronization endpoint."""

from __future__ import annotations

import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import List

from fastapi import Body

from rag.chains.indexing import IndexingChain
from rag.common.configuration import settings
from rag.common.utils import logger
from rag.connector.database.repository.knowledge_file_repository import (
    delete_file_from_db,
    get_file_detail,
)
from rag.connector.database.repository.indexing_diagnostic_repository import (
    find_notion_filename,
)
from rag.connector.database.utils import KnowledgeFile, get_file_path
from rag.connector.notion import NotionClient
from server.knowledge import KBServiceFactory, validate_vectorstore_name
from server.utils import BaseResponse


def _safe_title(title: str) -> str:
    """Return a Windows-safe filename stem while preserving the page title."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)
    safe = re.sub(r"\s+", " ", safe).strip(" ._")
    return safe[:150] or "Untitled"


def _page_filename(title: str, page_id: str, duplicate_title: bool) -> str:
    stem = _safe_title(title)
    if duplicate_title:
        stem = f"{stem} ({page_id.replace('-', '')[-8:]})"
    return f"{stem}.md"


def _atomic_write(path: str, content: bytes):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".notion-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def sync_notion_pages(
    knowledge_base_name: str = Body(..., description="目标知识库"),
    page_ids: List[str] = Body(
        default=[],
        description="可选。为空时同步 Connection 有权访问的全部页面；填写后只同步指定页面",
    ),
    recursive: bool = Body(True, description="是否递归同步子页面"),
    force: bool = Body(False, description="即使内容未变化也重新索引"),
    chunk_size: int = Body(settings.text_splitter.chunk_size),
    chunk_overlap: int = Body(settings.text_splitter.chunk_overlap),
) -> BaseResponse:
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")
    vectorstore = KBServiceFactory.get_service_by_name(knowledge_base_name)
    if vectorstore is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")

    try:
        with NotionClient(
            token=settings.notion.token,
            api_version=settings.notion.api_version,
            timeout=settings.notion.timeout_seconds,
            max_retries=settings.notion.max_retries,
        ) as client:
            pages = client.fetch_pages(page_ids or None, recursive=recursive)
    except Exception as exc:
        logger.error("拉取 Notion 页面失败：%s", exc, exc_info=exc)
        return BaseResponse(code=502, msg=f"拉取 Notion 页面失败：{exc}")

    indexed, skipped, failed = [], [], {}
    title_counts = Counter(_safe_title(page.title).casefold() for page in pages)
    for page in pages:
        safe_title = _safe_title(page.title)
        filename = _page_filename(
            page.title,
            page.page_id,
            duplicate_title=title_counts[safe_title.casefold()] > 1,
        )
        filepath = get_file_path(knowledge_base_name, filename)
        content = page.markdown.encode("utf-8")
        try:
            previous_filename = find_notion_filename(knowledge_base_name, page.page_id)
            unchanged = (
                os.path.isfile(filepath)
                and Path(filepath).read_bytes() == content
                and bool(get_file_detail(knowledge_base_name, filename))
            )
            if unchanged and not force:
                skipped.append(filename)
                continue
            _atomic_write(filepath, content)
            knowledge_file = KnowledgeFile(filename, knowledge_base_name)
            knowledge_file.source_metadata = {
                "source_type": "notion",
                "notion_page_id": page.page_id,
                "notion_url": page.url,
                "notion_last_edited_time": page.last_edited_time,
                "title": page.title,
            }
            chain = IndexingChain(
                vectorstore=vectorstore,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                multi_vector_param={
                    "smaller_chunk_size": settings.text_splitter.smaller_chunk_size,
                    "smaller_chunk_overlap": settings.text_splitter.smaller_chunk_overlap,
                    "summary": settings.text_splitter.summary,
                },
            )
            errors = chain.chain([knowledge_file])
            if errors:
                failed[filename] = errors.get(filename, str(errors))
            else:
                indexed.append(filename)
                # Migrate files created by the earlier ID-only naming scheme only
                # after the title-based document has been indexed successfully.
                legacy_filename = f"notion_{page.page_id.replace('-', '')}.md"
                obsolete_filenames = {
                    item
                    for item in (previous_filename, legacy_filename)
                    if item and item != filename
                }
                for obsolete_filename in obsolete_filenames:
                    obsolete_path = get_file_path(knowledge_base_name, obsolete_filename)
                    obsolete_file = KnowledgeFile(obsolete_filename, knowledge_base_name)
                    if get_file_detail(knowledge_base_name, obsolete_filename):
                        vectorstore.delete_doc(obsolete_filename)
                        delete_file_from_db(obsolete_file)
                    if os.path.isfile(obsolete_path):
                        os.unlink(obsolete_path)
        except Exception as exc:
            logger.error("同步 Notion 页面 %s 失败：%s", page.page_id, exc, exc_info=exc)
            failed[filename] = str(exc)

    return BaseResponse(
        code=207 if failed else 200,
        msg="Notion 页面同步完成",
        data={
            "discovered": len(pages),
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
        },
    )
