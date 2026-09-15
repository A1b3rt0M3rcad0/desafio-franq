from package.ui.activity_panel import (
    ACTIVITY_PANEL_HEIGHT_PX,
    activity_panel_marker,
    activity_panel_storage_key,
    build_activity_panel_script,
)


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
    assert 'addEventListener("toggle"' in script
    assert 'addEventListener("click", persistUserIntent, true)' in script
    assert "desiredOpen" in script
    assert "restoreDesiredOpenState" in script
    assert 'attributeFilter: ["open"]' in script
    assert "MutationObserver" in script
    assert "scrollHeight" in script
    assert "distanceFromBottom" in script
    assert "pinned" in script
    assert "franq-activity-timeline" in script


def test_activity_panel_does_not_treat_streamlit_toggle_as_user_intent() -> None:
    script = build_activity_panel_script("execution-1")

    # User preference is persisted from a click on the summary. A toggle caused by
    # Streamlit re-rendering must instead restore the desired state, otherwise every
    # SSE update can close an expander that the user intentionally left open.
    assert "const persistUserIntent" in script
    assert "desiredOpen = !details.open" in script
    assert "host.sessionStorage.setItem(storageKey, desiredOpen ? \"1\" : \"0\")" in script
    assert "if (details.open !== desiredOpen)" in script
    assert "requestAnimationFrame(restoreDesiredOpenState)" in script
    assert "detailsObserver.observe(details" in script


def test_activity_panel_forces_vertical_scroll_and_blocks_outer_horizontal_scroll() -> None:
    script = build_activity_panel_script("execution-1")

    assert 'target.style.setProperty("height", `${panelHeight}px`, "important")' in script
    assert 'target.style.setProperty("max-height", `${panelHeight}px`, "important")' in script
    assert 'target.style.setProperty("overflow-y", "auto", "important")' in script
    assert 'target.style.setProperty("overflow-x", "hidden", "important")' in script
    assert "overflow-y: auto !important" in script
    assert "overflow-x: hidden !important" in script
    assert "white-space: pre-wrap !important" in script
    assert "overflow-wrap: anywhere !important" in script


def test_activity_panel_reapplies_scroll_contract_after_dom_updates() -> None:
    script = build_activity_panel_script("execution-1")

    assert "const onContentMutation" in script
    assert "applyScrollContract(scrollTarget)" in script
    assert "contentObserver.observe(scrollTarget" in script
    assert "rootObserver.observe(doc.body" in script


def test_activity_panel_script_escapes_script_breakout_characters() -> None:
    script = build_activity_panel_script("execution-</script>&")

    assert "execution-\\u003c/script\\u003e\\u0026" in script
    assert "execution-</script>&" not in script
