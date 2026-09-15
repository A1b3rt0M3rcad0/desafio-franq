import json
from html import escape
from typing import Any, Iterable

import streamlit as st

from package.ui.components.assets import inject_style_asset, mount_script_asset, render_asset
from package.ui.observation import ActivityPresentation


ACTIVITY_PANEL_HEIGHT_PX = 156


def activity_panel_storage_key(execution_id: str) -> str:
    return f"franq:execution:{execution_id}:activities-open"


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


class ActivityPanel:
    def __init__(
        self,
        *,
        execution_id: str,
        label: str,
        state: str,
        activities: Iterable[ActivityPresentation] = (),
    ) -> None:
        self._execution_id = execution_id
        self._status_view = st.status(label, expanded=False, state=state)
        self._activity_view = self._status_view.container(
            height=ACTIVITY_PANEL_HEIGHT_PX,
            border=False,
            key=f"activity_timeline_{execution_id}",
            gap="xxsmall",
        )
        marker = render_asset(
            "activity_panel_marker.html",
            {"EXECUTION_ID": escape(execution_id, quote=True)},
        )
        self._activity_view.markdown(marker, unsafe_allow_html=True)
        inject_style_asset("activity_panel.css")
        mount_script_asset(
            "activity_panel.js",
            {
                "EXECUTION_ID_JSON": json.dumps(execution_id),
                "STORAGE_KEY_JSON": json.dumps(activity_panel_storage_key(execution_id)),
            },
        )
        for activity in activities:
            self.append(activity)

    def append(self, activity: ActivityPresentation) -> None:
        icon = {
            "running": "◌",
            "success": "✓",
            "error": "✕",
            "info": "•",
        }.get(activity.status, "•")
        self._activity_view.markdown(f"{icon} **{activity.title}**")
        if not activity.detail:
            return
        if activity.event_type == "sql.generated" or "SELECT " in activity.detail.upper():
            self._activity_view.code(activity.detail, language="sql")
        else:
            self._activity_view.caption(activity.detail)

    def update(self, *, label: str, state: str) -> None:
        self._status_view.update(label=label, state=state)
