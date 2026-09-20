import os
import json
import httpx
import requests
import pydantic
from pydantic import BaseModel, ConfigDict
from pathlib import Path
from io import BytesIO
from typing import (
    Literal,
    Iterator,
    Optional,
    Callable,
    Generator,
    Dict,
    Any,
    Awaitable,
    Union,
    Tuple,
    List
)

from rag.common.configuration import settings
from rag.common.utils import logger


class BaseResponse(BaseModel):
    code: int = pydantic.Field(200, description="API status code")
    msg: str = pydantic.Field("success", description="API status message")
    data: Any = pydantic.Field(None, description="API data")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 200,
                "msg": "success",
            }
        }
    )


class ListResponse(BaseResponse):
    data: List[str] = pydantic.Field(..., description="List of names")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 200,
                "msg": "success",
                "data": ["doc1.docx", "doc2.pdf", "doc3.txt"],
            }
        }
    )


def _http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, list):
            parts = [
                str(item.get("msg") or item)
                for item in detail
                if item
            ]
            if parts:
                return "；".join(parts)
    text = (response.text or "").strip()
    return text or f"请求失败（HTTP {response.status_code}）"


class ApiRequest:
    '''
    api.py调用的封装（同步模式）,简化api调用方式
    '''

    def __init__(
            self,
            base_url: str = "",
            timeout: float = None,
            api_key: Optional[str] = None,
            access_token: Optional[str] = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self._use_async = False
        self._client = None
        # Attach the shared API key automatically so the Streamlit front-end stays
        # authenticated when settings.server.auth_enabled is true. An explicit
        # argument always wins over the configured value.
        self.api_key = (api_key or (settings.server.auth_key or "")).strip()
        self.access_token = (access_token or "").strip()

    def _auth_headers(self) -> Dict[str, str]:
        """Attach distinct application and end-user credentials."""
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    @property
    def client(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout,
                                        headers=self._auth_headers(),
                                        proxies={
                                            # do not use proxy for locahost
                                            "all://127.0.0.1": None,
                                            "all://localhost": None,
                                        })
        return self._client

    def post(
            self,
            url: str,
            data: Dict = None,
            json: Dict = None,
            retry: int = 3,
            stream: bool = False,
            **kwargs: Any
    ) -> Union[httpx.Response, Iterator[httpx.Response], None]:
        url = self.base_url + url
        while retry > 0:
            try:
                if stream:
                    return self.client.stream("POST", url, data=data, json=json, **kwargs)
                else:
                    return self.client.post(url, data=data, json=json, **kwargs)
            except Exception as e:
                msg = f"error when post {url}: {e}"
                logger.error(f'{e.__class__.__name__}: {msg}')
                retry -= 1

    def list_knowledge_bases(self):
        '''
        对应api.py/knowledge_base/list_knowledge_bases接口
        '''
        response = self.post("/knowledge_base/list_knowledge_bases")
        return response.json().get("data", [])

    def create_knowledge_base(
        self,
        knowledge_base_name: str,
        vector_store_type: str
    ):
        '''
        对应api.py/knowledge_base/create_knowledge_base接口
        '''
        data = {
            "knowledge_base_name": knowledge_base_name,
            "vector_store_type": vector_store_type
        }

        response = self.post(
            "/knowledge_base/create_knowledge_base",
            json=data,
        )
        return response.json()

    def clear_knowledge_base(
        self,
        knowledge_base_name: str
    ):
        '''
        对应api.py/knowledge_base/clear_knowledge_base接口
        '''
        response = self.post(
            "/knowledge_base/clear_knowledge_base",
            json=f"{knowledge_base_name}",
        )
        return response.json()

    def rename_knowledge_base(self, knowledge_base_name: str, new_name: str):
        response = self.post(
            "/knowledge_base/rename_knowledge_base",
            json={
                "knowledge_base_name": knowledge_base_name,
                "new_knowledge_base_name": new_name,
            },
        )
        return response.json()

    def delete_knowledge_base(self, knowledge_base_name: str):
        response = self.post(
            "/knowledge_base/delete_knowledge_base",
            json=knowledge_base_name,
        )
        return response.json()

    def delete_knowledge_files(self, knowledge_base_name: str, file_names: List[str]):
        response = self.post(
            "/knowledge_base/delete_files",
            json={"knowledge_base_name": knowledge_base_name, "file_names": file_names},
        )
        return response.json()

    def upload_kb_docs(
        self,
        files: List[Union[str, Path, bytes]],
        knowledge_base_name: str,
        override: bool = True,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        splitter_name: Optional[str] = None,
    ):
        '''
        对应api.py/knowledge_base/upload_docs接口
        '''

        def convert_file(file, filename=None):
            if isinstance(file, bytes):  # raw bytes
                file = BytesIO(file)
            elif hasattr(file, "read"):  # a file io like object
                filename = filename or file.name
            else:  # a local path
                file = Path(file).absolute().open("rb")
                filename = filename or os.path.split(file.name)[-1]
            return filename, file

        files = [convert_file(file) for file in files]
        data = {
            "knowledge_base_name": knowledge_base_name,
            "override": override
        }
        if chunk_size is not None:
            data["chunk_size"] = chunk_size
        if chunk_overlap is not None:
            data["chunk_overlap"] = chunk_overlap
        if splitter_name is not None:
            data["splitter_name"] = splitter_name
        response = self.post(
            "/knowledge_base/upload_docs",
            data=data,
            files=[
                ("files", (filename, file, 'application/octet-stream')) for filename, file in files
            ],
        )
        return response.json()

    def assess_weijing_report(self, file, session_id: str) -> Dict[str, Any]:
        filename = getattr(file, "name", "report")
        content = file.getvalue() if hasattr(file, "getvalue") else file.read()
        response = self.post(
            "/weijing/reports/assess",
            data={"session_id": session_id},
            files={"file": (filename, content, getattr(file, "type", None))},
        )
        if response.status_code >= 400:
            raise RuntimeError(_http_error_detail(response))
        return response.json()

    def get_weijing_assessment(self, assessment_id: str) -> Dict[str, Any]:
        response = self.client.get(
            f"{self.base_url}/weijing/assessments/{assessment_id}"
        )
        response.raise_for_status()
        return response.json()

    def knowledge_base_chat(
        self,
        query: str,
        knowledge_base_names: List[str],
        session_id: str = "",
        business_type: str = "customer",
        history: List[Dict] = [],
        stream: bool = True,
        return_docs: bool = False,
        show_reasoning: bool = False,
        return_details: bool = False,
    ):
        '''
        对应api.py/chat/knowledge_base_chat接口
        '''
        data = {
            "query": query,
            "knowledge_base_names": knowledge_base_names,
            "session_id": session_id,
            "business_type": business_type,
            "history": history,
            # "topk": 8,
            "stream": stream,
            "return_docs": return_docs,
            "show_reasoning": show_reasoning,
        }
        url = self.base_url + "/chat/knowledge_base_chat"
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        response = requests.request("POST", url, headers=headers, data=json.dumps(data), stream=True)
        accumulated_result = ""
        for chunk in response.iter_lines(decode_unicode=True):
            if chunk:
                if chunk.startswith("data: "):
                    data = json.loads(chunk[6:].strip())
                elif chunk.startswith(":"):
                    continue
                else:
                    data = json.loads(chunk)
                if return_details:
                    yield data
                    continue

                event_type = data.get("type")
                if event_type == "delta":
                    accumulated_result += data.get("delta", "")
                    # Preserve the original convenience API: callers that do
                    # not request details still receive the accumulated answer.
                    yield accumulated_result
                elif event_type == "error":
                    raise RuntimeError(data.get("message") or "模型服务调用失败")

    def sync_notion_pages(
        self,
        knowledge_base_name: str,
        page_ids: Optional[List[str]] = None,
        recursive: bool = True,
        force: bool = False,
    ):
        response = self.post(
            "/knowledge_base/sync_notion_pages",
            json={
                "knowledge_base_name": knowledge_base_name,
                "page_ids": page_ids or [],
                "recursive": recursive,
                "force": force,
            },
        )
        return response.json()

        # response = self.post(
        #     "/chat/knowledge_base_chat",
        #     json=data,
        #     stream=True,
        # )
        # with response as r:
        #     for chunk in r.iter_text(None):
        #         if chunk.startswith("data: "):
        #             print(chunk)
        #             data = json.loads(chunk[6:-2])
        #         else:
        #             data = json.loads(chunk)
        #         yield data.get("result")


if __name__ == "__main__":
    api = ApiRequest("http://127.0.0.1:7861")
    # res = api.list_knowledge_bases()
    # res = api.create_knowledge_base(knowledge_base_name="test_webui_api",
    #                                 vector_store_type="pgvector")
    # res = api.upload_kb_docs(["/Users/ethan/Desktop/常见疾病知识大全.txt"],
    #                          "test_webui_api")
    # res = api.clear_knowledge_base("test")
    # print(res)

    for res in api.knowledge_base_chat(query="帮我写一篇500字的散文", knowledge_base_names=["test"]):
        print(res)
