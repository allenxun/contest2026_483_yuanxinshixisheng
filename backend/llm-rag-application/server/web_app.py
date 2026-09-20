import html
import hashlib
import os, sys
import re
import time
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import streamlit as st
import requests

log_dir = os.path.join(PROJECT_ROOT, "logs")
if not os.path.exists(log_dir):
    os.mkdir(log_dir)

from server.identity import Principal, principal_from_external_profile
from server.auth_client import AuthServiceClient, AuthServiceError
from server.utils import ApiRequest
from rag.common.configuration import settings
from rag.business.registry import business_registry
from rag.connector.database.repository.user_rights_repository import (
    assign_business_identity,
    get_business_identity,
)
VECTOR_STORE_TYPE = settings.vector_store.type
EMB_MODEL = settings.embeddings.model_name_or_path
AUTH_TOKEN_KEY = "auth_access_token"
AUTH_PROFILE_KEY = "auth_user_profile"
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
auth_client = AuthServiceClient(settings.auth_service)


@st.cache_data(ttl=10, show_spinner=False)
def check_api_health(base_url):
    """Avoid repeating a health request on every Streamlit script rerun."""
    try:
        response = requests.get(f"{base_url}/health", timeout=3)
        if response.status_code == 200:
            return True, ""
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.RequestException as exc:
        return False, str(exc)


def resolve_principal() -> Principal:
    """Revalidate the current access token and resolve its account identity."""
    token = str(st.session_state.get(AUTH_TOKEN_KEY) or "").strip()
    if not token:
        raise AuthServiceError("请先登录。", 401)
    try:
        profile = auth_client.profile(token)
    except AuthServiceError as exc:
        if exc.status_code == 401:
            st.session_state.pop(AUTH_TOKEN_KEY, None)
            st.session_state.pop(AUTH_PROFILE_KEY, None)
        raise
    st.session_state[AUTH_PROFILE_KEY] = profile
    user_id = str(profile.get("user_id") or "").strip()
    principal = principal_from_external_profile(
        profile,
        settings.server.get_admin_user_ids(),
        get_business_identity(user_id),
    )
    if not principal.business_types and not principal.has_any_role({"admin"}):
        raise AuthServiceError("该账号尚未设置业务身份，请联系管理员。", 403)
    return principal


def complete_external_login(token: str) -> None:
    """Validate a new token by querying the profile before accepting the session."""
    profile = auth_client.profile(token)
    user_id = str(profile.get("user_id") or "").strip()
    if not user_id:
        raise AuthServiceError("用户信息缺少用户标识，无法登录。")
    st.session_state[AUTH_TOKEN_KEY] = token
    st.session_state[AUTH_PROFILE_KEY] = profile


def complete_external_registration(token: str, business_type: str) -> None:
    """Persist the chosen identity only after account registration succeeds."""
    profile = auth_client.profile(token)
    principal = principal_from_external_profile(
        profile,
        settings.server.get_admin_user_ids(),
        business_type,
    )
    if not principal.business_types:
        raise AuthServiceError("请选择有效的业务身份。", 400)
    assigned_business_type = next(iter(principal.business_types))
    try:
        assign_business_identity(principal.user_id, assigned_business_type)
    except ValueError as exc:
        raise AuthServiceError(str(exc), 409) from exc
    st.session_state[AUTH_TOKEN_KEY] = token
    st.session_state[AUTH_PROFILE_KEY] = profile


def clear_external_login(*, notify_server: bool = True) -> None:
    token = st.session_state.get(AUTH_TOKEN_KEY)
    if token and notify_server:
        try:
            auth_client.logout(token)
        except AuthServiceError:
            pass
    st.session_state.pop(AUTH_TOKEN_KEY, None)
    st.session_state.pop(AUTH_PROFILE_KEY, None)
    st.session_state.pop("login_captcha", None)
    st.session_state.pop("register_captcha", None)


@st.dialog("重命名对话")
def show_rename_chat_dialog(session_id: str, user_id: str, current_title: str) -> None:
    from rag.connector.database.repository.chat_history_repository import rename_chat_session

    renamed_title = st.text_input("对话名称", value=current_title, max_chars=60)
    if st.button("保存", type="primary", use_container_width=True):
        try:
            renamed = rename_chat_session(session_id, user_id, renamed_title)
        except ValueError as exc:
            st.error(str(exc))
            return
        if not renamed:
            st.error("无法重命名该对话。")
            return
        st.session_state.pop("conversation_dialog", None)
        st.rerun()


@st.dialog("删除对话")
def show_delete_chat_dialog(
    session_id: str,
    user_id: str,
    selected_kb: str | None,
    knowledge_base_list: list[str],
) -> None:
    from rag.connector.database.repository.chat_history_repository import (
        create_chat_session,
        delete_chat_session,
        list_chat_sessions,
    )

    st.warning("删除后，这条对话及其中的全部消息将无法恢复。")
    cancel_column, delete_column = st.columns(2)
    if cancel_column.button("取消", use_container_width=True):
        st.session_state.pop("conversation_dialog", None)
        st.rerun()
    if delete_column.button("确认删除", type="primary", use_container_width=True):
        delete_chat_session(session_id, user_id)
        remaining_sessions = list_chat_sessions(user_id)
        if remaining_sessions:
            next_session_id = remaining_sessions[0]["session_id"]
        else:
            next_session_id = create_chat_session(
                user_id,
                selected_kb if selected_kb in knowledge_base_list else None,
            )["session_id"]
        st.session_state["current_chat_session_id"] = next_session_id
        st.session_state.pop("conversation_dialog", None)
        st.rerun()


@st.dialog("删除文件")
def show_delete_kb_file_dialog(api, knowledge_base_name: str, file_name: str) -> None:
    st.warning(f"确认删除“{file_name}”？")
    st.caption("文件、索引和相关检索记录将一并删除。")
    cancel_column, confirm_column = st.columns(2)
    if cancel_column.button("取消", use_container_width=True):
        st.session_state.pop("pending_kb_file_delete", None)
        st.rerun()
    if confirm_column.button("确认删除", type="primary", use_container_width=True):
        response = api.delete_knowledge_files(knowledge_base_name, [file_name])
        if response.get("code") == 200:
            st.session_state.pop("pending_kb_file_delete", None)
            st.rerun()
        st.error(response.get("msg") or "文件删除失败")


