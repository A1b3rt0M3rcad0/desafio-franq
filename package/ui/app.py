import time
from typing import Any

import httpx
import streamlit as st

from package.ui.client import FranqApiClient, ObservedFrame
from package.ui.components.activity_panel import (
    ActivityPanel,
    activity_from_mapping,
    latest_activity,
)
from package.ui.components.composer import render_chat_composer
from package.ui.components.conversation_sidebar import (
    DEFAULT_CONVERSATION_PAGE_SIZE,
    render_conversation_sidebar,
)
from package.ui.components.sticky_scroll import mount_sticky_chat_scroll
from package.ui.observation import (
    ActivityPresentation,
    apply_observed_frame,
    new_observation_state,
    phase_label,
    present_activity_frame,
)
from package.ui.rendering import render_result
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


def _reset_to_new_conversation() -> None:
    st.session_state.session_id = None
    st.session_state.messages = []
    st.session_state.active_execution_id = None
    st.session_state.active_response = None
    st.session_state.last_sequence = None
    for name in ("session_id", "execution_id"):
        if name in st.query_params:
            del st.query_params[name]


def _trace_cache() -> dict[str, list[dict[str, Any]]]:
    cache = st.session_state.setdefault("execution_trace_cache", {})
    if not isinstance(cache, dict):
        cache = {}
        st.session_state.execution_trace_cache = cache
    return cache


def _cache_execution_activities(execution_id: str, values: list[Any]) -> None:
    serialized: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, ActivityPresentation):
            serialized.append(value.as_dict())
        elif isinstance(value, dict):
            serialized.append(dict(value))
    _trace_cache()[execution_id] = serialized


