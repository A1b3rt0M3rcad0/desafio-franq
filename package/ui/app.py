import time
from typing import Any

import httpx
import streamlit as st

from package.ui.activity_panel import (
    ACTIVITY_PANEL_HEIGHT_PX,
    activity_panel_marker,
    mount_activity_panel_behavior,
)
from package.ui.client import FranqApiClient
from package.ui.composer import render_chat_composer
from package.ui.observation import (
    ActivityPresentation,
    apply_observed_frame,
    new_observation_state,
    phase_label,
)
from package.ui.rendering import render_result
from package.ui.scroll import mount_sticky_chat_scroll
from package.ui.settings import StreamlitSettings


st.set_page_config(
    page_title="Assistente Virtual de Dados",
    page_icon="💬",
    layout="centered",
)


@st.cache_resource
def _client(base_url: str, timeout_seconds: float) -> FranqApiClient:
    return FranqApiClient(base_url=base_url, timeout_seconds=timeout_seconds)


def _query_value(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return str(value[-1]) if value else None
    return str(value) if value else None


def _set_session(session_id: str) -> None:
    st.session_state.session_id = session_id
    st.query_params["session_id"] = session_id


def _new_active_response(execution_id: str) -> dict[str, Any]:
    return new_observation_state(execution_id)


def _active_response(execution_id: str) -> dict[str, Any]:
    active = st.session_state.get("active_response")
    if not isinstance(active, dict) or active.get("execution_id") != execution_id:
        active = _new_active_response(execution_id)
        st.session_state.active_response = active
    return active


def _clear_active_execution() -> None:
    st.session_state.active_execution_id = None
    st.session_state.active_response = None
    st.session_state.last_sequence = None
    if "execution_id" in st.query_params:
        del st.query_params["execution_id"]


def _load_history(client: FranqApiClient, session_id: str) -> None:
    executions = client.list_session_executions(session_id)
    messages: list[dict[str, Any]] = []
    active_execution_id: str | None = None

    for execution in executions:
        execution_id = str(execution["id"])
        messages.append(
            {
                "role": "user",
                "content": str(execution["question"]),
                "execution_id": execution_id,
            }
        )
        status = str(execution.get("status") or "")
        if status == "completed":
            messages.append(
                {
                    "role": "assistant",
                    "content": str(execution.get("answer") or ""),
                    "result": execution.get("result"),
                    "execution_id": execution_id,
                }
            )
        elif status == "failed":
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "Não foi possível concluir a execução: "
                        f"{execution.get('error') or 'erro desconhecido'}"
                    ),
                    "result": None,
                    "execution_id": execution_id,
                }
            )
        elif status == "cancelled":
            messages.append(
                {
                    "role": "assistant",
                    "content": str(execution.get("answer") or ""),
                    "result": execution.get("result"),
                    "execution_id": execution_id,
                    "cancelled": True,
                }
            )
        elif status in {"pending", "running", "cancel_requested"}:
            active_execution_id = execution_id

    st.session_state.messages = messages
    st.session_state.active_execution_id = active_execution_id
    st.session_state.active_response = (
        _new_active_response(active_execution_id) if active_execution_id else None
    )
    st.session_state.last_sequence = None
    if active_execution_id:
        st.query_params["execution_id"] = active_execution_id
    elif "execution_id" in st.query_params:
        del st.query_params["execution_id"]


def _ensure_session(client: FranqApiClient) -> str:
    requested = _query_value("session_id")
    current = st.session_state.get("session_id")

    if requested and requested != current:
        try:
            client.get_session(requested)
        except httpx.HTTPError:
            requested = None
        else:
            _set_session(requested)
            _load_history(client, requested)
            return requested

    if current:
        st.query_params["session_id"] = current
        if "messages" not in st.session_state:
            _load_history(client, current)
        return str(current)

    created = client.create_session()
    session_id = str(created["id"])
    _set_session(session_id)
    _load_history(client, session_id)
    return session_id


def _new_conversation(client: FranqApiClient) -> None:
    created = client.create_session()
    session_id = str(created["id"])
    st.session_state.clear()
    _set_session(session_id)
    st.session_state.messages = []
    st.session_state.active_execution_id = None
    st.session_state.active_response = None
    st.session_state.last_sequence = None
    if "execution_id" in st.query_params:
        del st.query_params["execution_id"]
    st.rerun()


