from io import BytesIO
import re
from typing import Iterator, List, Union

import numpy as np
from PIL import Image
from docx import Document, ImagePart
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from langchain_community.document_loaders import UnstructuredFileLoader

from rag.module.indexing.loader.ocr import get_rapid_ocr


class CustomizedOcrDocLoader(UnstructuredFileLoader):
    """Load paragraphs, tables, and text contained in Word images."""

    @staticmethod
    def _iter_block_items(
        parent: Union[DocxDocument, _Cell],
    ) -> Iterator[Union[Paragraph, Table]]:
        if isinstance(parent, DocxDocument):
            parent_element = parent.element.body
        elif isinstance(parent, _Cell):
            parent_element = parent._tc
        else:
            raise ValueError("CustomizedOcrDocLoader parse failed")

        for child in parent_element.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    def _extract_text(self, filepath: str) -> str:
        document = Document(filepath)
        text_blocks: List[str] = []
        rapid_ocr = None

        for block in self._iter_block_items(document):
            if isinstance(block, Paragraph):
                paragraph_text = block.text.strip()
                if paragraph_text:
                    style_name = getattr(block.style, "name", "") or ""
                    heading_match = re.match(
                        r"^(?:Heading|标题)\s*(\d+)$", style_name, re.IGNORECASE
                    )
                    if heading_match:
                        level = min(6, max(1, int(heading_match.group(1))))
                        paragraph_text = f"{'#' * level} {paragraph_text}"
                    text_blocks.append(paragraph_text)

                # OCR is initialized lazily because most Word files contain
                # selectable text and do not need image recognition.
                for image_element in block._element.xpath(".//pic:pic"):
                    for image_id in image_element.xpath(".//a:blip/@r:embed"):
                        part = document.part.related_parts.get(image_id)
                        if not isinstance(part, ImagePart):
                            continue
                        if rapid_ocr is None:
                            rapid_ocr = get_rapid_ocr()
                        with Image.open(BytesIO(part._blob)) as image:
                            ocr_result, _ = rapid_ocr(np.array(image))
                        if not ocr_result:
                            continue
                        ocr_text = "".join(
                            line[1].strip()
                            for line in ocr_result
                            if line[1].strip()
                        )
                        if ocr_text:
                            text_blocks.append(ocr_text)

            elif isinstance(block, Table):
                rows = []
                for row in block.rows:
                    cells = [
                        cell.text.strip().replace("\n", " ").replace("|", "\\|")
                        for cell in row.cells
                    ]
                    if any(cells):
                        rows.append("| " + " | ".join(cells) + " |")
                if rows:
                    column_count = max(1, len(block.rows[0].cells))
                    separator = "| " + " | ".join(["---"] * column_count) + " |"
                    text_blocks.append("\n".join([rows[0], separator, *rows[1:]]))

        return "\n".join(text_blocks)

    def _get_elements(self) -> List:
        from unstructured.partition.text import partition_text

        text = self._extract_text(self.file_path)
        return partition_text(text=text, **self.unstructured_kwargs)