def _historical_activities(
    client: FranqApiClient,
    execution_id: str,
) -> list[ActivityPresentation]:
    cache = _trace_cache()
    stored = cache.get(execution_id)
    if stored is None:
        stored = []
        try:
            trace = client.get_execution_trace(execution_id)
        except (httpx.HTTPError, ValueError):
            trace = []
        for step in trace:
            if not isinstance(step, dict):
                continue
            payload = step.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            sequence = step.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                sequence = None
            frame = ObservedFrame(
                execution_id=execution_id,
                type=str(step.get("event_type") or ""),
                sequence=sequence,
                payload=payload,
            )
            presentation = present_activity_frame(frame)
            if presentation is not None:
                stored.append(presentation.as_dict())
        cache[execution_id] = stored

    return [activity_from_mapping(value) for value in stored if isinstance(value, dict)]


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
                    "status": status,
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
                    "status": status,
                }
            )
        elif status == "cancelled":
            messages.append(
                {
                    "role": "assistant",
                    "content": str(execution.get("answer") or ""),
                    "result": execution.get("result"),
                    "execution_id": execution_id,
                    "status": status,
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


def _ensure_session(client: FranqApiClient) -> str | None:
    requested = _query_value("session_id")
    current = st.session_state.get("session_id")

    if requested and requested != current:
        try:
            client.get_session(requested)
        except httpx.HTTPError:
            if "session_id" in st.query_params:
                del st.query_params["session_id"]
        else:
            _set_session(requested)
            _load_history(client, requested)
            return requested

    if current:
        st.query_params["session_id"] = str(current)
        if "messages" not in st.session_state:
            _load_history(client, str(current))
        return str(current)

    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("active_execution_id", None)
    st.session_state.setdefault("active_response", None)
    st.session_state.setdefault("last_sequence", None)
    return None


def _sessions_limit() -> int:
    raw = _query_value("sessions_limit")
    if raw is None:
        return DEFAULT_CONVERSATION_PAGE_SIZE
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_CONVERSATION_PAGE_SIZE
    return max(DEFAULT_CONVERSATION_PAGE_SIZE, min(parsed, 200))


def _handle_sidebar_actions(client: FranqApiClient) -> None:
    rename_id = _query_value("rename_session_id")
    rename_title = _query_value("rename_session_title")
    if rename_id:
        for key in ("rename_session_id", "rename_session_title"):
            if key in st.query_params:
                del st.query_params[key]
        if rename_title:
            try:
                client.update_session_title(rename_id, rename_title)
            except httpx.HTTPError as exc:
                st.sidebar.error(f"Não foi possível renomear a conversa: {exc}")
            else:
                st.rerun()

    delete_id = _query_value("delete_session_id")
    if delete_id:
        del st.query_params["delete_session_id"]
        try:
            client.delete_session(delete_id)
        except httpx.HTTPError as exc:
            st.sidebar.error(f"Não foi possível excluir a conversa: {exc}")
        else:
            if str(st.session_state.get("session_id") or "") == delete_id:
                _reset_to_new_conversation()
            st.rerun()


def _render_conversations(client: FranqApiClient, session_id: str | None) -> None:
    limit = _sessions_limit()
    request_limit = min(limit + 1, 200)
    try:
        sessions = client.list_sessions(limit=request_limit)
    except (httpx.HTTPError, ValueError) as exc:
        st.warning(f"Não foi possível carregar as conversas: {exc}")
        return

    has_more = len(sessions) > limit
    visible = sessions[:limit]
    visible_ids = {str(item.get("id") or "") for item in visible}
    if session_id and session_id not in visible_ids:
        try:
            selected = client.get_session(session_id)
        except httpx.HTTPError:
            selected = None
        if selected:
            visible.insert(0, selected)

    render_conversation_sidebar(
        visible,
        active_session_id=session_id,
        current_limit=limit,
        has_more=has_more,
    )


def _history_panel_state(message: dict[str, Any]) -> tuple[str, str]:
    status = str(message.get("status") or "completed")
    if status == "failed":
        return "Falha na execução", "error"
    if status == "cancelled":
        return "Interrompido", "complete"
    return "Concluído", "complete"


def _render_history(client: FranqApiClient) -> None:
    for message in st.session_state.get("messages", []):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                execution_id = str(message.get("execution_id") or "")
                if execution_id:
                    activities = _historical_activities(client, execution_id)
                    if activities:
                        label, state = _history_panel_state(message)
                        ActivityPanel(
                            execution_id=execution_id,
                            label=label,
                            state=state,
                            activities=activities,
                        )

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


def _running_status_label(
    active: dict[str, Any],
    latest: ActivityPresentation | None = None,
) -> str:
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
            stored_activities = [
                activity_from_mapping(value)
                for value in active.get("activities", [])
                if isinstance(value, dict)
            ]
            panel = ActivityPanel(
                execution_id=execution_id,
                label=_running_status_label(active, latest_activity(active.get("activities", []))),
                state="complete" if response_started else "running",
                activities=stored_activities,
            )

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
                    latest: ActivityPresentation | None = None
                    for activity in update.new_activities:
                        latest = activity
                        panel.append(activity)

                    if update.content_changed:
                        message_view.markdown(str(active.get("content") or ""))

                    if update.transport_degraded:
                        realtime_degraded = True
                        if not active.get("response_started"):
                            panel.update(label="Reconectando à execução...", state="running")
                    elif active.get("response_started"):
                        panel.update(label="Análise concluída", state="complete")
                    elif update.terminal_status == "failed":
                        panel.update(label="Falha na execução", state="error")
                    else:
                        panel.update(
                            label=_running_status_label(active, latest),
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
                    panel.update(label="Reconectando à execução...", state="running")
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
                        panel.update(label="Reconectando à execução...", state="running")
                    elif active.get("response_started"):
                        panel.update(label="Análise concluída", state="complete")
                    return False

            _cache_execution_activities(execution_id, list(active.get("activities", [])))

            if terminal_status == "completed":
                final_answer = str(
                    active.get("content") or "Execução concluída sem conteúdo textual."
                )
                message_view.markdown(final_answer)
                render_result(active.get("result"))
                panel.update(label="Concluído", state="complete")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": final_answer,
                        "result": active.get("result"),
                        "execution_id": execution_id,
                        "status": "completed",
                    }
                )
                _clear_active_execution()
                return True

            if terminal_status == "cancelled":
                partial = str(active.get("content") or "")
                if partial:
                    message_view.markdown(partial)
                st.caption("Resposta interrompida pelo usuário.")
                panel.update(label="Interrompido", state="complete")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": partial,
                        "result": active.get("result"),
                        "execution_id": execution_id,
                        "status": "cancelled",
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
                panel.update(label="Falha na execução", state="error")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": final_error,
                        "result": None,
                        "execution_id": execution_id,
                        "status": "failed",
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


def _submit_question(
    client: FranqApiClient,
    session_id: str | None,
    question: str,
) -> None:
    try:
        if session_id is None:
            started = client.start_session(question=question)
            session = started.get("session")
            execution = started.get("execution")
            if not isinstance(session, dict) or not isinstance(execution, dict):
                raise ValueError("Invalid start-session response")
            session_id = str(session["id"])
            _set_session(session_id)
        else:
            execution = client.create_execution(session_id=session_id, question=question)
    except (httpx.HTTPError, ValueError) as exc:
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

    _handle_sidebar_actions(client)

    try:
        session_id = _ensure_session(client)
    except httpx.HTTPError as exc:
        st.error(f"Não foi possível conectar à API: {exc}")
        st.stop()

    with st.sidebar:
        st.subheader("Conversas")
        active_execution = st.session_state.get("active_execution_id")
        if st.button(
            "Nova conversa",
            use_container_width=True,
            disabled=bool(active_execution),
        ):
            _reset_to_new_conversation()
            st.rerun()
        _render_conversations(client, session_id)
        st.caption("Clique duas vezes para renomear. Clique com o botão direito para opções.")

    _render_history(client)

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
        finished = _observe_execution(client, execution_id, active_response_container)
        if finished:
            st.rerun()
        time.sleep(0.2)
        st.rerun()
        return

    if question:
        _submit_question(client, session_id, question)


if __name__ == "__main__":
    main()
