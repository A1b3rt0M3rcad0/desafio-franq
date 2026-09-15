from package.ui.activity_panel import (
    ACTIVITY_PANEL_HEIGHT_PX,
    activity_panel_marker,
    activity_panel_storage_key,
    build_activity_panel_script,
)


def test_activity_panel_uses_compact_fixed_height() -> None:
    assert 140 <= ACTIVITY_PANEL_HEIGHT_PX <= 220


def test_activity_panel_marker_escapes_execution_id() -> None:
    marker = activity_panel_marker('execution-<1>"')

    assert 'data-franq-activity-panel="execution-&lt;1&gt;&quot;"' in marker
    assert "display:none" in marker


def test_activity_panel_script_preserves_expansion_and_tracks_latest_action() -> None:
    execution_id = "execution-1"
    script = build_activity_panel_script(execution_id)

    assert activity_panel_storage_key(execution_id) in script
    assert "sessionStorage" in script
    assert 'addEventListener("toggle"' in script
    assert "MutationObserver" in script
    assert "scrollHeight" in script
    assert "distanceFromBottom" in script
    assert "pinned" in script
    assert "franq-activity-timeline" in script


def test_activity_panel_script_escapes_script_breakout_characters() -> None:
    script = build_activity_panel_script("execution-</script>&")

    assert "execution-\\u003c/script\\u003e\\u0026" in script
    assert "execution-</script>&" not in script
