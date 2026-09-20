from langchain_community.document_loaders import TextLoader


class Utf8TextLoader(TextLoader):
    """Load project-generated Markdown and text files consistently on Windows."""

    def __init__(self, file_path: str, **kwargs):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("autodetect_encoding", True)
        super().__init__(file_path, **kwargs)