def _switch_session(client: FranqApiClient, session_id: str) -> None:
    _set_session(session_id)
    _clear_active_execution()
    _load_history(client, session_id)
    st.rerun()


def _session_label(session: dict[str, Any]) -> str:
    session_id = str(session.get("id") or "")
    metadata = session.get("metadata")
    if isinstance(metadata, dict):
        title = metadata.get("title")
        if title:
            return str(title)
    created_at = str(session.get("created_at") or "").replace("T", " ")[:16]
    short_id = session_id[:8] if session_id else "sessão"
    return f"{created_at} · {short_id}" if created_at else short_id


def _render_session_selector(client: FranqApiClient, session_id: str) -> None:
    try:
        sessions = client.list_sessions(limit=100)
    except (httpx.HTTPError, ValueError) as exc:
        st.warning(f"Não foi possível carregar as sessões: {exc}")
        return

    by_id = {
        str(session["id"]): session
        for session in sessions
        if isinstance(session, dict) and session.get("id")
    }
    if session_id not in by_id:
        try:
            by_id[session_id] = client.get_session(session_id)
        except httpx.HTTPError:
            pass

    options = list(by_id)
    if not options:
        return

    index = options.index(session_id) if session_id in options else 0
    selected = st.selectbox(
        "Conversas",
        options,
        index=index,
        format_func=lambda value: _session_label(by_id[value]),
        key=f"session_selector_{session_id}",
    )
    if selected != session_id:
        _switch_session(client, selected)


def _render_history() -> None:
    for message in st.session_state.get("messages", []):
        with st.chat_message(message["role"]):
            content = str(message.get("content") or "")
            if content:
                st.markdown(content)
            if message.get("cancelled"):
                st.caption("Resposta interrompida pelo usuário.")
            if message["role"] == "assistant":
                render_result(message.get("result"))


def _refresh_durable_result(
    client: FranqApiClient,
    execution_id: str,
    *,
    current_answer: str,
    current_result: dict[str, Any] | None,
) -> tuple[str | None, str, dict[str, Any] | None, str | None]:
    try:
        execution = client.get_execution(execution_id)
    except httpx.HTTPError:
        return None, current_answer, current_result, None

    status = str(execution.get("status") or "")
    answer = str(execution.get("answer") or current_answer)
    result = current_result
    if isinstance(execution.get("result"), dict):
        result = execution["result"]
    error = str(execution.get("error")) if execution.get("error") else None
    return status, answer, result, error


def _apply_durable_result(
    active: dict[str, Any],
    *,
    status: str | None,
    answer: str,
    result: dict[str, Any] | None,
    error: str | None,
) -> bool:
    content_changed = False
    current = str(active.get("content") or "")
    if answer and answer != current:
        if answer.startswith(current) or not current.startswith(answer):
            active["content"] = answer
            content_changed = True
    if result is not None:
        active["result"] = result
    if error:
        active["error"] = error
    if status:
        active["phase"] = status
        if status == "completed":
            active["response_started"] = True
            active["response_completed"] = True
    return content_changed


def _activity_from_state(value: dict[str, Any]) -> ActivityPresentation:
    return ActivityPresentation(
        sequence=value.get("sequence") if isinstance(value.get("sequence"), int) else None,
        event_type=str(value.get("event_type") or ""),
        title=str(value.get("title") or value.get("event_type") or "Atividade"),
        detail=str(value.get("detail")) if value.get("detail") else None,
        status=str(value.get("status") or "info"),
    )


def _latest_activity(active: dict[str, Any]) -> ActivityPresentation | None:
    activities = active.get("activities")
    if not isinstance(activities, list):
        return None
    for stored in reversed(activities):
        if isinstance(stored, dict):
            return _activity_from_state(stored)
    return None


def _render_activity(activity_view, activity: ActivityPresentation) -> None:
    icon = {
        "running": "◌",
        "success": "✓",
        "error": "✕",
        "info": "•",
    }.get(activity.status, "•")
    activity_view.markdown(f"{icon} **{activity.title}**")
    if not activity.detail:
        return
    if activity.event_type == "sql.generated" or "SELECT " in activity.detail.upper():
        activity_view.code(activity.detail, language="sql")
    else:
        activity_view.caption(activity.detail)


