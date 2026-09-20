# -*- coding: utf-8 -*-
import re
from typing import List, Optional, Any, Iterable
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from rag.common.utils import nltk, logger


def _split_text_with_regex_from_end(
        text: str, separator: str, keep_separator: bool
) -> List[str]:
    if separator:
        if keep_separator:
            # 根据分隔符对文本进行拆分, 并且保留分隔符
            _splits = re.split(f"({separator})", text)
            splits = ["".join(i) for i in zip(_splits[0::2], _splits[1::2])]
            if len(_splits) % 2 == 1:
                splits += _splits[-1:]
            # splits = [_splits[0]] + splits
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [s for s in splits if s != ""]


class ChineseRecursiveTextSplitter(RecursiveCharacterTextSplitter):
    def __init__(
            self,
            separators: Optional[List[str]] = None,
            keep_separator: bool = True,
            is_separator_regex: bool = True,
            **kwargs: Any,
    ) -> None:
        """Create a new TextSplitter."""
        super().__init__(keep_separator=keep_separator, **kwargs)
        self._separators = separators or [
            "\n\n",
            "\n",
            "。|！|？",
            "\.\s|\!\s|\?\s",
            "；|;\s",
            "，|,\s"
        ]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """Split incoming text and return chunks."""
        final_chunks = []
        # 取第一个为默认分隔符，剩余为候选分隔符
        separator = separators[-1]
        new_separators = []
        for i, _s in enumerate(separators):
            _separator = _s if self._is_separator_regex else re.escape(_s)
            if _s == "":
                separator = _s
                break
            if re.search(_separator, text):
                separator = _s
                new_separators = separators[i + 1:]
                break

        _separator = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex_from_end(text, _separator, self._keep_separator)

        _good_splits = []
        _separator = "" if self._keep_separator else separator
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, _separator)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, _separator)
            final_chunks.extend(merged_text)
        return [re.sub(r"\n{2,}", "\n", chunk.strip()) for chunk in final_chunks if chunk.strip()!=""]

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        """Split all documents by structural boundaries, then by text length."""
        chunks: List[Document] = []
        for document in documents:
            chunks.extend(self._split_structured_document(document))
        return chunks

    @staticmethod
    def _detect_heading(line: str):
        """Return ``(level, title)`` for Markdown and conservative plain headings."""
        stripped = line.strip()
        markdown = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", stripped)
        if markdown:
            return len(markdown.group(1)), markdown.group(2).strip()

        # PDF/OCR text often loses heading styles. Only recognize short,
        # conventional numbered lines to avoid treating normal prose as headings.
        if not stripped or len(stripped) > 80:
            return None
        plain_patterns = (
            (1, r"^第[一二三四五六七八九十百千万\d]+[章节篇部]\s*(.+)$"),
            (1, r"^[一二三四五六七八九十百千万]+、\s*(.+)$"),
            (2, r"^[（(][一二三四五六七八九十百千万\d]+[）)]\s*(.+)$"),
        )
        for level, pattern in plain_patterns:
            match = re.match(pattern, stripped)
            if match:
                return level, stripped

        decimal = re.match(r"^(\d+(?:\.\d+)+)[、.\s]+(.+)$", stripped)
        if decimal:
            return min(6, decimal.group(1).count(".") + 1), stripped
        return None

    @staticmethod
    def _is_table_row(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3

    @staticmethod
    def _is_table_separator(line: str) -> bool:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)

    @staticmethod
    def _context_metadata(base_metadata: dict, headers: dict) -> dict:
        metadata = dict(base_metadata)
        path = [headers[level] for level in sorted(headers) if headers[level]]
        metadata["context_path"] = " > ".join(path) if path else metadata.get(
            "document_title", "未分类"
        )
        for level, title in headers.items():
            if title:
                metadata[f"header_{level}"] = title
        return metadata

    def _split_table(self, lines: List[str], metadata: dict) -> List[Document]:
        """Split a Markdown table by complete rows and repeat the header."""
        header = lines[0]
        if len(lines) > 1 and self._is_table_separator(lines[1]):
            separator, rows = lines[1], lines[2:]
        else:
            column_count = max(1, header.count("|") - 1)
            separator = "| " + " | ".join(["---"] * column_count) + " |"
            rows = lines[1:]

        prefix = f"{header}\n{separator}"
        result, current_rows = [], []

        def emit(data_rows):
            chunk_metadata = dict(metadata)
            chunk_metadata["content_type"] = "table"
            chunk_metadata["table_header"] = header
            result.append(Document(
                page_content="\n".join([prefix, *data_rows]),
                metadata=chunk_metadata,
            ))

        for row in rows:
            candidate = "\n".join([prefix, *current_rows, row])
            if current_rows and self._length_function(candidate) > self._chunk_size:
                emit(current_rows)
                current_rows = [row]
            else:
                current_rows.append(row)
        emit(current_rows)
        return result

    def _split_structured_document(self, document: Document) -> List[Document]:
        """Prefer heading/table boundaries and use recursive splitting as fallback."""
        lines = document.page_content.splitlines()
        headers = {level: "" for level in range(1, 7)}
        current_lines: List[str] = []
        result: List[Document] = []
        index = 0

        def emit_text():
            if not current_lines:
                return
            # Consecutive headings only update the hierarchy. Do not create
            # low-value chunks that contain a heading and no actual content.
            has_body = any(
                line.strip() and self._detect_heading(line) is None
                for line in current_lines
            )
            if not has_body:
                current_lines.clear()
                return
            content = "\n".join(current_lines).strip()
            if content:
                metadata = self._context_metadata(document.metadata, headers)
                split_docs = self.create_documents([content], metadatas=[metadata])
                result.extend(
                    chunk
                    for chunk in split_docs
                    if any(
                        line.strip() and self._detect_heading(line) is None
                        for line in chunk.page_content.splitlines()
                    )
                )
            current_lines.clear()

        while index < len(lines):
            line = lines[index]
            heading = self._detect_heading(line)
            if heading:
                emit_text()
                level, title = heading
                headers[level] = title
                for child_level in range(level + 1, 7):
                    headers[child_level] = ""
                current_lines.append(line)
                index += 1
                continue

            if self._is_table_row(line):
                emit_text()
                table_lines = []
                while index < len(lines):
                    if self._is_table_row(lines[index]):
                        table_lines.append(lines[index].strip())
                        index += 1
                        continue
                    # Notion Markdown generated by older versions separated
                    # every table row with an empty line. Ignore that whitespace
                    # when the next non-empty line is another table row.
                    if not lines[index].strip():
                        next_index = index + 1
                        while next_index < len(lines) and not lines[next_index].strip():
                            next_index += 1
                        if (
                            next_index < len(lines)
                            and self._is_table_row(lines[next_index])
                        ):
                            index = next_index
                            continue
                    break
                metadata = self._context_metadata(document.metadata, headers)
                result.extend(self._split_table(table_lines, metadata))
                continue

            current_lines.append(line)
            index += 1

        emit_text()
        return result
