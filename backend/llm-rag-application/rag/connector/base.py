from rag.common.configuration import settings
from rag.connector.utils import get_llm, get_embedding_model, get_vectorstore

embedding_model = get_embedding_model(settings.embeddings.model_name_or_path,
                                      settings.embeddings.model_engine,
                                      settings.embeddings.modelscope_model_id)


def _inherit_api_key(task_api_key, default_api_key):
    """Use the main LLM key when a task-specific key was not configured.

    LLMConfig historically defaults to ``EMPTY`` for local OpenAI-compatible
    services.  Newly introduced task configurations also receive that default
    when their YAML sections are absent, so a normal truthiness check is not
    sufficient for backwards-compatible inheritance.
    """
    normalized_key = (task_api_key or "").strip()
    if not normalized_key or normalized_key.upper() == "EMPTY":
        return default_api_key
    return normalized_key


def _build_task_llm(task_config, default_config):
    task_url = (task_config.base_url or "").strip()
    default_url = (default_config.base_url or "").strip()
    task_key = (task_config.api_key or "").strip()
    if task_url and default_url and task_url != default_url and (
        not task_key or task_key.upper() == "EMPTY"
    ):
        # A different provider URL cannot reuse the default API key.
        task_url = default_url
    return get_llm(
        api_key=_inherit_api_key(task_config.api_key, default_config.api_key),
        model_name=task_config.model_name or default_config.model_name,
        base_url=task_url or default_url,
        enable_thinking=task_config.enable_thinking,
    )


router_llm = _build_task_llm(settings.router_llm, settings.llm)
generation_llm = _build_task_llm(settings.generation_llm, settings.llm)

# Backwards-compatible alias for modules that have not yet declared a task role.
llm = generation_llm
