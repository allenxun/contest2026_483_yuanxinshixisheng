"""Synchronize all pages shared with the configured Notion connection."""

import os
import sys

import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rag.common.configuration import settings
from rag.connector.database.repository.knowledge_base_repository import list_kbs_from_db
from server.web_app import AUTH_TOKEN_KEY, resolve_principal
from server.utils import ApiRequest


try:
    principal = resolve_principal()
except Exception as exc:
    st.error(f"身份认证失败：{getattr(exc, 'detail', str(exc))}")
    st.stop()
if not principal.has_any_role({"admin"}):
    st.error("当前用户没有同步知识库的权限。")
    st.stop()

st.title("Notion Sync")
st.caption("自动发现 Connection 已获权访问的全部页面，并增量同步到知识库。")

knowledge_bases = list_kbs_from_db()[::-1]
if not knowledge_bases:
    st.warning("请先创建知识库。")
    st.stop()

selected_kb = st.selectbox("目标知识库", knowledge_bases)
force = st.checkbox("强制重新索引未变化页面", value=False)

with st.expander("高级：只同步指定页面"):
    st.caption("通常留空即可。需要限定范围时，每行填写一个页面 URL 或 ID。")
    page_input = st.text_area("页面 URL 或 ID", height=140)

if st.button("同步全部已连接页面", type="primary"):
    page_ids = [line.strip() for line in page_input.splitlines() if line.strip()]
    api = ApiRequest(
        settings.server.get_api_base_url(),
        timeout=1800,
        access_token=st.session_state[AUTH_TOKEN_KEY],
    )
    with st.spinner("正在发现 Notion 页面并增量同步……"):
        try:
            result = api.sync_notion_pages(
                selected_kb,
                page_ids=page_ids or None,
                recursive=True,
                force=force,
            )
        except Exception as exc:
            st.exception(exc)
        else:
            data = result.get("data") or {}
            if result.get("code") in (200, 207):
                st.success(result.get("msg", "同步完成"))
                left, middle, right = st.columns(3)
                left.metric("发现页面", data.get("discovered", 0))
                middle.metric("本次索引", len(data.get("indexed", [])))
                right.metric("跳过未变化", len(data.get("skipped", [])))
                if data.get("failed"):
                    st.error("部分页面同步失败")
                    st.json(data["failed"])
            else:
                st.error(result.get("msg", "同步失败"))
