from package.ui.components.activity_panel import (
    ACTIVITY_PANEL_HEIGHT_PX,
    activity_panel_storage_key,
    build_activity_panel_script,
    render_activity_panel_html,
)
from package.ui.components.assets import render_asset
from package.ui.observation import ActivityPresentation


def _activity(
    sequence: int,
    *,
    title: str = "Atividade",
    detail: str | None = None,
    event_type: str = "tool.completed",
    status: str = "success",
) -> ActivityPresentation:
    return ActivityPresentation(
        sequence=sequence,
        event_type=event_type,
        title=title,
        detail=detail,
        status=status,
    )


def test_activity_panel_uses_compact_fixed_height() -> None:
    assert 140 <= ACTIVITY_PANEL_HEIGHT_PX <= 180


def test_activity_panel_renders_one_owned_html_tree_and_escapes_content() -> None:
    html = render_activity_panel_html(
        execution_id='execution-<1>"',
        label="Analisando <dados>",
        state="running",
        activities=[
            _activity(1, title="Consulta <1>", detail="resultado & detalhe"),
            _activity(
                2,
                title="SQL",
                detail="SELECT * FROM compras WHERE categoria = '<x>'",
                event_type="sql.generated",
            ),
        ],
    )

    assert 'data-franq-activity-panel="execution-&lt;1&gt;&quot;"' in html
    assert "Analisando &lt;dados&gt;" in html
    assert "Consulta &lt;1&gt;" in html
    assert "resultado &amp; detalhe" in html
    assert "&lt;x&gt;" in html
    assert html.count("franq-activity-item franq-activity-item--") == 2
    assert 'data-franq-activity-scroll' in html
    assert "stVerticalBlock" not in html


def test_activity_panel_script_preserves_expansion_and_scroll_across_replacement() -> None:
    execution_id = "execution-1"
    script = build_activity_panel_script(execution_id)

    assert activity_panel_storage_key(execution_id) in script
    assert "sessionStorage" in script
    assert "persistUserIntent" in script
    assert "desiredOpen" in script
    assert "restoreDesiredOpenState" in script
    assert "MutationObserver" in script
    assert "savedScrollTop" in script
    assert "distanceFromBottom" in script
    assert "pinned" in script
    assert "[data-franq-activity-scroll]" in script


def test_activity_panel_script_never_mutates_layout_styles() -> None:
    script = build_activity_panel_script("execution-1")

    assert "style.setProperty" not in script
    assert "getComputedStyle" not in script
    assert "stVerticalBlockBorderWrapper" not in script
    assert "stVerticalBlock" not in script


def test_activity_panel_css_owns_vertical_scroll_without_streamlit_selectors() -> None:
    css = render_asset(
        "activity_panel.css",
        {"PANEL_HEIGHT_PX": str(ACTIVITY_PANEL_HEIGHT_PX)},
    )

    assert f"max-height: {ACTIVITY_PANEL_HEIGHT_PX}px" in css
    assert "overflow-y: auto" in css
    assert "overflow-x: hidden" in css
    assert "display: flex" in css
    assert "flex-direction: column" in css
    assert "data-testid" not in css
    assert "stVerticalBlock" not in css


def test_activity_panel_script_escapes_script_breakout_characters() -> None:
    script = build_activity_panel_script("execution-</script>&")

    assert "execution-\\u003c/script\\u003e\\u0026" in script
    assert "execution-</script>&" not in script
