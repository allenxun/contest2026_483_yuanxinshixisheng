from fastapi import FastAPI, Depends
import uvicorn
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from server.limiter import limiter
from server.utils import BaseResponse, ListResponse
from server.knowledge import (
    create_knowledge_base,
    rename_knowledge_base,
    delete_knowledge_base,
    delete_knowledge_files,
    clear_knowledge_base,
    upload_docs,
    list_kbs
)
from server.chat import knowledge_base_chat
from server.internal_ai import internal_ai_router
from server.trace import trace_rag_pipeline
from server.notion import sync_notion_pages
from server.identity import get_current_principal, require_any_role
from server.weijing import assess_report, get_assessment

VERSION = "v1.0"

# The API key authenticates the internal caller. The principal dependency then
# requires a user identity, and role dependencies authorize sensitive actions.
AUTHENTICATED = [Depends(get_current_principal)]
ADMIN_ONLY = [Depends(require_any_role("admin"))]


@limiter.exempt
async def health():
    """Lightweight liveness endpoint that does not touch models or databases."""
    return {"status": "ok"}


def create_app(run_mode: str = None):
    app = FastAPI(
        title="RAG API Server",
        version=VERSION
    )
    # 中间件使 default_limits 覆盖未单独装饰的业务路由。
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    mount_app_routes(app, run_mode=run_mode)
    return app


def mount_app_routes(app: FastAPI, run_mode: str = None):

    app.get("/health", tags=["System"], summary="服务健康检查")(health)

    # 医疗云后端调用的内部 AI 接口（/internal/*）。
    app.include_router(internal_ai_router)

    # 知识库相关
    app.post("/knowledge_base/list_knowledge_bases",
             tags=["Knowledge Base Management"],
             response_model=ListResponse,
             summary="获取知识库列表",
             dependencies=ADMIN_ONLY)(list_kbs)
    app.post("/knowledge_base/create_knowledge_base",
             tags=["Knowledge Base Management"],
             response_model=BaseResponse,
             summary="创建知识库",
             dependencies=ADMIN_ONLY)(create_knowledge_base)
    app.post("/knowledge_base/delete_knowledge_base",
             tags=["Knowledge Base Management"],
             response_model=BaseResponse,
             summary="删除知识库",
             dependencies=ADMIN_ONLY)(delete_knowledge_base)
    app.post("/knowledge_base/rename_knowledge_base",
             tags=["Knowledge Base Management"],
             response_model=BaseResponse,
             summary="重命名知识库",
             dependencies=ADMIN_ONLY)(rename_knowledge_base)
    app.post("/knowledge_base/delete_files",
             tags=["Knowledge Base Management"],
             response_model=BaseResponse,
             summary="删除知识库文件",
             dependencies=ADMIN_ONLY)(delete_knowledge_files)
    app.post("/knowledge_base/clear_knowledge_base",
             tags=["Knowledge Base Management"],
             response_model=BaseResponse,
             summary="清空知识库",
             dependencies=ADMIN_ONLY)(clear_knowledge_base)
    app.post("/knowledge_base/upload_docs",
             tags=["Knowledge Base Management"],
             response_model=BaseResponse,
             summary="上传文件到知识库，并/或进行向量化",
             dependencies=ADMIN_ONLY)(upload_docs)
    app.post(
        "/knowledge_base/sync_notion_pages",
        tags=["Knowledge Base Management"],
        response_model=BaseResponse,
        summary="同步多个 Notion 页面到知识库",
        dependencies=ADMIN_ONLY,
    )(sync_notion_pages)

    # 对话相关
    app.post("/chat/knowledge_base_chat",
             tags=["Chat"],
             summary="与知识库对话",
             dependencies=AUTHENTICATED)(knowledge_base_chat)

    app.post(
        "/weijing/reports/assess",
        tags=["Weijing Assessment"],
        summary="解析检测报告并一次生成微晶改善方案",
        dependencies=AUTHENTICATED,
    )(assess_report)
    app.get(
        "/weijing/assessments/{assessment_id}",
        tags=["Weijing Assessment"],
        summary="读取当前用户的微晶改善方案",
        dependencies=AUTHENTICATED,
    )(get_assessment)


def run_api(host, port, **kwargs):
    app = create_app()
    # 经反向代理按路径前缀挂载时（如 nginx /chat/api/ -> 本服务并剥掉前缀），
    # 通过 root_path 告知外部前缀，使 /docs Swagger 页面生成正确的
    # openapi.json 地址。直连部署时留空即可。
    extra_kwargs = {}
    if kwargs.get("root_path"):
        extra_kwargs["root_path"] = kwargs["root_path"]
    if kwargs.get("ssl_keyfile") and kwargs.get("ssl_certfile"):
        uvicorn.run(app,
                    host=host,
                    port=port,
                    ssl_keyfile=kwargs.get("ssl_keyfile"),
                    ssl_certfile=kwargs.get("ssl_certfile"),
                    **extra_kwargs,
                    )
    else:
        uvicorn.run(app,
                    host=host,
                    port=port,
                    **extra_kwargs)
