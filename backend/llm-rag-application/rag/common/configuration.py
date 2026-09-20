"""The definition of the rag configuration."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from rag.common.configuration_wizard import ConfigWizard, configclass, configfield


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def resolve_project_path(path: str) -> str:
    """Resolve a local relative path against the project root."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return str(candidate.resolve())


@configclass
class VectorStoreConfig(ConfigWizard):
    """Configuration class for the Vector Store connection.
    """

    type: str = configfield(
        "type",
        default="pgvector",
        help_txt="The type of vector store",
    )
    host: str = configfield(
        "host",
        default="",
        help_txt="The host of the machine running Vector Store DB",
    )
    port: str = configfield(
        "port",
        default="",
        help_txt="The port of the machine running Vector Store DB",
    )
    user: str = configfield(
        "user",
        default="",
        help_txt="The username of the machine running Vector Store DB",
    )
    password: str = configfield(
        "password",
        default="",
        help_txt="The password of the machine running Vector Store DB",
    )
    kwargs: dict = configfield(
        "kwargs",
        default="",
        help_txt="",
    )


@configclass
class DatabaseConfig(ConfigWizard):
    """PostgreSQL connection shared by metadata storage and pgvector."""

    host: str = configfield("host", default="127.0.0.1")
    port: int = configfield("port", default=5432)
    user: str = configfield("user", default="postgres")
    password: str = configfield("password", default="")
    database: str = configfield("database", default="rag")


@configclass
class NotionConfig(ConfigWizard):
    """Read-only Notion connection. Keep the token in APP_NOTION_TOKEN."""

    token: str = configfield("token", default="")
    api_version: str = configfield("api_version", default="2026-03-11")
    timeout_seconds: float = configfield("timeout_seconds", default=30.0)
    max_retries: int = configfield("max_retries", default=4)


