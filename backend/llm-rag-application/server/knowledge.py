import os
import re
import shutil
import tempfile
import urllib
from pathlib import Path
from pydantic import Json
from typing import List
from fastapi import File, Form, Body, UploadFile, Request
from langchain_core.documents import Document

from server.utils import BaseResponse, ListResponse
from rag.common.configuration import settings
from rag.common.utils import run_in_thread_pool, logger
from rag.chains.indexing import IndexingChain
from rag.connector.database.repository.knowledge_base_repository import add_kb_to_db, list_kbs_from_db, delete_kb_from_db, load_kb_from_db
from rag.connector.database.repository.knowledge_file_repository import delete_file_from_db, delete_files_from_db
from rag.connector.database.utils import get_doc_path, KnowledgeFile
from rag.connector.utils import get_vectorstore
from rag.connector.base import embedding_model
from rag.module.indexing.splitter import SPLITER_MAPPING
from server.limiter import limiter

# 知识库名称白名单：仅允许字母、数字、下划线、连字符和中文字符，长度 1-64。
# 该名称会同时用于数据库表前缀、本地文件路径和向量库集合名，
# 必须排除所有路径分隔符和特殊字符以阻止路径穿越攻击。
_KB_NAME_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff-]{0,63}")


def validate_vectorstore_name(name: str) -> bool:
    """Return True only when *name* is safe to use as a KB identifier.

    The name is embedded into file-system paths, database table names and
    vector-store collection names, so it must be a strict alphanumeric
    identifier.  A regex whitelist replaces the old ``"../" in name`` blacklist
    which could be bypassed with ``..``, absolute paths or platform separators.
    """
    return bool(name and _KB_NAME_PATTERN.fullmatch(name))


# ── 文件上传安全限制 ──────────────────────────────────────────────────────────
# 允许上传的文件扩展名，与 LOADER_MAPPING 中支持的格式对齐。
ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".md", ".markdown", ".txt",
})

# 单个文件最大体积（字节），默认 300 MB。
MAX_UPLOAD_FILE_SIZE: int = 300 * 1024 * 1024

# 单次请求最大上传文件数。
MAX_UPLOAD_FILE_COUNT: int = 50
UPLOAD_COPY_CHUNK_SIZE: int = 1024 * 1024


def _safe_upload_path(knowledge_base_name: str, filename: str) -> Path:
    """Return a contained destination path or raise for an unsafe filename."""
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or Path(filename).is_absolute()
        or Path(filename).name != filename
    ):
        raise ValueError("文件名不能包含路径或特殊目录")

    upload_root = Path(get_doc_path(knowledge_base_name)).resolve()
    destination = (upload_root / filename).resolve()
    if destination.parent != upload_root:
        raise ValueError("文件路径超出知识库目录")
    return destination


def _validate_upload_files(files: list[UploadFile]) -> str | None:
    """Return an error message if the upload batch violates any limit, else None."""
    if not files:
        return "未上传任何文件"
    if len(files) > MAX_UPLOAD_FILE_COUNT:
        return f"单次上传文件数不能超过 {MAX_UPLOAD_FILE_COUNT}，当前 {len(files)} 个"

    for upload_file in files:
        filename = upload_file.filename or ""
        try:
            _safe_upload_path("validation", filename)
        except (OSError, ValueError) as exc:
            return f"非法文件名 '{filename}'：{exc}"

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
            return f"不支持的文件类型 '{ext}'（文件：{filename}）。允许的类型：{allowed}"

        # 检查文件大小：先 seek 到末尾获取 size，再回到开头。
        try:
            upload_file.file.seek(0, 2)  # seek to end
            size = upload_file.file.tell()
            upload_file.file.seek(0)  # rewind
        except (OSError, AttributeError):
            return f"无法确定文件 '{filename}' 的大小"
        if size > MAX_UPLOAD_FILE_SIZE:
            max_mb = MAX_UPLOAD_FILE_SIZE // (1024 * 1024)
            return f"文件 '{filename}' 大小 {size / (1024*1024):.1f} MB 超过上限 {max_mb} MB"

    return None


class KBServiceFactory:

    @staticmethod
    def get_service(kb_name: str,
                    vector_store_type: str):
        """TODO 支持选择语义化模型"""
        return get_vectorstore(kb_name, vector_store_type, embedding_model)

    @staticmethod
    def get_service_by_name(kb_name: str):
        """从db中查询知识库信息，知识库名称和向量数据库类型"""
        _, vs_type, embed_model = load_kb_from_db(kb_name)
        if _ is None:  # 数据库中查不到该数据库
            return None
        else:
            return KBServiceFactory.get_service(kb_name, vs_type)


