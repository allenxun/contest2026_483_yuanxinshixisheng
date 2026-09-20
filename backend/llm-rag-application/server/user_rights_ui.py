import json
import os
from pathlib import Path

import streamlit as st
from docx import Document

from rag.connector.database.repository.chat_history_repository import (
    list_chat_messages,
    list_chat_sessions,
)
from rag.connector.database.repository.user_rights_repository import (
    create_feedback,
    delete_user_personal_data,
    has_current_consent,
    record_consent,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGREEMENT_VERSION = os.getenv("RAG_AGREEMENT_VERSION", "2026-08-19")


def _configured_document(env_name: str, default_name: str) -> Path:
    value = os.getenv(env_name, str(PROJECT_ROOT / "docs" / default_name))
    return Path(value).expanduser()


def read_legal_document(path: Path) -> str:
    if not path.exists():
        return f"⚠️ 尚未配置文档：`{path}`。请管理员上传正式版本后再开放服务。"
    if path.suffix.lower() == ".docx":
        return "\n\n".join(p.text.strip() for p in Document(path).paragraphs if p.text.strip())
    if path.suffix.lower() in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    return f"暂不支持在线预览 `{path.suffix}` 文件，请转换为 .docx、.md 或 .txt。"


def _legal_documents() -> tuple[tuple[str, Path, str], ...]:
    return (
        ("用户协议", _configured_document("RAG_USER_AGREEMENT_PATH", "用户协议.docx"), "agreement"),
        ("隐私政策", _configured_document("RAG_PRIVACY_POLICY_PATH", "隐私政策.docx"), "privacy"),
    )


def require_current_consent(user_id: str) -> None:
    if has_current_consent(user_id, AGREEMENT_VERSION):
        return

    st.title("使用前请阅读并同意")
    st.info("本服务提供美容相关信息，不构成效果保证，请谨慎判断。")
    documents = _legal_documents()
    tabs = st.tabs([item[0] for item in documents])
    documents_available = True
    for tab, (title, path, _) in zip(tabs, documents):
        with tab:
            content = read_legal_document(path)
            st.markdown(content)
            documents_available = documents_available and path.exists()
            if path.exists():
                st.download_button(f"下载{title}", path.read_bytes(), file_name=path.name,
                                   key=f"download_{title}")

    accepted = st.checkbox("我已阅读并同意《用户协议》和《隐私政策》")
    if st.button("同意并进入服务", type="primary",
                 disabled=not accepted or not documents_available):
        record_consent(user_id, AGREEMENT_VERSION)
        st.rerun()
    st.caption(f"协议版本：{AGREEMENT_VERSION}。协议更新后将重新征得同意。")
    st.stop()


@st.dialog("用户协议与隐私政策", width="large")
def show_legal_documents() -> None:
    documents = _legal_documents()
    tabs = st.tabs([item[0] for item in documents])
    for tab, (title, path, _) in zip(tabs, documents):
        with tab:
            st.markdown(read_legal_document(path))
            if path.exists():
                st.download_button(f"下载{title}", path.read_bytes(), file_name=path.name,
                                   key=f"dialog_download_{title}")


@st.dialog("投诉、举报与反馈")
def show_feedback_form(user_id: str, session_id: str | None) -> None:
    st.caption("我们会记录并核查反馈。一般反馈将在 7 个工作日内答复；涉及人身安全或违法内容的举报将优先处理。")
    with st.form("user_feedback_form", clear_on_submit=True):
        category = st.selectbox("反馈类型", ("反馈", "投诉", "违法或不良信息举报", "隐私与数据", "功能建议", "其他"))
        content = st.text_area("详细说明", max_chars=4000,
                               placeholder="请描述问题、出现时间及希望如何处理（请勿填写不必要的健康或身份信息）")
        contact = st.text_input("联系方式（选填）", max_chars=255)
        attach_session = st.checkbox("关联当前会话，便于核查", value=True)
        submitted = st.form_submit_button("提交反馈", type="primary")
    if submitted:
        if len(content.strip()) < 5:
            st.error("请至少填写 5 个字符的问题说明。")
        else:
            feedback_id = create_feedback(
                user_id, category, content, contact,
                session_id if attach_session else None,
            )
            st.success(f"提交成功。受理编号：{feedback_id}")


def export_user_conversations(user_id: str) -> bytes:
    payload = []
    for chat_session in list_chat_sessions(user_id, limit=1000):
        payload.append({
            "session": chat_session,
            "messages": list_chat_messages(chat_session["session_id"], user_id),
        })
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


@st.dialog("个人数据管理")
def show_data_controls(user_id: str) -> None:
    st.download_button(
        "导出全部会话（JSON）",
        data=export_user_conversations(user_id),
        file_name="我的会话数据.json",
        mime="application/json",
        use_container_width=True,
    )
    st.divider()
    st.warning("删除后，会话记录、协议同意记录和个性化推荐设置将无法恢复。投诉反馈为履行处理及审计义务，将按公示的保留期限另行保存。")
    confirmed = st.checkbox("我确认删除我的会话、同意记录和个性化推荐设置")
    if st.button("删除个人数据", disabled=not confirmed, use_container_width=True):
        delete_user_personal_data(user_id)
        for key in ("current_chat_session_id", "chat_session_selector"):
            st.session_state.pop(key, None)
        st.success("个人数据已删除。重新使用服务前需再次同意协议。")