@configclass
class AuthServiceConfig(ConfigWizard):
    """External account service used by the web application."""

    base_url: str = configfield("base_url", default="http://10.3.6.163")
    timeout_seconds: float = configfield("timeout_seconds", default=10.0)
    captcha_path: str = configfield("captcha_path", default="/api/auth/app/captcha")
    sms_send_path: str = configfield(
        "sms_send_path", default="/api/auth/app/sms/captcha-send"
    )
    sms_login_path: str = configfield(
        "sms_login_path", default="/api/auth/app/sms/login"
    )
    password_login_path: str = configfield(
        "password_login_path", default="/api/auth/app/login"
    )
    set_password_path: str = configfield(
        "set_password_path", default="/api/auth/app/password"
    )
    profile_path: str = configfield("profile_path", default="/api/user/profile")
    logout_path: str = configfield("logout_path", default="/api/auth/app/logout")

    def endpoint(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


@configclass
class LLMConfig(ConfigWizard):
    """Configuration class for the llm connection.
    """

    api_key: str = configfield(
        "api_key",
        default="EMPTY",
        help_txt="API kEY.",
    )
    base_url: str = configfield(
        "base_url",
        default="",
        help_txt="The url of the online llm inference service.",
    )
    model_name: str = configfield(
        "model_name",
        default="",
        help_txt="The name of the hosted model.",
    )
    enable_thinking: bool = configfield(
        "enable_thinking",
        default=False,
        help_txt="Whether the compatible model should use thinking mode.",
    )

@configclass
class TextSplitterConfig(ConfigWizard):
    """Configuration class for the Text Splitter.

    :cvar chunk_size: Chunk size for text splitter. Tokens per chunk in token-based splitters.
    :cvar chunk_overlap: Text overlap in text splitter.
    """
    splitter_name: str = configfield(
        "splitter_name",
        default="ChineseTextSplitter",
        help_txt="Chunk size for text splitting.",
    )

    chunk_size: int = configfield(
        "chunk_size",
        default=510,
        help_txt="Chunk size for text splitting.",
    )
    chunk_overlap: int = configfield(
        "chunk_overlap",
        default=200,
        help_txt="Overlapping text length for splitting.",
    )

    smaller_chunk_size: int = configfield(
        "smaller_chunk_size",
        default=0,
        help_txt="",
    )

    smaller_chunk_overlap: int = configfield(
        "smaller_chunk_overlap",
        default=0,
        help_txt="Overlapping text length for child chunks.",
    )

    summary: int = configfield(
        "summary",
        default=0,
        help_txt="",
    )


@configclass
class EmbeddingConfig(ConfigWizard):
    """Configuration class for the Embeddings.
    """

    model_name_or_path: str = configfield(
        "model_name_or_path",
        default="./models/bge-m3",
        help_txt="The name or local path of huggingface embedding model.",
    )
    model_engine: str = configfield(
        "model_engine",
        default="huggingface",
        help_txt="The server type of the hosted model. Allowed values are hugginface",
    )
    modelscope_model_id: str = configfield(
        "modelscope_model_id",
        default="BAAI/bge-m3",
        help_txt="ModelScope model ID used when the local embedding model is missing.",
    )
    dimensions: int = configfield(
        "dimensions",
        default=1024,
        help_txt="The required dimensions of the embedding model. Currently utilized for vector DB indexing.",
    )
    sparse_dimensions: int = configfield(
        "sparse_dimensions",
        default=250002,
        help_txt="BGE-M3 tokenizer vocabulary size used by sparse vector indexing.",
    )

@configclass
class RerankConfig(ConfigWizard):
    """Configuration class for the Rerank Model.
    """
    model_name_or_path: str = configfield(
        "model_name_or_path",
        default="bge-reranker-large",
        help_txt="The model name or local path of rerank model.",
    )
    modelscope_model_id: str = configfield(
        "modelscope_model_id",
        default="BAAI/bge-reranker-large",
        help_txt="ModelScope model ID used when the local reranker model is missing.",
    )
    type: str = configfield(
        "type",
        default="rank",
        help_txt="The type of the rerank model. Allowed values are {rank, llm}",
    )
    relevance_gate_enabled: bool = configfield(
        "relevance_gate_enabled",
        default=True,
        help_txt="Use reranker score thresholds before falling back to an LLM judge.",
    )
    relevance_high_threshold: float = configfield(
        "relevance_high_threshold",
        default=2.0,
        help_txt="Top reranker score at or above which evidence is accepted directly.",
    )
    relevance_low_threshold: float = configfield(
        "relevance_low_threshold",
        default=0.0,
        help_txt="Top reranker score below which evidence is rejected directly.",
    )
    retrieval_candidate_k: int = configfield(
        "retrieval_candidate_k",
        default=15,
        help_txt="Number of documents recalled from vector search.",
    )
    reranker_top_k: int = configfield(
        "reranker_top_k",
        default=5,
        help_txt="Number of documents retained after reranking.",
    )
    reranker_candidate_k: int = configfield(
        "reranker_candidate_k",
        default=20,
        help_txt="Number of fused candidates scored by the reranker.",
    )


@configclass
class HybridSearchConfig(ConfigWizard):
    """BGE-M3 dense/sparse retrieval and rank-fusion configuration."""

    enabled: bool = configfield("enabled", default=False)
    provider: str = configfield("provider", default="postgresql")
    candidate_k: int = configfield("candidate_k", default=20)
    dense_weight: float = configfield("dense_weight", default=0.5)
    sparse_weight: float = configfield("sparse_weight", default=0.5)
    rrf_k: int = configfield("rrf_k", default=60)

    def __post_init__(self):
        if self.provider.lower() != "postgresql":
            raise ValueError("hybrid_search.provider must be 'postgresql'")
        if self.candidate_k < 1:
            raise ValueError("hybrid_search.candidate_k must be positive")
        if self.rrf_k < 1:
            raise ValueError("hybrid_search.rrf_k must be positive")
        if self.dense_weight < 0 or self.sparse_weight < 0:
            raise ValueError("hybrid search weights cannot be negative")
        if self.dense_weight == 0 and self.sparse_weight == 0:
            raise ValueError("at least one hybrid search weight must be positive")


@configclass
class FileRoutingConfig(ConfigWizard):
    """Optional LLM file-name routing before vector search."""

    enabled: bool = configfield(
        "enabled",
        default=False,
        help_txt="Select knowledge-base files by name before retrieval.",
    )


@configclass
class PromptsConfig(ConfigWizard):
    """Configuration class for the Prompts.

    :cvar chat_template: Prompt template for chat.
    :cvar rag_template: Prompt template for rag.
    """

    chat_template: str = configfield(
        "chat_template",
        default=(
            "<s>[INST] <<SYS>>"
            "你是一个乐于助人、尊重他人、诚实的助手。"
            "在安全的情况下，请尽可能提供帮助。"
            "请确保你的回答是积极的。"
            "<</SYS>>"
            "[/INST] {context} </s><s>[INST] {query} [/INST]"
        ),
        help_txt="Prompt template for chat.",
    )
    rag_template: str = configfield(
        "rag_template",
        default=(
            "<s>[INST] <<SYS>>"
            "根据已知信息，简洁和专业的来回答问题。如果无法从中得到答案，"
            "请说 “根据已知信息无法回答该问题”，不允许在答案中添加编造成分，答案请使用中文。"
            "<</SYS>>"
            "<s>[INST] 已知信息：{context} 问题：{query} 答案：[/INST]"
        ),
        help_txt="Prompt template for rag.",
    )


@configclass
class ServerConfig(ConfigWizard):

    api_base_url: str = configfield(
        "api_base_url",
        default="",
        help_txt="Internal URL used by Streamlit to call the FastAPI service.",
    )

    api_server_host: str = configfield(
        "api_server_host",
        default="127.0.0.1",
        help_txt="Api Server host",
    )

    api_server_port: int = configfield(
        "api_server_port",
        default=7861,
        help_txt="Api Server port",
    )

    web_server_port: int = configfield(
        "web_server_port",
        default=9003,
        help_txt="Web Server port",
    )

    default_knowledge_base: str = configfield(
        "default_knowledge_base",
        default="",
        help_txt="Knowledge base selected automatically for non-admin chat users.",
    )

    auth_enabled: bool = configfield(
        "auth_enabled",
        default=False,
        help_txt="Require the Streamlit service credential on API endpoints.",
    )

    auth_key: str = configfield(
        "auth_key",
        default="",
        help_txt="Shared application secret validated against X-API-Key.",
    )

    admin_user_ids: str = configfield(
        "admin_user_ids",
        default="",
        help_txt="Comma-separated external user IDs granted the admin role server-side.",
    )

    def get_admin_user_ids(self) -> frozenset[str]:
        return frozenset(
            user_id.strip()
            for user_id in self.admin_user_ids.split(",")
            if user_id.strip()
        )

    def get_api_base_url(self) -> str:
        """Return an explicit service URL or the local development default."""
        if self.api_base_url and self.api_base_url.strip():
            return self.api_base_url.strip().rstrip("/")
        return f"http://127.0.0.1:{self.api_server_port}"


def _parse_pairs(value: str) -> dict:
    """Parse a ``key=value,key=value`` configuration string."""
    pairs = {}
    for item in (value or "").split(","):
        key, separator, pair_value = item.partition("=")
        if separator and key.strip() and pair_value.strip():
            pairs[key.strip()] = pair_value.strip()
    return pairs


@configclass
class InternalAiConfig(ConfigWizard):
    """Medical-platform internal AI API (``/internal/v1/ai/*``) configuration.

    Secrets are never stored here: ``api_keys`` is injected by the deployment
    environment (``APP_INTERNAL_AI_API_KEYS``) and ``conf/config.yaml`` keeps it
    empty. Version fields must carry real registered values, because the frozen
    contract forbids placeholders such as ``unknown``/``latest``/``default``.
    """

    allowed_service: str = configfield(
        "allowed_service",
        default="medical-platform",
        help_txt="Value required in the X-Service-Name header of internal callers.",
    )
    api_keys: str = configfield(
        "api_keys",
        default="",
        help_txt=(
            "Comma-separated X-API-Key secrets injected by the deployment "
            "environment. The previous key may stay listed during rotation."
        ),
    )
    protocol_version: str = configfield(
        "protocol_version",
        default="1.0",
        help_txt="Protocol version required in X-Protocol-Version and the request body.",
    )
    output_schema_version: str = configfield(
        "output_schema_version",
        default="1.0",
        help_txt="Version reported in responses as output_schema_version.",
    )
    prompt_version: str = configfield(
        "prompt_version",
        default="",
        help_txt="Registered prompt version reported in responses; empty blocks readiness.",
    )
    safety_policy_version: str = configfield(
        "safety_policy_version",
        default="",
        help_txt="Registered safety policy version reported in responses; empty blocks readiness.",
    )
    max_body_bytes: int = configfield(
        "max_body_bytes",
        default=262144,
        help_txt="Maximum accepted request body size in bytes (256 KiB by default).",
    )
    knowledge_scopes: str = configfield(
        "knowledge_scopes",
        default="",
        help_txt=(
            "Comma-separated <scope_ref>=<knowledge_base> registrations mapping the "
            "opaque knowledge_scope_refs sent by callers to physical knowledge bases."
        ),
    )
    use_case_business_types: str = configfield(
        "use_case_business_types",
        default="",
        help_txt=(
            "Comma-separated <use_case>=<business_type> bindings used to isolate "
            "intents and knowledge bases per entry point."
        ),
    )

    def get_api_keys(self) -> tuple:
        return tuple(key.strip() for key in self.api_keys.split(",") if key.strip())

    def get_knowledge_scopes(self) -> dict:
        return _parse_pairs(self.knowledge_scopes)

    def get_use_case_business_types(self) -> dict:
        return _parse_pairs(self.use_case_business_types)


@configclass
class LangfuseConfig(ConfigWizard):

    langfuse_secret_key: str = configfield(
        "langfuse_secret_key",
        default="",
        help_txt=".",
    )

    langfuse_public_key: str = configfield(
        "langfuse_public_key",
        default="",
        help_txt=".",
    )

    langfuse_host: str = configfield(
        "langfuse_host",
        default="",
        help_txt=".",
    )


@configclass
class KnowledgeGraphConfig(ConfigWizard):

    type: str = configfield(
        "type",
        default="",
        help_txt="The type of the Graph DB",
    )
    ip: str = configfield(
        "ip",
        default="",
        help_txt="The ip of the Graph DB",
    )
    port: str = configfield(
        "port",
        default="",
        help_txt="The port of the Graph DB",
    )
    username: str = configfield(
        "username",
        default="",
        help_txt="The username of the Graph DB",
    )
    password: str = configfield(
        "password",
        default="",
        help_txt="The password of the Graph DB",
    )
    gql_generation_template: str = configfield(
        "gql_generation_template",
        default="",
        help_txt="",
    )
    kwargs: dict = configfield(
        "kwargs",
        default="",
        help_txt="",
    )


@configclass
class RagConfig(ConfigWizard):
    """Configuration class for the application.

    :cvar vector_store: The configuration of the vector db connection.
    :type vector_store: VectorStoreConfig
    :cvar llm: The configuration of the backend llm server.
    :type llm: LLMConfig
    :cvar text_splitter: The configuration for text splitter
    :type text_splitter: TextSplitterConfig
    :cvar embeddings: The configuration for huggingface embeddings
    :type embeddings: EmbeddingConfig
    :cvar prompts: The Prompts template for RAG and Chat
    :type prompts: PromptsConfig
    """

    vector_store: VectorStoreConfig = configfield(
        "vector_store",
        env=False,
        help_txt="The configuration of the vector db connection.",
        default=VectorStoreConfig(),
    )
    database: DatabaseConfig = configfield(
        "database",
        env=False,
        help_txt="PostgreSQL connection used by metadata storage and pgvector.",
        default=DatabaseConfig(),
    )
    notion: NotionConfig = configfield(
        "notion",
        env=False,
        help_txt="Read-only Notion ingestion configuration.",
        default=NotionConfig(),
    )
    auth_service: AuthServiceConfig = configfield(
        "auth_service",
        env=False,
        help_txt="External registration, login and user-profile API.",
        default=AuthServiceConfig(),
    )
    llm: LLMConfig = configfield(
        "llm",
        env=False,
        help_txt="The configuration for the server hosting the Large Language Models.",
        default=LLMConfig(),
    )
    router_llm: LLMConfig = configfield(
        "router_llm",
        env=False,
        help_txt="Fast non-thinking model used for routing and relevance decisions.",
        default=LLMConfig(),
    )
    generation_llm: LLMConfig = configfield(
        "generation_llm",
        env=False,
        help_txt="Model used to generate user-visible answers.",
        default=LLMConfig(),
    )
    text_splitter: TextSplitterConfig = configfield(
        "text_splitter",
        env=False,
        help_txt="The configuration for text splitter.",
        default=TextSplitterConfig(),
    )
    embeddings: EmbeddingConfig = configfield(
        "embeddings",
        env=False,
        help_txt="The configuration of embedding model.",
        default=EmbeddingConfig(),
    )
    reranker: RerankConfig = configfield(
        "reranker",
        env=False,
        help_txt="The configuration of rerank model.",
        default=RerankConfig(),
    )
    hybrid_search: HybridSearchConfig = configfield(
        "hybrid_search",
        env=False,
        help_txt="BGE-M3 dense + sparse hybrid retrieval configuration.",
        default=HybridSearchConfig(),
    )
    file_routing: FileRoutingConfig = configfield(
        "file_routing",
        env=False,
        help_txt="Route retrieval to selected knowledge-base files.",
        default=FileRoutingConfig(),
    )
    prompts: PromptsConfig = configfield(
        "prompts",
        env=False,
        help_txt="Prompt templates for chat and rag.",
        default=PromptsConfig(),
    )
    server: ServerConfig = configfield(
        "server",
        env=False,
        help_txt="Server args.",
        default=ServerConfig(),
    )
    internal_ai: InternalAiConfig = configfield(
        "internal_ai",
        env=False,
        help_txt="Medical-platform internal AI API contract and service identity.",
        default=InternalAiConfig(),
    )
    langfuse: LangfuseConfig = configfield(
        "langfuse",
        env=False,
        help_txt="",
        default=LangfuseConfig(),
    )
    knowledge_graph: KnowledgeGraphConfig = configfield(
        "knowledge_graph",
        env=False,
        help_txt="The configuration of the graph db.",
        default=KnowledgeGraphConfig(),
    )


@lru_cache
def get_config() -> "ConfigWizard":
    """Parse the application configuration."""
    config = RagConfig.from_file(str(PROJECT_ROOT / "conf" / "config.yaml"))
    if config:
        return config
    raise RuntimeError("Unable to find configuration.")


settings = get_config()