def list_kbs():
    # Get List of Knowledge Base
    return ListResponse(data=list_kbs_from_db())


def create_knowledge_base(knowledge_base_name: str = Body("test_kb"),
                          vector_store_type: str = Body("pgvector")
                          ) -> BaseResponse:
    # Create selected knowledge base
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")

    if knowledge_base_name is None or knowledge_base_name.strip() == "":
        return BaseResponse(code=404, msg="知识库名称不能为空，请重新填写知识库名称")

    """step 1. 校验知识库是否已存在"""
    kb = KBServiceFactory.get_service_by_name(knowledge_base_name)
    if kb is not None:
        return BaseResponse(code=404, msg=f"已存在同名知识库 {knowledge_base_name}")
    # else:
    #     vs = KBServiceFactory.get_service(knowledge_base_name, vector_store_type)
    try:
        # 创建成功后知识库信息添加到数据库
        embed_model = settings.embeddings.model_name_or_path
        res = add_kb_to_db(knowledge_base_name, "", vector_store_type, embed_model)
        if not res:
            raise RuntimeError("保存知识库信息到数据库失败")
    except Exception as e:
        msg = f"创建知识库出错： {e}"
        logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
        return BaseResponse(code=500, msg=msg)

    return BaseResponse(code=200, msg=f"已新增知识库 {knowledge_base_name}")


def delete_knowledge_base(
        knowledge_base_name: str = Body("test_kb")
) -> BaseResponse:
    # Delete selected knowledge base
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")
    knowledge_base_name = urllib.parse.unquote(knowledge_base_name)

    kb = KBServiceFactory.get_service_by_name(knowledge_base_name)

    if kb is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")
    else:
        vs = kb  # 这里的kb指的是向量数据库
    try:
        vs.drop_vectorstore()
        status = delete_files_from_db(knowledge_base_name)
        status2 = delete_kb_from_db(knowledge_base_name)
        if status and status2:
            kb_directory = Path(get_doc_path(knowledge_base_name)).parent
            if kb_directory.exists():
                shutil.rmtree(kb_directory)
            return BaseResponse(code=200, msg=f"成功删除知识库 {knowledge_base_name}")
    except Exception as e:
        msg = f"删除知识库时出现意外： {e}"
        logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
        return BaseResponse(code=500, msg=msg)

    return BaseResponse(code=500, msg=f"删除知识库失败 {knowledge_base_name}")


def rename_knowledge_base(
        knowledge_base_name: str = Body(...),
        new_knowledge_base_name: str = Body(...),
) -> BaseResponse:
    """Rename a knowledge base and every persisted reference to its stable name."""
    old_name = urllib.parse.unquote(knowledge_base_name).strip()
    new_name = urllib.parse.unquote(new_knowledge_base_name).strip()
    if not validate_vectorstore_name(old_name) or not validate_vectorstore_name(new_name):
        return BaseResponse(code=403, msg="非法知识库名称")
    if old_name == new_name:
        return BaseResponse(code=400, msg="新名称与当前名称相同")
    if KBServiceFactory.get_service_by_name(old_name) is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {old_name}")
    if KBServiceFactory.get_service_by_name(new_name) is not None:
        return BaseResponse(code=409, msg=f"已存在同名知识库 {new_name}")

    from rag.connector.database.base import SessionLocal
    from rag.connector.database.models.chat_history_model import ChatSessionModel
    from rag.connector.database.models.indexing_diagnostic_model import IndexingDiagnosticModel
    from rag.connector.database.models.knowledge_base_model import KnowledgeBaseModel
    from rag.connector.database.models.knowledge_file_model import FileDocModel, KnowledgeFileModel
    from rag.connector.database.models.vector_document_model import VectorDocumentModel

    old_dir = Path(get_doc_path(old_name)).parent
    new_dir = Path(get_doc_path(new_name)).parent
    moved_directory = False
    try:
        if new_dir.exists():
            return BaseResponse(code=409, msg=f"目标目录已存在：{new_name}")
        if old_dir.exists():
            old_dir.rename(new_dir)
            moved_directory = True
        with SessionLocal.begin() as session:
            session.query(KnowledgeBaseModel).filter(
                KnowledgeBaseModel.kb_name.ilike(old_name)
            ).update({KnowledgeBaseModel.kb_name: new_name}, synchronize_session=False)
            for model in (KnowledgeFileModel, FileDocModel, VectorDocumentModel, IndexingDiagnosticModel):
                session.query(model).filter(model.kb_name == old_name).update(
                    {model.kb_name: new_name}, synchronize_session=False
                )
            session.query(ChatSessionModel).filter(
                ChatSessionModel.knowledge_base_name == old_name
            ).update(
                {ChatSessionModel.knowledge_base_name: new_name},
                synchronize_session=False,
            )
        get_vectorstore.cache_clear()
        return BaseResponse(code=200, msg=f"已将知识库 {old_name} 重命名为 {new_name}")
    except Exception as exc:
        if moved_directory and new_dir.exists() and not old_dir.exists():
            new_dir.rename(old_dir)
        logger.error("重命名知识库失败", exc_info=exc)
        return BaseResponse(code=500, msg=f"重命名知识库失败：{exc}")


