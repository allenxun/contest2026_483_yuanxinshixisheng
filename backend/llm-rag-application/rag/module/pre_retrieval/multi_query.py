import re

from langchain_core.prompts.prompt import PromptTemplate
from rag.connector.base import router_llm
from rag.common.utils import logger

# Default prompt
DEFAULT_QUERY_PROMPT = PromptTemplate(
    input_variables=["question"],
    template="""你是企业知识库的检索查询生成器，不回答问题。
根据给定的独立问题生成三个语义互补的检索表达，以改善向量召回。
要求：
1. 保持原意，不得加入问题中不存在的事实或答案。
2. 可以调整措辞、突出不同子问题或使用文档中可能出现的专业表述。
3. 每行只输出一个查询，不要编号、解释或使用 Markdown。
原始问题：{question}""",
)


def generate_queries(question: str):
    prompt = DEFAULT_QUERY_PROMPT.format(question=question)
    try:
        response = router_llm.invoke(prompt)
        content = getattr(response, "content", response)
        queries = []
        for line in str(content).splitlines():
            query = re.sub(r"^\s*(?:[-•]|\d+[.)、])\s*", "", line).strip()
            if query and query != question and query not in queries:
                queries.append(query)
        return queries[:3]
    except Exception as exc:
        logger.warning("Multi Query 生成失败，退回单查询检索：%s", exc, exc_info=exc)
        return []
