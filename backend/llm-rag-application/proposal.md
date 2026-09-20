# LLM-RAG 应用构建方案

## 代码结构

- `conf/`：应用配置文件。
- `rag/`：RAG 应用的核心代码。
- `server/`：FastAPI 服务与 Streamlit WebUI。
- `docs/`：用户协议与隐私政策，供 WebUI 展示和下载。
- `models/`：本地 Embedding 和 Reranker 模型，不提交到 Git；缺失时自动从 ModelScope 下载。
- `pyproject.toml`、`uv.lock`：Python 依赖及锁定版本。
- `start.py`：同时启动 FastAPI 与 Streamlit 的一键启动脚本。

## 环境准备

项目要求 Python 3.10 或 3.11，推荐使用 `uv` 严格按照 `uv.lock` 安装锁定依赖：

```shell
uv sync --frozen
```

该命令会创建或更新项目的 `.venv`，但不会修改 `uv.lock`。首次部署以及
`pyproject.toml` 或 `uv.lock` 更新后需要执行；仅重启服务时无需重复执行。

## 核心流程

- Indexing：解析并切分文档，生成向量后写入 PostgreSQL/pgvector。
- Retrieval：根据用户问题执行语义检索，可选 PostgreSQL 关键词检索与 RRF 融合。
- Rerank：使用本地 Reranker 对召回结果重新排序。
- Generate：结合检索结果调用已配置的大模型生成回答。

## 外部依赖

- PostgreSQL，并安装支持 `sparsevec` 的 `vector`（pgvector 0.7.0+）扩展。
- 统一账号服务，提供注册、登录、短信验证码和用户资料接口。
- 可访问的 OpenAI 兼容大模型 API。
- 首次缺少本地模型时，需要能够访问 ModelScope；下载完成后可离线加载模型。

具体数据库、模型与服务参数在 `conf/config.yaml` 中配置，敏感值应通过 `.env` 或环境变量注入，不要提交到 Git。

## 用户账号服务

WebUI 直接调用 `conf/config.yaml` 中的 `auth_service`。默认接入统一账号服务，
完成图形验证码、短信验证码、注册、登录、用户资料查询和退出登录。生产环境应
通过 `APP_AUTH_SERVICE_BASE_URL` 注入 HTTPS 地址，不要使用明文 HTTP。

## 用户角色

| 角色 | 操作范围 |
|---|---|
| 普通用户 `user` | 注册、登录、问答，以及管理自己的历史会话和个人数据。 |
| 管理员 `admin` | 包含普通用户能力，并可创建知识库、上传文档、同步 Notion、查看索引诊断和清空知识库。 |

统一账号接口登录的用户默认映射为普通用户。管理员权限应由独立的服务端管理
机制授予，不能由浏览器请求或客户端表单自行声明。

## 启动应用

完成依赖同步和服务器配置后，在项目根目录执行：

```shell
uv run python start.py
```

该命令同时启动 FastAPI 和 Streamlit，并完成幂等数据库建表。

服务器首次部署或依赖更新后的完整命令为：

```shell
uv sync --frozen
uv run python start.py
```

服务默认地址：

- FastAPI 文档：<http://127.0.0.1:7861/docs>
- Streamlit WebUI：<http://127.0.0.1:9003>

正式环境不直接向公网暴露 `7861`、`9003` 和 FastAPI `/docs`，通过 Nginx 等反向代理提供 HTTPS：

- `https://your-domain.com/` 代理到 Streamlit `127.0.0.1:9003`
- `https://your-domain.com/api/` 代理到 FastAPI `127.0.0.1:7861`

按 `Ctrl+C` 会同时停止 FastAPI 和 Streamlit。

已经完成数据库初始化时，可以把参数透传给 `start.py`，跳过建表：

```shell
uv run python start.py --skip-create-tables
```

端口和监听地址可以覆盖：

```shell
uv run python start.py --api-host 0.0.0.0 --api-port 7861 --web-host 0.0.0.0 --web-port 9003
```

## 分别启动

需要单独调试服务时，可以使用以下命令。

启动 FastAPI，并初始化数据库表：

```shell
uv run python -m server.main --create_tables
```

启动 Streamlit：

```shell
uv run streamlit run server/web_app.py --server.port 9003
```