def _running_status_label(active: dict[str, Any], latest: ActivityPresentation | None = None) -> str:
    if active.get("response_started"):
        return "Análise concluída"
    if latest is not None:
        title = latest.title.rstrip(".")
        return title if title.endswith("...") else f"{title}..."
    return phase_label(str(active.get("phase") or "pending")) or "Execução em andamento..."


def _observe_execution(
    client: FranqApiClient,
    execution_id: str,
    response_container,
) -> bool:
    active = _active_response(execution_id)
    terminal_status: str | None = None
    realtime_degraded = False

    with response_container:
        with st.chat_message("assistant"):
            response_started = bool(active.get("response_started"))
            status_view = st.status(
                _running_status_label(active, _latest_activity(active)),
                expanded=False,
                state="complete" if response_started else "running",
            )
            activity_view = status_view.container(
                height=ACTIVITY_PANEL_HEIGHT_PX,
                border=False,
                key=f"activity_timeline_{execution_id}",
                gap="xxsmall",
            )
            activity_view.markdown(
                activity_panel_marker(execution_id),
                unsafe_allow_html=True,
            )
            mount_activity_panel_behavior(execution_id)
            for stored in active.get("activities", []):
                if isinstance(stored, dict):
                    _render_activity(activity_view, _activity_from_state(stored))

            message_view = st.empty()
            if active.get("content"):
                message_view.markdown(str(active["content"]))

            try:
                for frame in client.observe_execution(
                    execution_id,
                    last_sequence=st.session_state.get("last_sequence"),
                ):
                    if frame.sequence is not None:
                        st.session_state.last_sequence = frame.sequence

                    update = apply_observed_frame(active, frame)
                    latest_activity: ActivityPresentation | None = None
                    for activity in update.new_activities:
                        latest_activity = activity
                        _render_activity(activity_view, activity)

                    if update.content_changed:
                        message_view.markdown(str(active.get("content") or ""))

                    if update.transport_degraded:
                        realtime_degraded = True
                        if not active.get("response_started"):
                            status_view.update(
                                label="Reconectando à execução...",
                                state="running",
                            )
                    elif active.get("response_started"):
                        status_view.update(
                            label="Análise concluída",
                            state="complete",
                        )
                    elif update.terminal_status == "failed":
                        status_view.update(label="Falha na execução", state="error")
                    else:
                        status_view.update(
                            label=_running_status_label(active, latest_activity),
                            state="running",
                        )

                    if update.terminal_status is not None:
                        terminal_status = update.terminal_status

                    st.session_state.active_response = active
            except (httpx.HTTPError, ValueError):
                realtime_degraded = True
                durable_status, durable_answer, durable_result, durable_error = (
                    _refresh_durable_result(
                        client,
                        execution_id,
                        current_answer=str(active.get("content") or ""),
                        current_result=active.get("result"),
                    )
                )
                changed = _apply_durable_result(
                    active,
                    status=durable_status,
                    answer=durable_answer,
                    result=durable_result,
                    error=durable_error,
                )
                if changed:
                    message_view.markdown(str(active.get("content") or ""))
                if durable_status in {"completed", "failed", "cancelled"}:
                    terminal_status = durable_status
                elif not active.get("response_started"):
                    status_view.update(
                        label="Reconectando à execução...",
                        state="running",
                    )
                st.session_state.active_response = active

            if terminal_status not in {"completed", "failed", "cancelled"}:
                durable_status, durable_answer, durable_result, durable_error = (
                    _refresh_durable_result(
                        client,
                        execution_id,
                        current_answer=str(active.get("content") or ""),
                        current_result=active.get("result"),
                    )
                )
                changed = _apply_durable_result(
                    active,
                    status=durable_status,
                    answer=durable_answer,
                    result=durable_result,
                    error=durable_error,
                )
                if changed:
                    message_view.markdown(str(active.get("content") or ""))
                if durable_status in {"completed", "failed", "cancelled"}:
                    terminal_status = durable_status
                else:
                    st.session_state.active_response = active
                    if realtime_degraded and not active.get("response_started"):
                        status_view.update(
                            label="Reconectando à execução...",
                            state="running",
                        )
                    elif active.get("response_started"):
                        status_view.update(
                            label="Análise concluída",
                            state="complete",
                        )
                    return False

            if terminal_status == "completed":
                final_answer = str(
                    active.get("content") or "Execução concluída sem conteúdo textual."
                )
                message_view.markdown(final_answer)
                render_result(active.get("result"))
                status_view.update(label="Concluído", state="complete")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": final_answer,
                        "result": active.get("result"),
                        "execution_id": execution_id,
                    }
                )
                _clear_active_execution()
                return True

            if terminal_status == "cancelled":
                partial = str(active.get("content") or "")
                if partial:
                    message_view.markdown(partial)
                st.caption("Resposta interrompida pelo usuário.")
                status_view.update(label="Interrompido", state="complete")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": partial,
                        "result": active.get("result"),
                        "execution_id": execution_id,
                        "cancelled": True,
                    }
                )
                _clear_active_execution()
                return True

            if terminal_status == "failed":
                final_error = (
                    "Não foi possível concluir a execução: "
                    f"{active.get('error') or 'erro desconhecido'}"
                )
                st.error(final_error)
                status_view.update(label="Falha na execução", state="error")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": final_error,
                        "result": None,
                        "execution_id": execution_id,
                    }
                )
                _clear_active_execution()
                return True

            st.session_state.active_response = active
            return False


