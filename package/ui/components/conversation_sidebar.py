import streamlit as st

from package.ui.components.assets import load_asset


DEFAULT_CONVERSATION_PAGE_SIZE = 20
MAX_CONVERSATION_PANEL_HEIGHT = 560
MIN_CONVERSATION_PANEL_HEIGHT = 120


_CONVERSATION_SIDEBAR = st.components.v2.component(
    name="franq_conversation_sidebar",
    html=load_asset("conversation_sidebar.html"),
    css=load_asset("conversation_sidebar.css"),
    js=load_asset("conversation_sidebar.js"),
    isolate_styles=True,
)


def render_conversation_sidebar(
    sessions: list[dict[str, object]],
    *,
    active_session_id: str | None,
    current_limit: int,
    has_more: bool,
) -> None:
    visible_sessions: list[dict[str, str]] = []
    for session in sessions:
        session_id = str(session.get("id") or "")
        if not session_id:
            continue
        visible_sessions.append(
            {
                "id": session_id,
                "title": str(session.get("title") or "Conversa"),
            }
        )

    content_height = max(
        MIN_CONVERSATION_PANEL_HEIGHT,
        min(MAX_CONVERSATION_PANEL_HEIGHT, len(visible_sessions) * 38 + 8),
    )
    _CONVERSATION_SIDEBAR(
        data={
            "sessions": visible_sessions,
            "active_session_id": active_session_id,
            "current_limit": max(current_limit, DEFAULT_CONVERSATION_PAGE_SIZE),
            "page_size": DEFAULT_CONVERSATION_PAGE_SIZE,
            "has_more": has_more,
        },
        key="franq_conversation_sidebar",
        width="stretch",
        height=content_height,
    )
