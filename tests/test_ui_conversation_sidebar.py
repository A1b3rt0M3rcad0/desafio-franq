from package.ui.components.assets import load_asset


def test_conversation_sidebar_supports_right_click_delete_and_inline_rename() -> None:
    javascript = load_asset("conversation_sidebar.js")
    css = load_asset("conversation_sidebar.css")
    html = load_asset("conversation_sidebar.html")

    assert 'addEventListener("contextmenu"' in javascript
    assert 'addEventListener("dblclick"' in javascript
    assert "delete_session_id" in javascript
    assert "rename_session_id" in javascript
    assert "conversation-title-editor" in javascript
    assert "window.prompt" not in javascript
    assert "window.confirm" not in javascript
    assert 'id="conversation-delete-confirm"' in html
    assert 'id="conversation-delete-confirm-action"' in html
    assert 'id="conversation-delete-cancel"' in html
    assert ".conversation-title-editor" in css


def test_conversation_sidebar_loads_more_when_vertical_scroll_reaches_end() -> None:
    javascript = load_asset("conversation_sidebar.js")
    css = load_asset("conversation_sidebar.css")

    assert 'list.addEventListener("scroll"' in javascript
    assert "sessions_limit" in javascript
    assert "overflow-y: auto" in css
    assert "overflow-x: hidden" in css


def test_conversation_titles_stay_on_one_line_with_ellipsis() -> None:
    css = load_asset("conversation_sidebar.css")

    assert "white-space: nowrap" in css
    assert "text-overflow: ellipsis" in css


def test_conversation_sidebar_syncs_parent_theme_and_highlights_active_session() -> None:
    javascript = load_asset("conversation_sidebar.js")
    css = load_asset("conversation_sidebar.css")

    assert "syncTheme" in javascript
    assert '[data-testid="stSidebar"]' in javascript
    assert "--franq-text-color" in javascript
    assert ".conversation-item.is-active" in css
    assert "box-shadow: inset 3px 0 0 var(--franq-accent)" in css
    assert "color: var(--franq-text-color)" in css
