from langchain_core.documents import Document


def document_title(document: Document) -> str:
    metadata = document.metadata or {}
    title = str(metadata.get("document_title") or "").strip()
    if title:
        return title
    filename = str(metadata.get("filename") or metadata.get("title") or "").strip()
    if not filename:
        return ""
    return filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]


def format_document_passage(document: Document) -> str:
    """Prefix chunk text the same way embedding and generation see it."""
    metadata = document.metadata or {}
    title = document_title(document)
    context_path = str(metadata.get("context_path") or "").strip()
    headers = []
    if title:
        headers.append(f"文档标题：{title}")
    if context_path and context_path != title:
        headers.append(f"章节路径：{context_path}")
    content = document.page_content or ""
    if not headers:
        return content
    return "\n".join([*headers, content])
