from .doc_loader import CustomizedOcrDocLoader
from .pdf_loader import CustomizedOcrPdfLoader
from .text_loader import Utf8TextLoader

LOADER_MAPPING = {
    "CustomizedOcrPdfLoader": [".pdf"],
    # UnstructuredFileLoader: [".pdf", ".txt"],
    "CustomizedOcrDocLoader": [".docx", ".doc"],
    "Utf8TextLoader": [".md", ".markdown", ".txt"],
}
