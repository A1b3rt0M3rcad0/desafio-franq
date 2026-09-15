import json
from html import escape
from typing import Any, Iterable

import streamlit as st

from package.ui.components.assets import inject_style_asset, mount_script_asset, render_asset
from package.ui.observation import ActivityPresentation


ACTIVITY_PANEL_HEIGHT_PX = 156
_ALLOWED_PANEL_STATES = {"running", "complete", "error"}
_ACTIVITY_ICONS = {
    "running": "◌",
    "success": "✓",
    "error": "✕",
    "info": "•",
}


def _javascript_json(value: str) -> str:
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def activity_panel_storage_key(execution_id: str) -> str:
    return f"franq:execution:{execution_id}:activities-open"


def _script_replacements(execution_id: str) -> dict[str, str]:
    return {
        "EXECUTION_ID_JSON": _javascript_json(execution_id),
        "STORAGE_KEY_JSON": _javascript_json(activity_panel_storage_key(execution_id)),
    }


def build_activity_panel_script(execution_id: str) -> str:
    return render_asset("activity_panel.js", _script_replacements(execution_id))


def activity_from_mapping(value: dict[str, Any]) -> ActivityPresentation:
    return ActivityPresentation(
        sequence=value.get("sequence") if isinstance(value.get("sequence"), int) else None,
        event_type=str(value.get("event_type") or ""),
        title=str(value.get("title") or value.get("event_type") or "Atividade"),
        detail=str(value.get("detail")) if value.get("detail") else None,
        status=str(value.get("status") or "info"),
    )


def latest_activity(values: Iterable[dict[str, Any]]) -> ActivityPresentation | None:
    sequence = list(values)
    for value in reversed(sequence):
        if isinstance(value, dict):
            return activity_from_mapping(value)
    return None


def _activity_detail_html(activity: ActivityPresentation) -> str:
    if not activity.detail:
        return ""
    detail = escape(activity.detail)
    if activity.event_type == "sql.generated" or "SELECT " in activity.detail.upper():
        return render_asset("activity_sql_detail.html", {"DETAIL": detail})
    return render_asset("activity_detail.html", {"DETAIL": detail})


def _activity_html(activity: ActivityPresentation) -> str:
    status = activity.status if activity.status in _ACTIVITY_ICONS else "info"
    sequence = "" if activity.sequence is None else str(activity.sequence)
    return render_asset(
        "activity_item.html",
        {
            "STATUS": status,
            "SEQUENCE": escape(sequence, quote=True),
            "ICON": _ACTIVITY_ICONS[status],
            "TITLE": escape(activity.title),
            "DETAIL": _activity_detail_html(activity),
        },
    )


def render_activity_panel_html(
    *,
    execution_id: str,
    label: str,
    state: str,
    activities: Iterable[ActivityPresentation],
) -> str:
    normalized_state = state if state in _ALLOWED_PANEL_STATES else "running"
    activities_html = "".join(_activity_html(activity) for activity in activities)
    return render_asset(
        "activity_panel.html",
        {
            "STATE": normalized_state,
            "EXECUTION_ID": escape(execution_id, quote=True),
            "LABEL": escape(label),
            "ACTIVITIES": activities_html,
        },
    )


class ActivityPanel:
    """Realtime execution panel rendered through a single Streamlit delta node."""

    def __init__(
        self,
        *,
        execution_id: str,
        label: str,
        state: str,
        activities: Iterable[ActivityPresentation] = (),
    ) -> None:
        self._execution_id = execution_id
        self._label = label
        self._state = state if state in _ALLOWED_PANEL_STATES else "running"
        self._activities = list(activities)
        inject_style_asset(
            "activity_panel.css",
            {"PANEL_HEIGHT_PX": str(ACTIVITY_PANEL_HEIGHT_PX)},
        )
        self._view = st.empty()
        self._render()
        mount_script_asset("activity_panel.js", _script_replacements(execution_id))

    def _render(self) -> None:
        # st.html owns one DOM subtree and avoids the Markdown block parser. Keeping
        # every activity inside this single delta node is important while SSE events
        # update the panel repeatedly during the same Streamlit script run.
        self._view.html(
            render_activity_panel_html(
                execution_id=self._execution_id,
                label=self._label,
                state=self._state,
                activities=self._activities,
            ),
        )

    def append(self, activity: ActivityPresentation) -> None:
        self._activities.append(activity)
        self._render()

    def update(self, *, label: str, state: str) -> None:
        normalized_state = state if state in _ALLOWED_PANEL_STATES else "running"
        if label == self._label and normalized_state == self._state:
            return
        self._label = label
        self._state = normalized_state
        self._render()
