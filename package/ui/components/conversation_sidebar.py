from html import escape

import streamlit.components.v1 as components

from package.ui.components.assets import load_asset, render_asset


DEFAULT_CONVERSATION_PAGE_SIZE = 20
MAX_CONVERSATION_PANEL_HEIGHT = 560


def render_conversation_sidebar(
    sessions: list[dict[str, object]],
    *,
    active_session_id: str | None,
    current_limit: int,
    has_more: bool,
) -> None:
    items: list[str] = []
    for session in sessions:
        session_id = str(session.get("id") or "")
        if not session_id:
            continue
        title = str(session.get("title") or "Conversa")
        items.append(
            render_asset(
                "conversation_item.html",
                {
                    "SESSION_ID": escape(session_id, quote=True),
                    "TITLE": escape(title),
                    "TITLE_ATTR": escape(title, quote=True),
                    "ACTIVE_CLASS": " is-active" if session_id == active_session_id else "",
                },
            )
        )

    javascript = render_asset(
        "conversation_sidebar.js",
        {
            "CURRENT_LIMIT": str(max(current_limit, DEFAULT_CONVERSATION_PAGE_SIZE)),
            "PAGE_SIZE": str(DEFAULT_CONVERSATION_PAGE_SIZE),
            "HAS_MORE": "true" if has_more else "false",
        },
    )
    html = render_asset(
        "conversation_sidebar.html",
        {
            "STYLE": load_asset("conversation_sidebar.css"),
            "ITEMS": "".join(items),
            "SCRIPT": javascript,
        },
    )
    content_height = max(56, len(items) * 38 + 8)
    components.html(
        html,
        height=min(MAX_CONVERSATION_PANEL_HEIGHT, content_height),
        scrolling=False,
    )