def _request_stop(client: FranqApiClient, execution_id: str) -> None:
    active = _active_response(execution_id)
    try:
        client.stop_execution(execution_id)
    except httpx.HTTPError as exc:
        st.error(f"Não foi possível interromper a execução: {exc}")
        return
    active["cancel_requested"] = True
    active["phase"] = "cancel_requested"
    st.session_state.active_response = active


def _submit_question(client: FranqApiClient, session_id: str, question: str) -> None:
    try:
        execution = client.create_execution(session_id=session_id, question=question)
    except httpx.HTTPError as exc:
        with st.chat_message("assistant"):
            st.error(f"Não foi possível iniciar a execução: {exc}")
        return

    execution_id = str(execution["id"])
    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
            "execution_id": execution_id,
        }
    )
    st.session_state.active_execution_id = execution_id
    st.session_state.active_response = _new_active_response(execution_id)
    st.session_state.last_sequence = None
    st.query_params["execution_id"] = execution_id
    st.rerun()


def main() -> None:
    settings = StreamlitSettings()
    client = _client(
        settings.streamlit_api_base_url,
        settings.streamlit_api_timeout_seconds,
    )

    st.title("Assistente Virtual de Dados")
    st.caption("Faça perguntas sobre os dados em linguagem natural.")

    try:
        session_id = _ensure_session(client)
    except httpx.HTTPError as exc:
        st.error(f"Não foi possível conectar à API: {exc}")
        st.stop()

    with st.sidebar:
        st.subheader("Conversas")
        _render_session_selector(client, session_id)
        if st.button("Nova conversa", use_container_width=True):
            try:
                _new_conversation(client)
            except httpx.HTTPError as exc:
                st.error(f"Não foi possível criar uma nova sessão: {exc}")
        st.caption(f"Sessão atual: `{session_id}`")

    _render_history()

    query_execution = _query_value("execution_id")
    active_execution = query_execution or st.session_state.get("active_execution_id")
    active_response_container = st.container() if active_execution else None

    question, stop_requested = render_chat_composer(
        active_execution_id=str(active_execution) if active_execution else None,
    )
    mount_sticky_chat_scroll()

    if active_execution:
        execution_id = str(active_execution)
        st.session_state.active_execution_id = execution_id
        st.query_params["execution_id"] = execution_id
        if stop_requested:
            _request_stop(client, execution_id)
        if active_response_container is None:
            active_response_container = st.container()
        finished = _observe_execution(
            client,
            execution_id,
            active_response_container,
        )
        if finished:
            st.rerun()
        time.sleep(0.2)
        st.rerun()
        return

    if question:
        _submit_question(client, session_id, question)


if __name__ == "__main__":
    main()