def delete_knowledge_files(
        knowledge_base_name: str = Body(...),
        file_names: List[str] = Body(...),
) -> BaseResponse:
    """Delete selected source files together with their vectors and metadata."""
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")
    kb = KBServiceFactory.get_service_by_name(knowledge_base_name)
    if kb is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")
    names = list(dict.fromkeys(name for name in file_names if name))
    if not names:
        return BaseResponse(code=400, msg="请选择要删除的文件")

    failed_files = {}
    for file_name in names:
        try:
            file_path = _safe_upload_path(knowledge_base_name, file_name)
            kb.delete_doc(file_name)
            delete_file_from_db(KnowledgeFile(file_name, knowledge_base_name))
            if file_path.exists():
                file_path.unlink()
        except Exception as exc:
            failed_files[file_name] = str(exc)
            logger.error("删除知识库文件失败：%s", file_name, exc_info=exc)
    code = 200 if not failed_files else 500
    return BaseResponse(
        code=code,
        msg=f"已删除 {len(names) - len(failed_files)} 个文件",
        data={"failed_files": failed_files},
    )


def clear_knowledge_base(
        knowledge_base_name: str = Body("test_kb")
) -> BaseResponse:
    # Delete selected knowledge base
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")
    knowledge_base_name = urllib.parse.unquote(knowledge_base_name)

    kb = KBServiceFactory.get_service_by_name(knowledge_base_name)

    if kb is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")
    else:
        vs = kb  # 这里的kb指的是向量数据库
    try:
        vs.clear_vectorstore()
        status = delete_files_from_db(knowledge_base_name)
        if status:
            content_directory = Path(get_doc_path(knowledge_base_name))
            if content_directory.exists():
                shutil.rmtree(content_directory)
            content_directory.mkdir(parents=True, exist_ok=True)
            return BaseResponse(code=200, msg=f"成功清空知识库 {knowledge_base_name}")
    except Exception as e:
        msg = f"清空知识库时出现意外： {e}"
        logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
        return BaseResponse(code=500, msg=msg)

    return BaseResponse(code=500, msg=f"清空知识库失败 {knowledge_base_name}")


def _save_files_in_thread(files: List[UploadFile],
                          knowledge_base_name: str,
                          override: bool):
    """
    通过多线程将上传的文件保存到对应知识库目录内。
    生成器返回保存结果：{"code":200, "msg": "xxx", "data": {"knowledge_base_name":"xxx", "file_name": "xxx"}}
    """

    def save_file(file: UploadFile,
                  knowledge_base_name: str,
                  override: bool) -> dict:
        '''
        保存单个文件。
        '''
        filename = file.filename or ""
        data = {"knowledge_base_name": knowledge_base_name, "file_name": filename}
        try:
            file_path = _safe_upload_path(knowledge_base_name, filename)
            file_size = file.file.seek(0, 2)
            file.file.seek(0)
            if (os.path.isfile(file_path)
                    and not override
                    and os.path.getsize(file_path) == file_size
            ):
                file_status = f"文件 {filename} 已存在。"
                logger.warning(file_status)
                return dict(code=404, msg=file_status, data=data)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=file_path.parent, delete=False
                ) as destination:
                    temporary_path = Path(destination.name)
                    while chunk := file.file.read(UPLOAD_COPY_CHUNK_SIZE):
                        written += len(chunk)
                        if written > MAX_UPLOAD_FILE_SIZE:
                            raise ValueError("文件大小超过上传限制")
                        destination.write(chunk)
                os.replace(temporary_path, file_path)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
            return dict(code=200, msg=f"成功上传文件 {filename}", data=data)
        except Exception as e:
            msg = f"{filename} 文件上传失败，报错信息为: {e}"
            logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
            return dict(code=500, msg=msg, data=data)

    params = [{"file": file, "knowledge_base_name": knowledge_base_name, "override": override} for file in files]
    for result in run_in_thread_pool(save_file, params=params):
        yield result


