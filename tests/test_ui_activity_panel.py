from package.ui.components.activity_panel import (
    ACTIVITY_PANEL_HEIGHT_PX,
    activity_panel_marker,
    activity_panel_storage_key,
    build_activity_panel_script,
)
from package.ui.components.assets import load_asset


def test_activity_panel_uses_compact_fixed_height() -> None:
    assert 140 <= ACTIVITY_PANEL_HEIGHT_PX <= 180


def test_activity_panel_marker_escapes_execution_id() -> None:
    marker = activity_panel_marker('execution-<1>"')

    assert 'data-franq-activity-panel="execution-&lt;1&gt;&quot;"' in marker
    assert "display:none" in marker


def test_activity_panel_script_preserves_expansion_and_tracks_latest_action() -> None:
    execution_id = "execution-1"
    script = build_activity_panel_script(execution_id)

    assert activity_panel_storage_key(execution_id) in script
    assert "sessionStorage" in script
    assert "persistUserIntent" in script
    assert "desiredOpen" in script
    assert "restoreDesiredOpenState" in script
    assert "attributeFilter: ['open']" in script
    assert "MutationObserver" in script
    assert "scrollHeight" in script
    assert "distanceFromBottom" in script
    assert "pinned" in script
    assert "franq-activity-timeline" in script


def test_activity_panel_does_not_mutate_streamlit_layout_contract() -> None:
    script = build_activity_panel_script("execution-1")

    assert "findVerticalScrollContainer" in script
    assert "getComputedStyle" in script
    assert "style.setProperty" not in script
    assert "max-height" not in script
    assert "overflow-y" not in script
    assert "overflow-x" not in script
    assert "stVerticalBlockBorderWrapper" not in script


def test_activity_panel_css_only_styles_content_not_layout_wrappers() -> None:
    css = load_asset("activity_panel.css")

    assert ".franq-activity-timeline *" not in css
    assert "stVerticalBlockBorderWrapper" not in css
    assert "white-space: pre-wrap" in css
    assert "overflow-x: hidden" in css


def test_activity_panel_script_escapes_script_breakout_characters() -> None:
    script = build_activity_panel_script("execution-</script>&")

    assert "execution-\\u003c/script\\u003e\\u0026" in script
    assert "execution-</script>&" not in script
