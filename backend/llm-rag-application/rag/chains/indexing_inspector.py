"""Quality metrics collected as a side effect of normal production indexing."""

import hashlib
from collections import Counter
from statistics import mean


def _actual_overlap(left: str, right: str, maximum: int) -> int:
    """Return the largest exact suffix/prefix overlap between adjacent chunks."""
    maximum = min(maximum, len(left), len(right))
    for size in range(maximum, 0, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def _inspect_chunks(raw_documents, chunks, chunk_size: int, chunk_overlap: int):
    raw_chars = sum(len(doc.page_content) for doc in raw_documents)
    lengths = [len(doc.page_content) for doc in chunks]
    empty_count = sum(not doc.page_content.strip() for doc in chunks)
    hashes = [
        hashlib.sha256(doc.page_content.strip().encode("utf-8")).hexdigest()
        for doc in chunks
    ]
    duplicate_count = sum(
        count - 1 for count in Counter(hashes).values() if count > 1
    )
    overlaps = [
        _actual_overlap(
            chunks[index - 1].page_content,
            chunks[index].page_content,
            chunk_overlap,
        )
        for index in range(1, len(chunks))
    ]
    short_limit = max(20, int(chunk_size * 0.2))
    short_count = sum(0 < length < short_limit for length in lengths)
    oversized_count = sum(length > int(chunk_size * 1.2) for length in lengths)

    warnings = []
    if not chunks:
        warnings.append("没有生成任何 chunk，请检查 Loader、文件内容和切分器。")
    if empty_count:
        warnings.append(f"发现 {empty_count} 个空 chunk，应在入库前过滤。")
    if duplicate_count:
        warnings.append(f"发现 {duplicate_count} 个完全重复的 chunk，可能造成重复召回。")
    if short_count:
        warnings.append(
            f"发现 {short_count} 个过短 chunk（少于 {short_limit} 字符），可能缺少检索语义。"
        )
    if oversized_count:
        warnings.append(
            f"发现 {oversized_count} 个明显超过目标长度的 chunk，请检查分隔符策略。"
        )
    if raw_chars and sum(lengths) < raw_chars * 0.8:
        warnings.append("切分后字符总量明显少于原文，可能存在内容丢失。")

    return {
        "raw_characters": raw_chars,
        "chunk_count": len(chunks),
        "min_chunk_length": min(lengths, default=0),
        "avg_chunk_length": round(mean(lengths), 1) if lengths else 0,
        "max_chunk_length": max(lengths, default=0),
        "short_chunk_count": short_count,
        "oversized_chunk_count": oversized_count,
        "duplicate_chunk_count": duplicate_count,
        "avg_actual_overlap": round(mean(overlaps), 1) if overlaps else 0,
        "configured_overlap": chunk_overlap,
    }, warnings


def build_indexing_diagnostic(
    file,
    raw_documents,
    chunks,
    chunk_size: int,
    chunk_overlap: int,
) -> dict:
    """Build the observability snapshot persisted after a normal indexing run."""
    base_chunks = [
        chunk
        for chunk in chunks
        if chunk.metadata.get("multi_vector_type") in (None, "parent", "standalone")
    ]
    derived_chunks = [
        chunk
        for chunk in chunks
        if chunk.metadata.get("multi_vector_type") not in (None, "parent", "standalone")
    ]
    metrics, warnings = _inspect_chunks(
        raw_documents, base_chunks, chunk_size, chunk_overlap
    )
    metrics.update(
        {
            "raw_document_count": len(raw_documents),
            "base_chunk_count": len(base_chunks),
            "derived_chunk_count": len(derived_chunks),
        }
    )
    return {
        "status": "success",
        "loader_name": file.document_loader.__name__,
        "splitter_name": file.text_splitter.__name__,
        "parameters": {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
        "metrics": metrics,
        "warnings": warnings,
        "error": "",
    }
