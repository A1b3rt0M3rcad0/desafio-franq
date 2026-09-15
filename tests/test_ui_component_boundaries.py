from pathlib import Path


_UI_ROOT = Path("package/ui")
_ASSET_ROOT = _UI_ROOT / "components" / "assets"


def test_ui_python_does_not_embed_script_or_style_tags() -> None:
    offenders: list[str] = []
    for path in _UI_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if "<script" in text or "</script>" in text or "<style" in text or "</style>" in text:
            offenders.append(str(path))

    assert offenders == []


def test_component_assets_are_separated_from_python() -> None:
    expected = {
        "activity_panel.js",
        "activity_panel.css",
        "activity_panel_marker.html",
        "sticky_chat_scroll.js",
        "composer.css",
        "script_host.html",
        "style_host.html",
    }
    actual = {path.name for path in _ASSET_ROOT.iterdir() if path.is_file()}

    assert expected <= actual
