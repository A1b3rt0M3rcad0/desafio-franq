from package.ui.components.assets import load_asset


def test_conversation_sidebar_supports_right_click_delete_and_inline_rename() -> None:
    javascript = load_asset("conversation_sidebar.js")

    assert 'addEventListener("contextmenu"' in javascript
    assert 'addEventListener("dblclick"' in javascript
    assert "delete_session_id" in javascript
    assert "rename_session_id" in javascript
    assert "window.confirm" in javascript


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
