from functools import lru_cache
from importlib import resources
from typing import Mapping

import streamlit as st
import streamlit.components.v1 as components


_ASSET_ROOT = resources.files("package.ui.components").joinpath("assets")


@lru_cache(maxsize=64)
def load_asset(name: str) -> str:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("asset name must be a simple file name")
    return _ASSET_ROOT.joinpath(name).read_text(encoding="utf-8")


def render_asset(name: str, replacements: Mapping[str, str] | None = None) -> str:
    rendered = load_asset(name)
    for key, value in (replacements or {}).items():
        rendered = rendered.replace(f"__{key}__", value)
    return rendered


def inject_style_asset(
    name: str,
    replacements: Mapping[str, str] | None = None,
) -> None:
    css = render_asset(name, replacements)
    html = render_asset("style_host.html", {"CONTENT": css})
    st.markdown(html, unsafe_allow_html=True)


def mount_script_asset(
    name: str,
    replacements: Mapping[str, str] | None = None,
) -> None:
    javascript = render_asset(name, replacements)
    html = render_asset("script_host.html", {"CONTENT": javascript})
    components.html(html, height=0, width=0)
