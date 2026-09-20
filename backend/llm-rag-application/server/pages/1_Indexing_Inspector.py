"""Inspect automatic indexing diagnostics and chunks already stored in pgvector."""

import os
import sys

import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rag.connector.database.repository.indexing_diagnostic_repository import (
    get_indexing_diagnostic,
    list_stored_chunks,
)
from rag.connector.database.repository.knowledge_base_repository import list_kbs_from_db
from rag.connector.database.repository.knowledge_file_repository import list_files_from_db
from server.web_app import resolve_principal


try:
    principal = resolve_principal()
except Exception as exc:
    st.error(f"身份认证失败：{getattr(exc, 'detail', str(exc))}")
    st.stop()
if not principal.has_any_role({"admin"}):
    st.error("当前用户没有查看索引诊断的权限。")
    st.stop()

st.title("Indexing Inspector")
st.caption("查看正常入库时自动产生的质量诊断，以及已经写入 pgvector 的真实 chunk。")

knowledge_bases = list_kbs_from_db()[::-1]
if not knowledge_bases:
    st.warning("当前没有知识库。")
    st.stop()

with st.sidebar:
    selected_kb = st.selectbox("知识库", knowledge_bases)
    files = list_files_from_db(selected_kb)
    if not files:
        st.info("这个知识库还没有文件。")
        st.stop()
    selected_file = st.selectbox("已入库文件", files)
    show_derived = st.checkbox("显示派生 chunk", value=True)

diagnostic = get_indexing_diagnostic(selected_kb, selected_file)
chunks = list_stored_chunks(selected_kb, selected_file)
if not show_derived:
    chunks = [chunk for chunk in chunks if chunk["type"] == "base"]

if not diagnostic:
    st.info("该文件是在诊断功能启用前入库的。重新上传或更新一次即可生成诊断记录。")
else:
    if diagnostic["status"] == "success":
        st.success("最近一次 Indexing 已完成")
    else:
        st.error(f"最近一次 Indexing 状态：{diagnostic['status']}　{diagnostic['error']}")

    st.caption(
        f"Loader：{diagnostic['loader_name']}　·　"
        f"Splitter：{diagnostic['splitter_name']}　·　"
        f"更新时间：{diagnostic['updated_at']}"
    )
    metrics = diagnostic["metrics"]
    columns = st.columns(6)
    columns[0].metric("原文字符", metrics.get("raw_characters", 0))
    columns[1].metric("原始 Documents", metrics.get("raw_document_count", 0))
    columns[2].metric("基础 Chunks", metrics.get("base_chunk_count", 0))
    columns[3].metric("派生 Chunks", metrics.get("derived_chunk_count", 0))
    columns[4].metric("平均长度", metrics.get("avg_chunk_length", 0))
    columns[5].metric("平均重叠", metrics.get("avg_actual_overlap", 0))

    if diagnostic["warnings"]:
        for warning in diagnostic["warnings"]:
            st.warning(warning)
    else:
        st.success("自动诊断没有发现明显的空块、重复块、过短块、超长块或内容丢失。")

overview_tab, chunks_tab, distribution_tab = st.tabs(["运行信息", "真实 Chunk", "长度分布"])

with overview_tab:
    if diagnostic:
        st.subheader("索引参数")
        st.json(diagnostic["parameters"])
        st.subheader("完整诊断指标")
        st.json(diagnostic["metrics"])
    st.metric("当前数据库中的 Chunk 数", len(chunks))

with chunks_tab:
    if not chunks:
        st.warning("没有查询到该文件对应的向量记录。")
    else:
        labels = [
            f"#{chunk['metadata'].get('chunk_index', index)} · "
            f"{chunk['characters']} 字符 · {chunk['type']}"
            for index, chunk in enumerate(chunks)
        ]
        selected_index = st.selectbox(
            "选择 Chunk", range(len(chunks)), format_func=lambda index: labels[index]
        )
        chunk = chunks[selected_index]
        st.text_area("数据库中的正文", chunk["content"], height=360, disabled=True)
        st.json(chunk["metadata"])
        left, right = st.columns(2)
        if selected_index > 0:
            with left.expander("前一个 Chunk"):
                st.text(chunks[selected_index - 1]["content"])
        if selected_index + 1 < len(chunks):
            with right.expander("后一个 Chunk"):
                st.text(chunks[selected_index + 1]["content"])

with distribution_tab:
    length_rows = [
        {
            "chunk": str(chunk["metadata"].get("chunk_index", index)),
            "characters": chunk["characters"],
        }
        for index, chunk in enumerate(chunks)
    ]
    if length_rows:
        st.bar_chart(length_rows, x="chunk", y="characters", height=320)
        st.dataframe(length_rows, use_container_width=True, hide_index=True)