CHUNK_SIZE = settings.text_splitter.chunk_size
OVERLAP_SIZE = settings.text_splitter.chunk_overlap
SPLITTER_NAME = settings.text_splitter.splitter_name
ZH_TITLE_ENHANCE = False


@limiter.limit("5/minute")
def upload_docs(
        request: Request,
        files: List[UploadFile] = File(..., description="上传文件，支持多文件"),
        knowledge_base_name: str = Form(..., description="知识库名称", examples=["samples"]),
        override: bool = Form(True, description="覆盖已有文件"),
        chunk_size: int = Form(CHUNK_SIZE, description="知识库中单段文本最大长度"),
        chunk_overlap: int = Form(OVERLAP_SIZE, description="知识库中相邻文本重合长度"),
        splitter_name: str = Form(SPLITTER_NAME, description="文档切分器名称"),
        zh_title_enhance: bool = Form(ZH_TITLE_ENHANCE, description="是否开启中文标题加强"),
) -> BaseResponse:
    """
    API接口：上传文件，并/或向量化
    """
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")

    # 文件上传安全校验：类型、大小、数量
    upload_error = _validate_upload_files(files)
    if upload_error:
        return BaseResponse(code=400, msg=upload_error)

    kb = KBServiceFactory.get_service_by_name(knowledge_base_name)
    if kb is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")

    failed_files = {}
    # file_names = list(docs.keys())
    file_names = []

    # 先将上传的文件保存到磁盘
    for result in _save_files_in_thread(files,
                                        knowledge_base_name=knowledge_base_name,
                                        override=override):
        filename = result["data"]["file_name"]
        if result["code"] != 200:
            failed_files[filename] = result["msg"]

        if result["code"] == 200 and filename not in file_names:
            file_names.append(filename)

    # 对保存的文件进行向量化
    result = update_docs(
        knowledge_base_name=knowledge_base_name,
        file_names=file_names,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        splitter_name=splitter_name,
        zh_title_enhance=zh_title_enhance,
    )
    failed_files.update(result.data["failed_files"])

    return BaseResponse(code=200, msg="文件上传与向量化完成", data={"failed_files": failed_files})


def update_docs(
        knowledge_base_name: str = Body(..., description="知识库名称", examples=["samples"]),
        file_names: List[str] = Body(..., description="文件名称，支持多文件", examples=[["file_name1", "text.txt"]]),
        chunk_size: int = Body(CHUNK_SIZE, description="知识库中单段文本最大长度"),
        chunk_overlap: int = Body(OVERLAP_SIZE, description="知识库中相邻文本重合长度"),
        splitter_name: str = Body(SPLITTER_NAME, description="文档切分器名称"),
        zh_title_enhance: bool = Body(ZH_TITLE_ENHANCE, description="是否开启中文标题加强"),
) -> BaseResponse:
    """
    更新知识库文档
    TODO: 支持用户上传自定义的结构化文档
    """
    if not validate_vectorstore_name(knowledge_base_name):
        return BaseResponse(code=403, msg="非法知识库名称")

    kb = KBServiceFactory.get_service_by_name(knowledge_base_name)
    if kb is None:
        return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")
    else:
        vs = kb

    failed_files = {}
    kb_files = []

    # 生成需要加载docs的文件列表
    for file_name in file_names:
        try:
            knowledge_file = KnowledgeFile(filename=file_name, knowledge_base_name=knowledge_base_name)
            if splitter_name not in SPLITER_MAPPING:
                raise ValueError(f"未知切分器：{splitter_name}")
            knowledge_file.text_splitter = SPLITER_MAPPING[splitter_name]
            kb_files.append(knowledge_file)
        except Exception as e:
            msg = f"加载文档 {file_name} 时出错：{e}"
            logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
            failed_files[file_name] = msg

    indexing_chain = IndexingChain(vectorstore=vs,
                                   chunk_size=chunk_size,
                                   chunk_overlap=chunk_overlap,
                                   zh_title_enhance=zh_title_enhance,
                                   multi_vector_param={"smaller_chunk_size": settings.text_splitter.smaller_chunk_size,
                                                       "smaller_chunk_overlap": settings.text_splitter.smaller_chunk_overlap,
                                                       "summary": settings.text_splitter.summary})
    failed_files = indexing_chain.chain(kb_files)

    return BaseResponse(code=200, msg=f"更新文档完成", data={"failed_files": failed_files})
