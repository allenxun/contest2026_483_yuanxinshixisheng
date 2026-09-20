import os
import uuid
from typing import List, Union, Tuple, Dict

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

from rag.common.utils import run_in_thread_pool, nltk, logger
from rag.module.indexing.splitter import SPLITER_MAPPING
from rag.module.indexing.multi_vector import (
    build_parent_child_chunks,
    generate_text_summaries,
)

from rag.chains.base import BaseIndexingChain
from rag.connector.vectorstore.base import VectorStoreBase
from rag.connector.database.repository.knowledge_file_repository import (
    delete_file_from_db,
    add_file_to_db,
    add_docs_to_db
)
from rag.connector.database.repository.indexing_diagnostic_repository import (
    save_indexing_diagnostic,
)
from rag.chains.indexing_inspector import build_indexing_diagnostic
from rag.connector.database.utils import KnowledgeFile


class IndexingChain(BaseIndexingChain):

    def __init__(self,
                 vectorstore: VectorStoreBase,
                 chunk_size: int,
                 chunk_overlap: int,
                 zh_title_enhance: bool = False,
                 multi_vector_param: Dict = None):
        self.vectorstore = vectorstore
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.zh_title_enhance = zh_title_enhance
        self.multi_vector_param = multi_vector_param or {}

    def load(self,
             file: KnowledgeFile,
             loader: None):
        """
        加载文件内容
        :param file:
        :param loader: 配置加载器，默认根据文件后缀名进行路由，也可指定
        :return:
        """
        if loader is None:
            loader_class = file.document_loader
        else:
            loader_class = loader
        file_path = file.filename if os.path.exists(file.filename) else file.filepath
        docs = loader_class(file_path).load()
        document_title = os.path.splitext(os.path.basename(file.filename))[0]
        for doc in docs:
            doc.metadata.update(file.source_metadata)
            doc.metadata.setdefault("filename", file.filename)
            doc.metadata.setdefault("document_title", document_title)
        return docs

    def split(self,
              docs: List[Document],
              splitter: Union[str, TextSplitter]): # Union[X, Y] means either X or Y
        if isinstance(splitter, str):
            splitter = SPLITER_MAPPING[splitter]
        splitter_class = splitter
        chunks = splitter_class(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        ).split_documents(documents=docs)
        if not chunks: return []
        for chunk_index, chunk in enumerate(chunks):
            chunk.metadata["id"] = str(uuid.uuid4()) # 遍历所有切分出的 chunk，在它们的 metadata（元数据）字典里打上唯一的id
            chunk.metadata["chunk_index"] = chunk_index

        smaller_chunk_size = int(self.multi_vector_param.get("smaller_chunk_size") or 0)
        smaller_chunk_overlap = int(
            self.multi_vector_param.get("smaller_chunk_overlap") or 0
        )
        summary = self.multi_vector_param.get("summary") # 每个 chunk 生成一段更短的自动摘要，再对这个摘要做一次向量化。
        if smaller_chunk_size > 0:
            if smaller_chunk_overlap >= smaller_chunk_size:
                raise ValueError("smaller_chunk_overlap 必须小于 smaller_chunk_size")
            child_splitter = splitter_class(
                chunk_size=smaller_chunk_size,
                chunk_overlap=smaller_chunk_overlap,
            )
            chunks = build_parent_child_chunks(
                chunks,
                child_splitter=child_splitter,
                child_chunk_size=smaller_chunk_size,
            )

        multi_vector_chunks = []
        if summary:
            summary_sources = (
                [
                    chunk
                    for chunk in chunks
                    if chunk.metadata.get("multi_vector_type") == "parent"
                ]
                if smaller_chunk_size > 0
                else chunks
            )
            multi_vector_chunks.extend(generate_text_summaries(summary_sources))

        return chunks + multi_vector_chunks

    def file2chunks(self, file, **kwargs) -> Tuple[bool, Tuple[KnowledgeFile, List[Document]]]:
        try:
            docs = self.load(file=file, loader=None)
            chunks = self.split(docs=docs, splitter=file.text_splitter)
            diagnostic = None
            try:
                diagnostic = build_indexing_diagnostic(
                    file=file,
                    raw_documents=docs,
                    chunks=chunks,
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )
            except Exception as diagnostic_error:
                logger.error("生成 indexing 诊断信息失败：%s", diagnostic_error)
            return True, (file, chunks, diagnostic)
        except Exception as e:
            msg = f"从文件 {file.filename} 加载文档时出错：{e}"
            logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
            try:
                save_indexing_diagnostic(
                    file.kb_name,
                    file.filename,
                    {
                        "status": "failed",
                        "loader_name": file.document_loader.__name__,
                        "splitter_name": file.text_splitter.__name__,
                        "parameters": {
                            "chunk_size": self.chunk_size,
                            "chunk_overlap": self.chunk_overlap,
                        },
                        "metrics": {},
                        "warnings": [],
                        "error": msg,
                    },
                )
            except Exception as diagnostic_error:
                logger.error("保存 indexing 失败诊断信息失败：%s", diagnostic_error)
            return False, (file, msg) # 打包了 原始文件对象 和 生成的 chunks 列表

    def store(self,
              file: KnowledgeFile,
              chunks: List[Document]):

        # step 1. 删除db中该文件相关记录
        del_status = delete_file_from_db(file)

        # step 2. 将docs更新到向量数据库，同样需要将老记录删除
        doc_infos = self.vectorstore.update_doc(file=file,
                                                docs=chunks)

        # shep 3. 将更新后的信息添加到db
        add_db_status = add_file_to_db(file, docs_count=len(chunks)) and \
                        add_docs_to_db(file.kb_name,
                                       file.filename,
                                       doc_infos=doc_infos)
        return del_status and add_db_status

    def chain(self,
              files: List[Union[KnowledgeFile, Tuple[str, str], Dict]], ):
        """
        利用多线程批量将磁盘文件转化成langchain Document，并存储到向量数据库.
        :param files:
        :return: status, (kb_name, file_name, docs | error)
        """
        failed_files = {}
        kwargs_list = []
        for i, file in enumerate(files):
            kwargs = {"file": file}
            kwargs_list.append(kwargs)

        for status, result in run_in_thread_pool(func=self.file2chunks, params=kwargs_list):
            if status:
                file, chunks, diagnostic = result
                store_status = self.store(file, chunks)
                try:
                    if diagnostic is None:
                        continue
                    if not store_status:
                        diagnostic["status"] = "failed"
                        diagnostic["error"] = "文档或向量元数据写入失败"
                    save_indexing_diagnostic(file.kb_name, file.filename, diagnostic)
                except Exception as diagnostic_error:
                    # Observability must never block the production indexing path.
                    logger.error(
                        "保存 indexing 诊断信息失败：%s",
                        diagnostic_error,
                        exc_info=diagnostic_error,
                    )
            else:
                file, error = result
                failed_files[file.filename] = error
        return failed_files
