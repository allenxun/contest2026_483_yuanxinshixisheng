import uuid
from typing import List
from rag.connector.base import generation_llm
from langchain.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter


def build_parent_child_chunks(
    documents: List[Document],
    child_splitter: TextSplitter,
    child_chunk_size: int,
) -> List[Document]:
    """Create searchable small chunks and non-searchable context parents."""
    result: List[Document] = []

    for document in documents:
        if len(document.page_content) <= child_chunk_size:
            document.metadata["multi_vector_type"] = "standalone"
            result.append(document)
            continue

        parent_id = document.metadata["id"]
        document.metadata["multi_vector_type"] = "parent"
        result.append(document)

        children = child_splitter.split_documents([document])
        for child_index, child in enumerate(children):
            # Re-splitting a section only sees its local heading. Preserve the
            # full hierarchy already resolved while building the parent.
            for key, value in document.metadata.items():
                if key == "context_path" or key.startswith("header_"):
                    child.metadata[key] = value
            child.metadata["id"] = str(uuid.uuid4())
            child.metadata["parent_id"] = parent_id
            child.metadata["child_index"] = child_index
            child.metadata["multi_vector_type"] = "child"
            result.append(child)

    return result


TEXT_SUMMARY_TEMPLATE = """你是一位阅读能手，善于对总结归纳文章段落的摘要。
这些摘要将会被向量化并用于检索召回原始的文章段落，现在请你概括出下面这段话的要点。
文章段落内容: {text} 
总结: """


def generate_text_summaries(documents: List[Document]):
    doc_ids = [doc.metadata['id'] for doc in documents]
    tot_docs = []
    for i, doc in enumerate(documents):
        prompt = PromptTemplate.from_template(TEXT_SUMMARY_TEMPLATE).format(text=doc.page_content)
        parent_id = doc_ids[i]
        summary_doc = Document(
            page_content=generation_llm.invoke(prompt),
            metadata=dict(doc.metadata),
        )
        summary_doc.metadata['id'] = str(uuid.uuid4())
        summary_doc.metadata['parent_id'] = parent_id
        summary_doc.metadata['multi_vector_type'] = "text summary"
        tot_docs.append(summary_doc)

    return tot_docs


TABLE_SUMMARY_TEMPLATE = """你是一位阅读能手，善于对总结归纳文章中表格信息的摘要内容。
这些摘要将会被向量化并用于检索召回原始的文章段落，现在请你概括出下面这张表格的要点。
表格内容: {table} 
总结: """


def generate_table_summaries(documents: List[Document]):
    tot_docs = []
    for i, doc in enumerate(documents):
        prompt = PromptTemplate.from_template(TABLE_SUMMARY_TEMPLATE).format(table=doc.page_content)
        summary_doc = Document(generation_llm.invoke(prompt))
        summary_doc.metadata['id'] = str(uuid.uuid4())
        summary_doc.metadata['multi_vector_type'] = "table summary"
        tot_docs.append(summary_doc)

    return tot_docs