def render_knowledge_sources(documents: list[dict]) -> None:
    if not documents:
        return
    with st.expander(f"知识依据（{len(documents)} 条）", expanded=False):
        for index, document in enumerate(documents, start=1):
            filename = html.escape(
                str(document.get("filename") or "来源未记录"), quote=True
            )
            knowledge_base = html.escape(
                str(document.get("knowledge_base") or "知识库未记录"), quote=True
            )
            source_url = html.escape(
                str(document.get("source_url") or ""), quote=True
            )
            content = " ".join(str(document.get("content") or "").split())
            if len(content) > 200:
                content = content[:200].rstrip() + "…"
            source_label = (
                f'<a href="{source_url}" target="_blank" rel="noopener noreferrer">'
                f'{filename}</a>'
                if source_url else filename
            )
            st.markdown(
                f'<div class="knowledge-source-item">'
                f'<div class="knowledge-source-title">{index}. {source_label}</div>'
                f'<div class="knowledge-source-meta">知识库：{knowledge_base}</div>'
                f'<div class="knowledge-source-excerpt">{html.escape(content)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_trace_performance(trace):
    performance = trace.get("performance") or {}
    if not performance:
        return
    st.markdown("**阶段耗时（秒）**")
    performance_labels = {
        "knowledge_base_check": "知识库检查",
        "intent_routing": "LLM 意图识别",
        "intent_recognition": "意图识别",
        "vector_store_setup": "向量库初始化",
        "pre_retrieval": "检索前处理",
        "file_routing": "LLM 文件路由",
        "query_embedding": "问题向量化",
        "vector_database": "向量数据库查询",
        "vector_search_total": "向量检索小计",
        "sparse_database": "BGE-M3 稀疏向量检索",
        "rrf_fusion": "RRF 排名融合",
        "reranker": "本地 Reranker",
        "retrieval_total": "完整检索小计",
        "relevance_assessment": "LLM 资料相关性判断",
        "before_generation": "生成前累计",
        "generation_first_chunk": "生成模型首片段",
        "time_to_first_chunk": "用户首字等待",
        "generation_total": "答案生成总耗时",
        "request_total": "请求总耗时",
    }
    for name, seconds in performance.items():
        label = performance_labels.get(name, name)
        if isinstance(seconds, (int, float)):
            st.text(f"{label}: {seconds:.3f} 秒")
        else:
            st.text(f"{label}: {seconds}")


def _render_retrieved_documents(documents):
    if not documents:
        return
    st.markdown(f"**检索证据（{len(documents)}条）**")
    for index, document in enumerate(documents, start=1):
        filename = document.get("filename") or "未知来源"
        chunk_index = document.get("chunk_index")
        score = document.get("similarity_score")
        sparse_score = document.get("sparse_score")
        fusion_score = document.get("fusion_score")
        details = []
        if chunk_index is not None:
            details.append(f"chunk {chunk_index}")
        if isinstance(score, (int, float)):
            details.append(f"向量分数 {score:.4f}")
        if isinstance(sparse_score, (int, float)):
            details.append(f"稀疏分数 {sparse_score:.4f}")
        if isinstance(fusion_score, (int, float)):
            details.append(f"RRF {fusion_score:.4f}")
        detail_text = f" · {' · '.join(details)}" if details else ""
        st.markdown(
            f"**[{index}] {filename}{detail_text}** "
            f"· {document.get('knowledge_base') or '未知知识库'}"
        )
        with st.container(border=True):
            content = html.escape(document.get("content") or "（文档内容为空）")
            st.markdown(
                f'<div class="retrieved-chunk-text">{content}</div>',
                unsafe_allow_html=True,
            )


def render_decision_trace(trace):
    if "intent_status" in trace or "intent_ids" in trace:
        intent_status_labels = {
            "confident": "已确认",
            "ambiguous": "意图不明确",
            "incomplete": "信息不完整",
            "oos": "超出范围",
        }
        evaluation = trace.get("retrieval_evaluation") or {}
        evaluation_labels = {
            "sufficient": "资料足以回答",
            "insufficient": "资料不足",
        }
        actions = trace.get("actions") or []
        has_knowledge = any(action.get("action_type") == "knowledge" for action in actions)
        columns = st.columns(3)
        columns[0].metric(
            "意图状态",
            intent_status_labels.get(
                trace.get("intent_status"),
                trace.get("intent_status") or "-",
            ),
        )
        columns[1].metric(
            "意图 ID",
            "、".join(trace.get("intent_ids") or []) or "未确认",
        )
        columns[2].metric(
            "资料判断",
            evaluation_labels.get(
                evaluation.get("status"),
                "已检索" if has_knowledge else "无需检索",
            ),
        )
        st.markdown(f"**用户目标：** {trace.get('user_goal') or '未提供'}")
        if trace.get("underlying_goal"):
            st.markdown(f"**潜在目标：** {trace.get('underlying_goal')}")
        st.markdown(f"**决策摘要：** {trace.get('reason_summary') or '未提供'}")
        information_needs = trace.get("information_needs") or []
        if information_needs:
            st.markdown("**信息需求：**")
            for need in information_needs:
                st.markdown(f"- {need}")
        retrieval_queries = trace.get("retrieval_queries") or []
        if retrieval_queries:
            st.markdown("**检索问题：**")
            for query in retrieval_queries:
                st.markdown(f"- {query}")
        missing_slots = trace.get("missing_slots") or []
        if missing_slots:
            st.warning("缺少槽位：" + "、".join(missing_slots))
        if actions:
            action_results = trace.get("action_results") or {}
            st.markdown("**执行动作**")
            for action in actions:
                result = action_results.get(action.get("action_id"), {})
                st.markdown(
                    f"- `{action.get('action_id')}` {action.get('action_type')}："
                    f"{action.get('target_name') or action.get('intent_id') or '-'}"
                    f"（{result.get('status', '未执行')}，文档 {result.get('documents', 0)} 条）"
                )
        if evaluation:
            covered = evaluation.get("covered_information_needs") or []
            missing = evaluation.get("missing_information_needs") or []
            st.markdown(f"**检索评估：** {evaluation.get('reason_summary') or evaluation.get('status') or '未提供'}")
            if covered:
                st.caption("已覆盖：" + "、".join(covered))
            if missing:
                st.caption("仍缺：" + "、".join(missing))
        _render_retrieved_documents(trace.get("documents") or [])
        _render_trace_performance(trace)
        return

    if "tasks" in trace:
        columns = st.columns(3)
        columns[0].metric("业务身份", trace.get("business_type", "-"))
        columns[1].metric("任务数量", len(trace.get("tasks") or []))
        columns[2].metric("风险等级", trace.get("risk_level", "-"))
        st.caption(
            f"内部推理：{'开启' if trace.get('reasoning_required') else '关闭'} · "
            f"可处理：{'是' if trace.get('can_handle') else '否'} · "
            f"置信度：{trace.get('confidence', 0):.2f}"
        )
        st.markdown(f"**总体目标：** {trace.get('user_goal') or '未提供'}")
        st.markdown(f"**决策摘要：** {trace.get('reason_summary') or '未提供'}")
        task_results = trace.get("task_results") or {}
        st.markdown("**任务与执行结果**")
        for task in trace.get("tasks") or []:
            result = task_results.get(task.get("task_id"), {})
            target = task.get("tool_name") or ", ".join(task.get("knowledge_bases") or [])
            st.markdown(
                f"- `{task.get('task_id')}` {task.get('task_type')}："
                f"{task.get('goal') or '-'}"
                f"{' → ' + target if target else ''}"
                f"（{result.get('status', '未执行')}）"
            )
        missing = trace.get("missing_information") or []
        if missing:
            st.warning("缺少信息：" + "、".join(missing))
        _render_retrieved_documents(trace.get("documents") or [])
        _render_trace_performance(trace)
        return

    intent_labels = {
        "chat": "普通聊天",
        "knowledge": "知识问题",
        "ambiguous": "意图不明确",
    }
    relevance_labels = {
        "answerable": "资料足以回答",
        "insufficient": "资料不足",
        "ambiguous": "相关性不明确",
        "not_applicable": "无需检索",
    }
    route_label = "普通聊天" if trace.get("route") == "chat" else "知识库检索"
    columns = st.columns(3)
    columns[0].metric("意图识别", intent_labels.get(trace.get("intent"), trace.get("intent", "-")))
    columns[1].metric("处理路径", route_label)
    columns[2].metric(
        "资料判断",
        relevance_labels.get(trace.get("relevance"), trace.get("relevance", "-")),
    )
    retrieval_complexity = trace.get("retrieval_complexity", trace.get("complexity"))
    st.caption(
        f"检索复杂度：{'复杂' if retrieval_complexity == 'complex' else '简单'} · "
        f"生成思考：{'开启' if trace.get('reasoning_required') else '关闭'}"
    )
    if trace.get("route") == "knowledge_base":
        st.caption(
            f"检索模式：{'BGE-M3 Dense + Sparse 混合检索' if trace.get('hybrid_search_enabled') else 'Dense 向量检索'} · "
            f"{'Multi Query 多查询召回' if trace.get('multi_query_enabled') else '单查询召回'}"
        )
        retrieval_channels = trace.get("retrieval_channels") or {}
        st.caption(
            f"通道候选：Dense {retrieval_channels.get('dense', 0)} 条 · "
            f"Sparse {retrieval_channels.get('sparse', 0)} 条"
        )
        if trace.get("query_rewritten"):
            st.markdown(f"**原始问题：** {trace.get('original_query') or '未提供'}")
            st.markdown(f"**检索改写：** {trace.get('retrieval_query') or '未提供'}")
        expanded_queries = trace.get("expanded_queries") or []
        if expanded_queries:
            st.markdown("**Multi Query 扩展问题：**")
            for expanded_query in expanded_queries:
                st.markdown(f"- {expanded_query}")
    st.markdown(f"**意图依据：** {trace.get('intent_reason') or '未提供'}")
    st.markdown(f"**相关性依据：** {trace.get('relevance_reason') or '未提供'}")
    relevance_method_labels = {
        "no_documents": "没有召回文档",
        "reranker_high_threshold": "Reranker 高阈值直接放行",
        "reranker_low_threshold": "Reranker 低阈值直接拒绝",
        "llm_judge": "边界结果，调用 LLM Judge",
        "not_applicable": "无需判断",
    }
    st.caption(
        f"相关性判定方式：{relevance_method_labels.get(trace.get('relevance_method'), trace.get('relevance_method', '-'))}"
        + (
            f" · 最高重排分数：{trace['top_rerank_score']:.4f}"
            if isinstance(trace.get("top_rerank_score"), (int, float))
            else ""
        )
    )
    if trace.get("route") == "knowledge_base":
        st.caption(
            f"向量相似度阈值：{trace.get('vector_threshold')} · "
            f"初筛召回：{trace.get('retrieved_count', 0)} 条"
        )
        documents = trace.get("documents") or []
        if not documents:
            st.info("没有检索资料通过相关性判断，本次回答未采用知识库文档。")
        else:
            _render_retrieved_documents(documents)
    _render_trace_performance(trace)


def web():

    from rag.common.configuration import settings
    from server.user_rights_ui import (
        require_current_consent,
        show_data_controls,
        show_feedback_form,
        show_legal_documents,
    )
    from rag.connector.database.repository.user_rights_repository import (
        set_personalization_enabled,
    )

    try:
        principal = resolve_principal()
    except Exception as exc:
        st.error(f"身份认证失败：{getattr(exc, 'detail', str(exc))}")
        st.stop()
    user_id = principal.user_id
    account_is_admin = principal.has_any_role({"admin"})
    is_admin = account_is_admin and st.session_state.get(
        "admin_view_mode", "普通用户"
    ) == "管理员"
    can_manage_knowledge = is_admin
    require_current_consent(user_id)

    pending_preference = st.session_state.pop("pending_personalization_enabled", None)
    if pending_preference is not None:
        set_personalization_enabled(user_id, bool(pending_preference))

    # if st.session_state.get("underage_mode_confirmed"):
    #     st.warning(
    #         "未成年人模式已开启：个性化推荐、医美项目推荐和消费引导功能已关闭。",
    #         icon="🛡️",
    #     )

    base_url = settings.server.get_api_base_url()
    api = None

    is_service_up, health_error = check_api_health(base_url)
    if is_service_up:
        api = ApiRequest(
            base_url=base_url,
            access_token=st.session_state[AUTH_TOKEN_KEY],
        )
    else:
        st.error(f"无法连接 API Server：{base_url}（{health_error}）")

    if api is None:
        st.stop()

    ########################################################
    # Knowledge Base
    ########################################################
    from rag.connector.database.repository.knowledge_file_repository import delete_files_from_db, list_files_from_db
    from rag.connector.database.repository.knowledge_base_repository import list_kbs_from_db
    from rag.connector.database.repository.chat_history_repository import (
        create_chat_session,
        get_chat_session,
        list_chat_messages,
        list_chat_sessions,
        save_chat_message,
        update_chat_session_knowledge_base,
    )

    knowledge_base_list = list_kbs_from_db()[::-1]

    st.markdown(
        """
        <style>
        /* Reserve space for Streamlit's sticky chat input so long answers and
           expanded decision traces do not scroll underneath it. */
        [data-testid="stAppViewBlockContainer"] {
            padding-bottom: 9rem;
        }
        /* Keep long-form answers at a comfortable reading width, consistent
           with familiar AI chat products on wide desktop displays. */
        [data-testid="stMainBlockContainer"] {
            max-width: 980px;
            padding-top: 2.25rem;
        }
        [data-testid="stBottom"] {
            z-index: 1000;
            background: var(--background-color, white);
        }
        .retrieved-chunk-text {
            margin: 0;
            color: inherit;
            font-family: inherit;
            font-size: 1rem;
            font-weight: 400;
            line-height: 1.65;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }
        .knowledge-source-item {
            padding: .45rem 0;
            border-bottom: 1px solid rgba(49, 51, 63, .1);
            font-size: .78rem;
            line-height: 1.45;
        }
        .knowledge-source-item:last-child {
            border-bottom: 0;
        }
        .knowledge-source-title {
            font-weight: 600;
        }
        .knowledge-source-meta {
            margin-top: .12rem;
            color: rgba(49, 51, 63, .62);
        }
        .knowledge-source-excerpt {
            margin-top: .3rem;
            color: rgba(49, 51, 63, .82);
        }
        /* Production-style utility links anchored to the bottom of the
           navigation rail, separate from the primary knowledge-base actions. */
        section[data-testid="stSidebar"] > div {
            position: relative;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] {
            border-radius: .65rem;
            padding: .12rem .2rem;
            margin-bottom: .2rem;
            transition: background-color .15s ease;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_active_"] {
            background: rgba(255, 75, 75, .09);
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"]:hover {
            background: rgba(49, 51, 63, .065);
        }
        /* The row's regular button is the conversation title. The management
           trigger is a Popover and is styled separately below. */
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stButton"] {
            opacity: 1 !important;
            visibility: visible !important;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stButton"] button {
            width: 100%;
            min-height: 2.25rem;
            padding: .35rem .55rem;
            justify-content: flex-start;
            text-align: left;
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            color: inherit !important;
            font-size: .92rem;
            font-weight: 400;
            min-width: 0;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stButton"] button p {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            margin: 0;
            width: 100%;
            text-align: left;
        }
        /* Only the actual popover trigger is hidden until its row is hovered. */
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stPopover"] {
            opacity: 0;
            pointer-events: none;
            transition: opacity .15s ease;
            flex-shrink: 0;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"]:hover [data-testid="stPopover"],
        .st-key-conversation_list [class*="st-key-conversation_row_"]:focus-within [data-testid="stPopover"] {
            opacity: 1;
            pointer-events: auto;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stPopover"] > button {
            width: 2rem;
            min-width: 2rem;
            min-height: 2rem;
            padding: 0;
            border: 0 !important;
            border-radius: 0;
            background: transparent !important;
            box-shadow: none !important;
            color: rgba(49, 51, 63, .62);
            font-size: 1.1rem;
            justify-content: center;
            gap: 0 !important;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stPopover"] > button:hover {
            background: transparent !important;
            box-shadow: none !important;
            color: rgba(49, 51, 63, 1);
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stPopover"] > button p {
            text-align: center;
            width: 100%;
            white-space: nowrap;
            line-height: 1;
        }
        .st-key-conversation_list [class*="st-key-conversation_row_"] [data-testid="stPopover"] button svg {
            display: none !important;
        }
        div[data-testid="stPopoverBody"] {
            min-width: 10rem;
            padding: .45rem;
            border: 1px solid rgba(49, 51, 63, .1);
            border-radius: .75rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, .14);
        }
        div[data-testid="stPopoverBody"] [data-testid="stButton"] button {
            width: 100%;
            justify-content: flex-start;
            text-align: left;
        }
        div[data-testid="stPopoverBody"] [data-testid="stButton"] button p {
            width: 100%;
            text-align: left;
        }
        /* Final widget-key overrides: Streamlit may insert wrapper elements
           between containers and buttons, so these do not depend on DOM depth. */
        [class*="st-key-open_chat_session_"] button {
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [class*="st-key-open_chat_session_"] button p {
            width: 100% !important;
            text-align: left !important;
        }
        .st-key-conversation_list [data-testid="stPopover"] button {
            border: 0 !important;
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
        }
        .st-key-conversation_list [data-testid="stPopover"] button svg,
        .st-key-conversation_list [data-testid="stPopover"] button [data-testid="stIconMaterial"] {
            display: none !important;
        }
        [class*="st-key-rename_chat_session_"] button,
        [class*="st-key-delete_chat_session_"] button {
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [class*="st-key-rename_chat_session_"] button p,
        [class*="st-key-delete_chat_session_"] button p {
            width: 100% !important;
            text-align: left !important;
        }
        /* Center text in rename/delete dialogs */
        div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] p,
        div[data-testid="stDialog"] [data-testid="stTextInput"] input {
            text-align: center;
        }
        div[data-testid="stDialog"] [data-testid="stButton"] button {
            justify-content: center;
            text-align: center;
        }
        div[data-testid="stDialog"] [data-testid="stButton"] button p {
            text-align: center;
            width: 100%;
        }
        .st-key-rights_footer {
            position: sticky;
            bottom: 0;
            width: calc(100% + 3rem);
            z-index: 1001;
            box-sizing: border-box;
            padding: .75rem 1.5rem 1rem;
            margin: .75rem 0 -1rem -1.5rem;
            background: rgb(240, 242, 246);
        }
        @media (prefers-color-scheme: dark) {
            .st-key-rights_footer {
                background: rgb(38, 39, 48);
            }
        }
        .st-key-rights_footer button {
            min-height: 2rem;
            padding: .2rem .45rem;
            justify-content: flex-start;
            border: 0 !important;
            outline: 0 !important;
            background: transparent !important;
            color: rgba(49, 51, 63, .72);
            font-weight: 400;
            box-shadow: none !important;
        }
        .st-key-rights_footer button:hover {
            background: transparent !important;
            color: rgba(49, 51, 63, 1);
        }
        .st-key-rights_footer button:focus,
        .st-key-rights_footer button:focus-visible {
            border: 0 !important;
            outline: 0 !important;
            box-shadow: none !important;
        }
        /* Sidebar actions must remain readable on narrow screens. Chinese text
           otherwise wraps one character per line inside Streamlit columns. */
        section[data-testid="stSidebar"] button p,
        section[data-testid="stSidebar"] [data-testid="stPageLink"] p {
            white-space: nowrap !important;
            word-break: keep-all !important;
        }
        .st-key-kb_file_pagination button {
            min-width: 0 !important;
            padding: .3rem .35rem !important;
        }
        .st-key-kb_file_pagination button p {
            font-size: .8rem !important;
        }
        .kb-file-page-number {
            padding-top: .45rem;
            text-align: center;
            color: rgba(49, 51, 63, .62);
            font-size: .78rem;
            white-space: nowrap;
        }
        [class*="st-key-kb_file_row_"] {
            padding: .15rem .25rem;
            border-radius: .5rem;
        }
        [class*="st-key-kb_file_row_"]:hover {
            background: rgba(49, 51, 63, .06);
        }
        .kb-file-name {
            overflow: hidden;
            padding: .35rem .15rem;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: .86rem;
        }
        [class*="st-key-kb_file_row_"] [data-testid="stButton"] {
            opacity: 0;
            transition: opacity .15s ease;
        }
        [class*="st-key-kb_file_row_"]:hover [data-testid="stButton"],
        [class*="st-key-kb_file_row_"]:focus-within [data-testid="stButton"] {
            opacity: 1;
        }
        [class*="st-key-kb_file_row_"] button {
            min-width: 2rem !important;
            padding: .25rem !important;
            border: 0 !important;
        }
        @media (hover: none) {
            [class*="st-key-kb_file_row_"] [data-testid="stButton"] {
                opacity: 1;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with (st.sidebar):
        st.subheader("AISIA美容助理")
        st.caption("AI生成内容仅供参考，请结合自身情况谨慎选择。")

        if account_is_admin:
            view_mode = st.segmented_control(
                "使用模式",
                options=("普通用户", "管理员"),
                default=st.session_state.get("admin_view_mode", "普通用户"),
                key="admin_view_mode_selector",
                width="stretch",
            )
            selected_view_mode = view_mode or "普通用户"
            if selected_view_mode != st.session_state.get("admin_view_mode"):
                st.session_state["admin_view_mode"] = selected_view_mode
                st.rerun()
            is_admin = selected_view_mode == "管理员"
            can_manage_knowledge = is_admin

        business_type_labels = {
            "customer": "客户",
            "advisor": "导购",
            "doctor": "医生",
        }
        available_business_types = list(
            business_registry.names()
            if account_is_admin and not is_admin
            else sorted(principal.business_types)
        )
        if is_admin:
            st.text_input(
                "当前管理身份",
                value="管理员（全库管理）",
                disabled=True,
                help="管理员模式用于管理全部知识库；切换到普通用户模式可检查各业务身份的实际权限。",
            )
            active_business_type = st.selectbox(
                "回答身份",
                list(business_registry.names()),
                format_func=lambda value: business_type_labels.get(value, value),
                key="admin_active_business_type",
                help="管理员可选择客户、导购或医生的回答策略测试当前知识库。",
            )
        else:
            active_business_type = available_business_types[0]
            st.text_input(
                "当前业务身份",
                value=business_type_labels.get(active_business_type, active_business_type),
                disabled=True,
                help="业务身份在注册时确定，决定可使用的知识库、工具和回答策略。",
            )
        previous_business_type = st.session_state.get("conversation_business_type")
        if previous_business_type and previous_business_type != active_business_type:
            # Do not carry a doctor's or advisor's conversation into another
            # identity context. A fresh session also prevents accidental data
            # disclosure through cross-identity history.
            st.session_state.pop("current_chat_session_id", None)
        st.session_state["conversation_business_type"] = active_business_type

        business_config = business_registry.get(active_business_type)
        authorized_knowledge_bases = list(
            business_registry.filter_knowledge_bases(
                business_config,
                knowledge_base_list,
            )
        )
        configured_default_kb = settings.server.default_knowledge_base.strip()
        selectable_knowledge_bases = (
            knowledge_base_list if is_admin else authorized_knowledge_bases
        )
        selected_kb = (
            configured_default_kb
            if configured_default_kb in selectable_knowledge_bases
            else (selectable_knowledge_bases[0] if selectable_knowledge_bases else None)
        )
        show_reasoning = False
        if is_admin:
            if (
                "selected_kb_name" in st.session_state
                and st.session_state["selected_kb_name"] in knowledge_base_list
            ):
                selected_kb_index = knowledge_base_list.index(
                    st.session_state["selected_kb_name"]
                )
            else:
                selected_kb_index = 0

            selected_kb = st.selectbox(
                "请选择或新建知识库：",
                knowledge_base_list + ["新建知识库"],
                index=selected_kb_index,
            )
            show_reasoning = st.checkbox(
                "显示判断过程",
                value=False,
                help="展示意图分类、检索路由和资料相关性结论，不展示模型内部思维链。",
            )
        elif active_business_type == "customer" and "weijing_knowledge" in authorized_knowledge_bases:
            selected_kb = "weijing_knowledge"
            st.text_input(
                "当前知识库",
                value="微晶知识库",
                disabled=True,
            )
            st.session_state["selected_kb_name"] = selected_kb
        elif authorized_knowledge_bases:
            previous_kb = st.session_state.get("selected_kb_name")
            selected_kb = st.selectbox(
                "当前知识库",
                authorized_knowledge_bases,
                index=(
                    authorized_knowledge_bases.index(previous_kb)
                    if previous_kb in authorized_knowledge_bases
                    else 0
                ),
                key=f"authorized_kb_selector_{active_business_type}",
                help="这里只显示当前业务身份已获授权的知识库，可在授权范围内切换。",
            )
            st.session_state["selected_kb_name"] = selected_kb
        else:
            st.warning("当前业务身份尚未获授权使用任何已有知识库，请联系管理员配置。")

        st.subheader("会话历史")
        chat_sessions = list_chat_sessions(user_id)
        current_session_id = st.session_state.get("current_chat_session_id")
        if not current_session_id or not get_chat_session(current_session_id, user_id):
            if chat_sessions:
                current_session_id = chat_sessions[0]["session_id"]
            else:
                current_session_id = create_chat_session(
                    user_id,
                    selected_kb if selected_kb in knowledge_base_list else None,
                )["session_id"]
            st.session_state["current_chat_session_id"] = current_session_id

        if st.button(
            "＋ 新建对话",
            type="primary",
            use_container_width=True,
        ):
            current_session_id = create_chat_session(
                user_id,
                selected_kb if selected_kb in knowledge_base_list else None,
            )["session_id"]
            st.session_state["current_chat_session_id"] = current_session_id
            st.rerun()

        chat_sessions = list_chat_sessions(user_id)
        st.caption("最近对话")
        with st.container(key="conversation_list"):
            for chat_session in chat_sessions[:20]:
                session_id = chat_session["session_id"]
                session_title = chat_session.get("title") or "新对话"
                safe_session_key = session_id.replace("-", "_")
                row_state = (
                    "active_" if session_id == current_session_id else ""
                )
                with st.container(
                    key=f"conversation_row_{row_state}{safe_session_key}"
                ):
                    title_column, menu_column = st.columns(
                        [10, 1], gap="small", vertical_alignment="center"
                    )
                    if title_column.button(
                        session_title,
                        key=f"open_chat_session_{safe_session_key}",
                        type="tertiary",
                        use_container_width=True,
                        help=session_title,
                    ):
                        st.session_state["current_chat_session_id"] = session_id
                        st.rerun()

                    with menu_column.popover(
                        "⋯",
                        help=f"管理「{session_title}」",
                        use_container_width=True,
                    ):
                        if st.button(
                            "✎  重命名",
                            key=f"rename_chat_session_{safe_session_key}",
                            type="tertiary",
                            use_container_width=True,
                        ):
                            st.session_state["conversation_dialog"] = {
                                "action": "rename",
                                "session_id": session_id,
                                "title": session_title,
                            }
                            st.rerun()
                        if st.button(
                            "🗑  删除",
                            key=f"delete_chat_session_{safe_session_key}",
                            type="tertiary",
                            use_container_width=True,
                        ):
                            st.session_state["conversation_dialog"] = {
                                "action": "delete",
                                "session_id": session_id,
                                "title": session_title,
                            }
                            st.rerun()

        if selected_kb == "新建知识库" and can_manage_knowledge:
            with st.form("create_kb", clear_on_submit=True, border=False):
                kb_name = st.text_input(
                    "请输入知识库名称：",
                    placeholder="新知识库名称，不支持中文命名",
                    key="kb_name",
                )
                submit_create_kb = st.form_submit_button("新      建", use_container_width=True)

            if submit_create_kb:
                if not kb_name or not kb_name.strip():
                    st.error(f"知识库名称不能为空！")
                elif kb_name in knowledge_base_list:
                    st.error(f"名为 {kb_name} 的知识库已经存在！")
                else:
                    resp = api.create_knowledge_base(
                        knowledge_base_name=kb_name,
                        vector_store_type=VECTOR_STORE_TYPE
                    )
                    if resp.get("code") == 200:
                        st.rerun()
                    else:
                        st.error(f"知识库 {kb_name} 创建失败")

        elif selected_kb and is_admin:
            uploaded_files = []
            submitted = False
            if can_manage_knowledge:
                with st.form("上传文件到知识库", clear_on_submit=True):
                    st.subheader("上传文件到知识库")
                    uploaded_files = st.file_uploader("", accept_multiple_files=True)
                    submitted = st.form_submit_button("上传")

            exist_files = [os.path.basename(f) for f in list_files_from_db(selected_kb)]

            if uploaded_files and submitted:
                st.info(f"正在上传 {len(uploaded_files)} 个文件到知识库 {selected_kb}")
                resp = api.upload_kb_docs(uploaded_files, selected_kb)

                code = resp.get("code")
                if code == 200:
                    failed_files = (resp.get("data") or {}).get("failed_files", {})
                    if failed_files:
                        for f in failed_files: print(f, failed_files[f])
                        msg = "下列文件上传失败: " + "\n".join([os.path.basename(f_name) for f_name in list(failed_files.keys())])
                        st.error(msg)
                    else:
                        st.success(f"所有文件上传成功!")
                        st.rerun()
                else:
                    st.error(resp.get("msg") or "文件上传失败！")

            st.subheader("文件管理")
            if exist_files:
                page_size = 20
                page_count = (len(exist_files) + page_size - 1) // page_size
                page_key = f"kb_file_page_{selected_kb}"
                current_page = min(
                    max(int(st.session_state.get(page_key, 1)), 1),
                    page_count,
                )
                page_start = (current_page - 1) * page_size
                visible_files = exist_files[page_start:page_start + page_size]
                st.caption(f"共 {len(exist_files)} 个文件，每页 {page_size} 个")
                for row_index, file_name in enumerate(visible_files):
                    absolute_index = page_start + row_index
                    with st.container(
                        key=f"kb_file_row_{selected_kb}_{absolute_index}"
                    ):
                        name_column, action_column = st.columns(
                            [8, 1], gap="small", vertical_alignment="center"
                        )
                        safe_file_name = html.escape(file_name, quote=True)
                        name_column.markdown(
                            f'<div class="kb-file-name" title="{safe_file_name}">'
                            f'{safe_file_name}</div>',
                            unsafe_allow_html=True,
                        )
                        if action_column.button(
                            "×",
                            key=f"request_delete_kb_file_{selected_kb}_{absolute_index}",
                            help=f"删除 {file_name}",
                        ):
                            st.session_state["pending_kb_file_delete"] = {
                                "knowledge_base": selected_kb,
                                "file_name": file_name,
                            }
                            st.rerun()

                with st.container(key="kb_file_pagination"):
                    previous_col, page_col, next_col = st.columns(
                        [1.25, 1, 1.25], vertical_alignment="center"
                    )
                    if previous_col.button(
                        "← 上页",
                        key=f"previous_kb_file_page_{selected_kb}",
                        disabled=current_page == 1,
                        use_container_width=True,
                    ):
                        st.session_state[page_key] = current_page - 1
                        st.rerun()
                    page_col.markdown(
                        f'<div class="kb-file-page-number">{current_page}/{page_count}</div>',
                        unsafe_allow_html=True,
                    )
                    if next_col.button(
                        "下页 →",
                        key=f"next_kb_file_page_{selected_kb}",
                        disabled=current_page == page_count,
                        use_container_width=True,
                    ):
                        st.session_state[page_key] = current_page + 1
                        st.rerun()

            else:
                st.caption("当前知识库为空")

            st.subheader("知识库设置")
            with st.expander("重命名知识库"):
                with st.form(f"rename_kb_{selected_kb}"):
                    renamed_kb = st.text_input(
                        "新名称",
                        value=selected_kb,
                        help="名称支持中文、字母、数字、下划线和连字符。",
                    )
                    submit_rename_kb = st.form_submit_button(
                        "保存新名称", use_container_width=True
                    )
                if submit_rename_kb:
                    response = api.rename_knowledge_base(selected_kb, renamed_kb.strip())
                    if response.get("code") == 200:
                        st.session_state["selected_kb_name"] = renamed_kb.strip()
                        st.success(response.get("msg"))
                        st.rerun()
                    else:
                        st.error(response.get("msg") or "知识库重命名失败")

            with st.expander("删除或清空知识库"):
                st.caption("清空会保留知识库；删除会移除知识库及其中全部文件。")
                confirm_clear = st.checkbox(
                    "确认清空全部文件", key=f"confirm_clear_kb_{selected_kb}"
                )
                if st.button(
                    "清空知识库",
                    key=f"clear_kb_{selected_kb}",
                    disabled=not confirm_clear,
                    use_container_width=True,
                ):
                    response = api.clear_knowledge_base(selected_kb)
                    if response.get("code") == 200:
                        st.rerun()
                    st.error(response.get("msg") or "清空知识库失败")
                confirm_delete = st.checkbox(
                    f"确认永久删除“{selected_kb}”",
                    key=f"confirm_delete_kb_{selected_kb}",
                )
                if st.button(
                    "删除知识库",
                    key=f"delete_kb_{selected_kb}",
                    disabled=not confirm_delete,
                    type="primary",
                    use_container_width=True,
                ):
                    response = api.delete_knowledge_base(selected_kb)
                    if response.get("code") == 200:
                        st.session_state.pop("selected_kb_name", None)
                        st.rerun()
                    st.error(response.get("msg") or "删除知识库失败")

        if is_admin:
            st.page_link(
                "pages/1_Indexing_Inspector.py",
                label="索引诊断",
                icon=":material/troubleshoot:",
            )
            st.page_link(
                "pages/2_Notion_Sync.py",
                label="Notion 同步",
                icon=":material/sync:",
            )

        with st.container(key="rights_footer"):
            profile = st.session_state.get(AUTH_PROFILE_KEY)
            if profile:
                if st.button(
                    "退出登录",
                    key="logout_current_user",
                    type="tertiary",
                    use_container_width=True,
                ):
                    clear_external_login()
                    st.rerun()
            with st.popover("ⓘ  关于AISIA平台", use_container_width=True):
                st.markdown("**美容知识问答**")
                st.caption("美容知识咨询服务")
                if st.button("用户协议与隐私政策", key="open_legal_documents",
                             use_container_width=True):
                    show_legal_documents()
                if st.button("投诉、举报与反馈", key="open_feedback_form",
                             use_container_width=True):
                    show_feedback_form(
                        user_id, st.session_state.get("current_chat_session_id")
                    )
                if st.button("个人数据管理", key="open_data_controls",
                             use_container_width=True):
                    show_data_controls(user_id)
                st.caption("AI 生成内容仅供参考，请谨慎判断。")

    pending_file_delete = st.session_state.get("pending_kb_file_delete")
    if pending_file_delete:
        show_delete_kb_file_dialog(
            api,
            pending_file_delete["knowledge_base"],
            pending_file_delete["file_name"],
        )

    conversation_dialog = st.session_state.get("conversation_dialog")
    if conversation_dialog:
        dialog_session_id = conversation_dialog.get("session_id")
        owned_dialog_session = get_chat_session(dialog_session_id, user_id)
        if owned_dialog_session is None:
            st.session_state.pop("conversation_dialog", None)
        elif conversation_dialog.get("action") == "rename":
            show_rename_chat_dialog(
                dialog_session_id,
                user_id,
                owned_dialog_session.get("title") or "新对话",
            )
        elif conversation_dialog.get("action") == "delete":
            show_delete_chat_dialog(
                dialog_session_id,
                user_id,
                selected_kb,
                knowledge_base_list,
            )

    ########################################################
    # LLM Response Generation and Chat
    ########################################################
    # st.info("AI 回答可能存在遗漏或错误，请结合资料来源审慎判断。")
    messages = list_chat_messages(current_session_id, user_id)
    for message in messages:
        with st.chat_message(message["role"]):
            message_trace = message.get("decision_trace") or {}
            if (
                message["role"] == "assistant"
                and message_trace.get("message_kind") == "weijing_assessment"
            ):
                with st.container(border=True):
                    st.caption("检测报告分析与微晶改善方案")
                    st.markdown(message["context"])
            else:
                st.markdown(message["context"])
            if message["role"] == "assistant" and is_admin:
                _relevance = message_trace.get("relevance_score")
                if isinstance(_relevance, (int, float)):
                    _pct = max(0, min(100, round(_relevance * 100)))
                    st.caption(f"📖 本次回答相关度：{_pct}%")
            if (
                message["role"] == "assistant"
                and message_trace.get("business_type") in {"advisor", "doctor"}
            ):
                render_knowledge_sources(message.get("source_documents") or [])
            if show_reasoning and message.get("decision_trace"):
                with st.expander("判断过程", expanded=False):
                    render_decision_trace(message["decision_trace"])

    with st.expander("上传检测报告", expanded=False):
        uploaded_report = st.file_uploader(
            "PDF 或 DOCX 检测报告",
            type=["pdf", "docx"],
            accept_multiple_files=False,
            key=f"weijing_report_{current_session_id}",
        )
        report_bytes = uploaded_report.getvalue() if uploaded_report else b""
        report_digest = hashlib.sha256(report_bytes).hexdigest() if report_bytes else ""
        submission_key = f"{current_session_id}:{report_digest}"
        already_submitted = (
            report_digest
            and st.session_state.get("last_weijing_report_submission") == submission_key
        )
        if st.button(
            "生成微晶改善方案",
            type="primary",
            use_container_width=True,
            disabled=not uploaded_report or bool(already_submitted),
        ):
            try:
                with st.spinner("正在解析报告并生成方案…"):
                    assessment = api.assess_weijing_report(uploaded_report, current_session_id)
                previous_message_id = messages[-1]["message_id"] if messages else None
                user_message = save_chat_message(
                    session_id=current_session_id,
                    user_id=user_id,
                    role="user",
                    content=f"已上传检测报告：{os.path.basename(uploaded_report.name)}",
                    parent_message_id=previous_message_id,
                )
                save_chat_message(
                    session_id=current_session_id,
                    user_id=user_id,
                    role="assistant",
                    content=assessment["rendered_markdown"],
                    parent_message_id=user_message["message_id"],
                    decision_trace={
                        "message_kind": "weijing_assessment",
                        "assessment_id": assessment["assessment_id"],
                        "report_id": assessment["report"]["report_id"],
                        "knowledge_base": "weijing_knowledge",
                        "knowledge_version": assessment["plan"]["knowledge_version"],
                    },
                )
                st.session_state["last_weijing_report_submission"] = submission_key
                st.rerun()
            except Exception as exc:
                st.error(f"检测报告处理失败：{exc}")

    # Read the submitted value directly. Streamlit already reruns the script
    # after a chat submission, so copying the widget value through a callback
    # and a second session-state key only adds another state transition.
    prompt = st.chat_input("可以继续询问报告、评分或改善方案")
    if prompt:
        chat_kb = "weijing_knowledge" if active_business_type == "customer" else selected_kb
        if chat_kb not in selectable_knowledge_bases:
            st.error("对话前请选择一个知识库！")
        else:
            st.chat_message("user").markdown(prompt)                                # 显示用户消息
            update_chat_session_knowledge_base(current_session_id, user_id, chat_kb)
            previous_message_id = messages[-1]["message_id"] if messages else None
            user_message = save_chat_message(
                session_id=current_session_id,
                user_id=user_id,
                role="user",
                content=prompt,
                parent_message_id=previous_message_id,
            )

            with st.chat_message("assistant"):  # 显示机器人回复
                message_placeholder = st.empty()
                full_response = ""
                decision_trace = None
                generation_error = None
                trace_id = None
                last_render_at = 0.0
                history = [
                    (message["role"], message["context"])
                    for message in messages
                    if message.get("status") == "complete"
                ]
                for event in api.knowledge_base_chat(
                    prompt,
                    knowledge_base_names=[chat_kb],
                    session_id=current_session_id,
                    business_type=active_business_type,
                    history=history,
                    return_docs=business_config.show_sources,
                    show_reasoning=show_reasoning,
                    return_details=True,
                ):
                    event_type = event.get("type")
                    trace_id = event.get("request_id", trace_id)
                    if event_type == "trace":
                        decision_trace = event.get("decision_trace", decision_trace)
                    elif event_type == "delta":
                        full_response += event.get("delta", "")
                        # Rendering every token forces the old Streamlit React
                        # frontend to reconcile the complete Markdown tree at a
                        # very high frequency. Cap UI refreshes at 20 FPS while
                        # still collecting every response fragment.
                        now = time.monotonic()
                        if now - last_render_at >= 0.05:
                            message_placeholder.markdown(full_response + "▌")
                            last_render_at = now
                    elif event_type == "done":
                        full_response = event.get("result", full_response)
                        if decision_trace is not None:
                            decision_trace["performance"] = event.get(
                                "performance",
                                decision_trace.get("performance", {}),
                            )
                    elif event_type == "error":
                        generation_error = event.get("message") or "模型服务调用失败，请稍后重试。"
                if generation_error:
                    message_placeholder.error(generation_error)
                else:
                    message_placeholder.markdown(full_response)
                    if is_admin:
                        _relevance = decision_trace.get("relevance_score")
                        if isinstance(_relevance, (int, float)):
                            _pct = max(0, min(100, round(_relevance * 100)))
                            st.caption(f"📖 本次回答相关度：{_pct}%")
                    if business_config.show_sources and decision_trace:
                        render_knowledge_sources(
                            decision_trace.get("documents") or []
                        )
                if show_reasoning and decision_trace:
                    with st.expander("判断过程", expanded=True):
                        render_decision_trace(decision_trace)
            save_chat_message(
                session_id=current_session_id,
                user_id=user_id,
                role="assistant",
                content=generation_error or full_response,
                parent_message_id=user_message["message_id"],
                trace_id=trace_id,
                status="error" if generation_error else "complete",
                source_documents=(decision_trace or {}).get("documents", []),
                decision_trace=decision_trace or {},
            )


def underage_mode(chat_page):
    """Public, reviewable simulation of the product's underage mode."""
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            width: min(92vw, 760px);
            max-width: 760px;
            padding-top: clamp(2.5rem, 8vh, 6rem);
        }
        .underage-badge {
            display: inline-block;
            margin-bottom: 1rem;
            padding: .3rem .75rem;
            border-radius: 999px;
            color: #1f6f43;
            background: #e7f6ed;
            font-size: .9rem;
            font-weight: 600;
        }
        </style>
        <span class="underage-badge">未成年人模式</span>
        """,
        unsafe_allow_html=True,
    )
    st.title("未成年人模式")
    st.write("为保护未成年人的身心健康，本模式仅提供适龄、审慎的美容健康常识。")

    # with st.container(border=True):
    #     st.subheader("模式限制")
    #     st.markdown(
    #         """
    #         - 不提供医美项目推荐、效果承诺或消费引导
    #         - 不根据外貌、身材等信息进行评价或个性化推荐
    #         - 不展示可能引发容貌焦虑的内容
    #         - 涉及皮肤疾病、用药或治疗的问题，建议由监护人陪同咨询正规医疗机构
    #         """
    #     )

    st.info("未成年人使用网络服务应征得监护人同意，并建议在监护人陪同下使用。")
    guardian_confirmed = st.checkbox("我已阅读上述提示，并在监护人知情的情况下体验")
    if st.button(
        "进入未成年人模式",
        type="primary",
        disabled=not guardian_confirmed,
        use_container_width=True,
    ):
        st.session_state["underage_mode_confirmed"] = True
        st.switch_page(chat_page)

    if st.session_state.get("underage_mode_confirmed"):
        st.warning("当前处于未成年人模式：个性化推荐和消费引导功能已关闭。")
    st.caption("如需退出，请关闭本页面或返回网站首页。")


def personalization_settings(chat_page):
    """Public entry for choosing whether personalized recommendations are used."""
    from rag.connector.database.repository.user_rights_repository import (
        personalization_enabled,
        set_personalization_enabled,
    )

    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            width: min(92vw, 720px);
            max-width: 720px;
            padding-top: clamp(3rem, 9vh, 7rem);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("个性化推荐设置")
    st.write("你可以自主决定是否允许系统在后续提供个性化产品推荐。")
    st.info(
        "当前版本仅提供个性化推荐的设置入口，尚未启用产品推荐功能。"
        "你的选择不会影响正常问答和知识库检索。"
    )

    principal = None
    try:
        principal = resolve_principal()
    except Exception:
        pass

    pending_value = st.session_state.get("pending_personalization_enabled")
    if pending_value is not None:
        current_value = bool(pending_value)
    elif principal is not None:
        current_value = personalization_enabled(principal.user_id)
    else:
        current_value = True

    choice = st.radio(
        "个性化推荐",
        ("开启", "关闭"),
        index=0 if current_value else 1,
        horizontal=True,
    )
    if st.button("保存设置", type="primary", use_container_width=True):
        enabled = choice == "开启"
        if principal is not None:
            set_personalization_enabled(principal.user_id, enabled)
            st.session_state.pop("pending_personalization_enabled", None)
        else:
            # Bind the choice to the account after the user signs in.
            st.session_state["pending_personalization_enabled"] = enabled
        if not enabled:
            st.session_state.pop("personalized_suggestion", None)
        st.success(
            "个性化推荐已开启。" if enabled else "个性化推荐已关闭。"
        )

    return_label = "返回聊天" if principal is not None else "返回登录或注册"
    if st.button(return_label, use_container_width=True):
        st.switch_page(chat_page)
    st.caption("设置入口：/personal。你可以随时回来修改选择。")


def render_sms_sender(phone: str, *, prefix: str) -> None:
    """Render the Web-safe captcha step before requesting an SMS code."""
    state_key = f"{prefix}_captcha"
    captcha = st.session_state.get(state_key)
    if st.button("获取 / 刷新图形验证码", key=f"{prefix}_captcha_refresh", use_container_width=True):
        if not PHONE_PATTERN.fullmatch(phone):
            st.error("请输入正确的 11 位大陆手机号。")
        else:
            try:
                captcha = auth_client.captcha(phone)
                captcha["phone"] = phone
                st.session_state[state_key] = captcha
            except AuthServiceError as exc:
                st.error(str(exc))
    if captcha and captcha.get("phone") == phone:
        st.image(captcha["image"], width=180)
        answer = st.text_input("图形验证码", max_chars=4, key=f"{prefix}_captcha_answer")
        if st.button("发送短信验证码", key=f"{prefix}_sms_send", use_container_width=True):
            try:
                auth_client.send_sms(phone, captcha["captcha_id"], answer)
                st.session_state.pop(state_key, None)
                st.success("短信验证码已发送。")
            except AuthServiceError as exc:
                st.error(str(exc))


def render_external_login() -> None:
    """Render conventional sign-in and sign-up account flows."""
    st.markdown(
        '<style>[data-testid="stMainBlockContainer"] '
        "{width:min(92vw,680px);max-width:680px;padding-top:5vh}</style>",
        unsafe_allow_html=True,
    )
    st.title("欢迎使用 AISIA 美容助理")
    login_tab, register_tab = st.tabs(("登录", "注册"))

    with login_tab:
        login_method = st.radio(
            "登录方式", ("密码登录", "验证码登录"), horizontal=True, label_visibility="collapsed"
        )
        if login_method == "密码登录":
            with st.form("password_login_form"):
                phone = st.text_input("手机号", max_chars=11, key="login_phone")
                password = st.text_input("密码", type="password", max_chars=32)
                submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
            if submitted:
                if not PHONE_PATTERN.fullmatch(phone):
                    st.error("请输入正确的 11 位大陆手机号。")
                else:
                    try:
                        complete_external_login(auth_client.password_login(phone, password))
                        st.rerun()
                    except AuthServiceError as exc:
                        st.error(str(exc))
        else:
            phone = st.text_input("手机号", max_chars=11, key="sms_login_phone")
            render_sms_sender(phone, prefix="login")
            with st.form("sms_login_form"):
                code = st.text_input("短信验证码", max_chars=6, key="login_sms_code")
                submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
            if submitted:
                if not PHONE_PATTERN.fullmatch(phone) or not re.fullmatch(r"\d{6}", code):
                    st.error("请输入正确的手机号和 6 位短信验证码。")
                else:
                    try:
                        complete_external_login(auth_client.sms_login(phone, code, False))
                        st.rerun()
                    except AuthServiceError as exc:
                        st.error(str(exc))

    with register_tab:
        phone = st.text_input("手机号", max_chars=11, key="register_phone")
        render_sms_sender(phone, prefix="register")
        with st.form("register_form"):
            code = st.text_input("短信验证码", max_chars=6, key="register_sms_code")
            business_type_labels = {
                "customer": "客户",
                "advisor": "导购",
                "doctor": "医生",
            }
            business_type = st.radio(
                "选择身份",
                list(business_registry.names()),
                format_func=lambda value: business_type_labels[value],
                horizontal=True,
            )
            password = st.text_input("设置密码（8–32 位）", type="password", max_chars=32)
            confirmation = st.text_input("确认密码", type="password", max_chars=32)
            agreed = st.checkbox("我已阅读并同意用户协议与隐私政策", key="register_privacy")
            submitted = st.form_submit_button("注册", type="primary", use_container_width=True)
        if submitted:
            if not agreed:
                st.error("请先阅读并同意用户协议与隐私政策。")
            elif not PHONE_PATTERN.fullmatch(phone) or not re.fullmatch(r"\d{6}", code):
                st.error("请输入正确的手机号和 6 位短信验证码。")
            elif len(password) < 8 or password != confirmation:
                st.error("密码至少 8 位，且两次输入必须一致。")
            else:
                token = ""
                try:
                    token = auth_client.sms_login(phone, code, agreed)
                    auth_client.set_password(token, phone[-6:], password)
                    complete_external_registration(token, business_type)
                    st.rerun()
                except AuthServiceError as exc:
                    if token:
                        try:
                            auth_client.logout(token)
                        except AuthServiceError:
                            pass
                    clear_external_login(notify_server=False)
                    st.error(str(exc))
                    st.info("如果该手机号已经注册，请切换到“登录”。")

    st.caption("登录凭证仅保存在当前浏览器会话中。")
    st.stop()


def authenticated_chat_entry():
    """Render the sign-in screen when needed, then enter the chat product."""
    if not st.session_state.get(AUTH_TOKEN_KEY):
        render_external_login()
    web()


def create_chat_page():
    return st.Page(
        authenticated_chat_entry,
        title="AISIA美容助理",
        icon="✨",
        url_path="chat",
        default=True,
    )


def switch_to_chat() -> None:
    st.switch_page(create_chat_page())


def main():
    """Build role-based navigation before running the selected Streamlit page."""
    st.set_page_config(
        page_title="AISIA美容助理",
        page_icon="✨",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    chat_page = create_chat_page()
    # Keep the regulatory review URL directly reachable without adding a
    # second primary navigation item to the customer-facing chat interface.
    def render_underage_mode():
        underage_mode(chat_page)

    def render_personalization_settings():
        personalization_settings(chat_page)

    underage_page = st.Page(
        render_underage_mode,
        title="未成年人模式",
        # icon=":material/child_care:",
        url_path="underage",
        visibility="hidden",
    )
    personal_page = st.Page(
        render_personalization_settings,
        title="个性化推荐设置",
        url_path="personal",
        visibility="hidden",
    )
    principal = None
    try:
        principal = resolve_principal()
    except Exception:
        # The selected authenticated page will display the detailed error.
        # Public pages such as /underage must remain independently reachable.
        pass

    if principal and principal.has_any_role({"admin"}):
        pages = [
            chat_page,
            underage_page,
            personal_page,
            st.Page(
                "pages/1_Indexing_Inspector.py",
                title="索引诊断",
                icon=":material/troubleshoot:",
            ),
            st.Page(
                "pages/2_Notion_Sync.py",
                title="Notion 同步",
                icon=":material/sync:",
            ),
        ]
        # Hide Streamlit's framework-level page navigation. It otherwise
        # flashes before the app finishes loading; admin links live in the
        # application sidebar above and all registered routes remain usable.
        navigation = st.navigation(pages, position="hidden")
    else:
        # With hidden navigation, admin pages are neither shown nor routable.
        navigation = st.navigation(
            [chat_page, underage_page, personal_page],
            position="hidden",
        )
    navigation.run()


if __name__ == "__main__":
    main()
