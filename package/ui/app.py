import time
from typing import Any

import httpx
import streamlit as st

from package.ui.client import FranqApiClient, ObservedFrame
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
    return {
        "execution_id": execution_id,
        "content": "",
        "phase": "pending",
        "result": None,
        "error": None,
        "cancel_requested": False,
    }


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


def _phase_label(phase: str) -> str | None:
    return {
        "pending": "Aguardando o agente...",
        "context": "Carregando contexto...",
        "reasoning": "Analisando a solicitação...",
        "skill": "Carregando conhecimento necessário...",
        "tool": "Consultando os dados...",
        "response_preparing": "Preparando a resposta...",
        "response_streaming": "Respondendo...",
        "finalizing": "Finalizando execução...",
        "cancel_requested": "Interrompendo a resposta...",
        "cancelled": "Interrompido",
        "completed": "Concluído",
        "failed": "Falha na execução",
    }.get(phase)


def _frame_phase(frame: ObservedFrame) -> str | None:
    if frame.type == "execution.state":
        return str(
            frame.payload.get("phase")
            or frame.payload.get("stage")
            or frame.payload.get("status")
            or ""
        )
    if frame.type == "execution.phase.changed":
        return str(frame.payload.get("phase") or "")
    if frame.type == "assistant.delta":
        return "response_streaming"
    if frame.type == "execution.cancel_requested":
        return "cancel_requested"
    if frame.type == "execution.cancelled":
        return "cancelled"
    if frame.type == "execution.completed":
        return "completed"
    if frame.type == "execution.failed":
        return "failed"
    return None


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


def _apply_state_answer(active: dict[str, Any], candidate: str) -> bool:
    current = str(active.get("content") or "")
    if not candidate:
        return False
    if candidate == current:
        return False
    if candidate.startswith(current):
        active["content"] = candidate
        return True
    if current.startswith(candidate):
        return False
    active["content"] = candidate
    return True


def _append_delta(active: dict[str, Any], content: str) -> bool:
    if not content:
        return False
    active["content"] = f"{active.get('content') or ''}{content}"
    return True


def _observe_execution(client: FranqApiClient, execution_id: str) -> bool:
    active = _active_response(execution_id)
    terminal_status: str | None = None

    with st.chat_message("assistant"):
        initial_phase = str(active.get("phase") or "pending")
        status_view = st.status(
            _phase_label(initial_phase) or "Execução em andamento...",
            expanded=False,
        )

        stop_disabled = initial_phase in {
            "cancel_requested",
            "cancelled",
            "completed",
            "failed",
        }
        if st.button(
            "■ Parar resposta",
            key=f"stop_execution_{execution_id}",
            disabled=stop_disabled,
        ):
            try:
                client.stop_execution(execution_id)
            except httpx.HTTPError as exc:
                st.error(f"Não foi possível interromper a execução: {exc}")
            else:
                active["cancel_requested"] = True
                active["phase"] = "cancel_requested"
                st.session_state.active_response = active
                status_view.update(label="Interrompendo a resposta...")

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

                phase = _frame_phase(frame)
                if phase:
                    active["phase"] = phase
                    label = _phase_label(phase)
                    if label:
                        status_view.update(label=label)

                content_changed = False
                if frame.type == "execution.state":
                    state_answer = frame.payload.get("partial_answer") or frame.payload.get("answer")
                    if state_answer:
                        content_changed = _apply_state_answer(active, str(state_answer))
                    if isinstance(frame.payload.get("result"), dict):
                        active["result"] = frame.payload["result"]
                    state_status = str(frame.payload.get("status") or "")
                    if state_status in {"completed", "failed", "cancelled"}:
                        terminal_status = state_status
                        active["error"] = frame.payload.get("error")
                elif frame.type == "assistant.delta":
                    content_changed = _append_delta(
                        active,
                        str(frame.payload.get("content") or ""),
                    )
                elif frame.type == "execution.completed":
                    terminal_status = "completed"
                    final_answer = str(frame.payload.get("answer") or "")
                    if final_answer:
                        content_changed = _apply_state_answer(active, final_answer) or content_changed
                    if isinstance(frame.payload.get("result"), dict):
                        active["result"] = frame.payload["result"]
                elif frame.type == "execution.cancelled":
                    terminal_status = "cancelled"
                elif frame.type == "execution.failed":
                    terminal_status = "failed"
                    active["error"] = str(frame.payload.get("error") or "erro desconhecido")
                elif frame.type == "execution.realtime_unavailable":
                    status_view.update(label="Recuperando estado da execução...")

                st.session_state.active_response = active
                if content_changed:
                    message_view.markdown(str(active.get("content") or ""))
        except (httpx.HTTPError, ValueError) as exc:
            status_view.update(label="Reconectando à execução...")
            durable_status, durable_answer, durable_result, durable_error = _refresh_durable_result(
                client,
                execution_id,
                current_answer=str(active.get("content") or ""),
                current_result=active.get("result"),
            )
            if durable_answer:
                _apply_state_answer(active, durable_answer)
                message_view.markdown(str(active.get("content") or ""))
            if durable_result is not None:
                active["result"] = durable_result
            active["error"] = durable_error or active.get("error")
            terminal_status = durable_status if durable_status in {"completed", "failed", "cancelled"} else None
            st.session_state.active_response = active
            if terminal_status is None:
                st.caption(f"Conexão realtime interrompida; tentando reanexar. ({exc})")
                return False

        if terminal_status not in {"completed", "failed", "cancelled"}:
            status_view.update(label="Sincronizando estado final...")
            for _ in range(40):
                durable_status, durable_answer, durable_result, durable_error = _refresh_durable_result(
                    client,
                    execution_id,
                    current_answer=str(active.get("content") or ""),
                    current_result=active.get("result"),
                )
                if durable_answer:
                    _apply_state_answer(active, durable_answer)
                    message_view.markdown(str(active.get("content") or ""))
                if durable_result is not None:
                    active["result"] = durable_result
                active["error"] = durable_error or active.get("error")
                if durable_status in {"completed", "failed", "cancelled"}:
                    terminal_status = durable_status
                    break
                time.sleep(0.25)

        if terminal_status == "completed":
            final_answer = str(active.get("content") or "Execução concluída sem conteúdo textual.")
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
    mount_sticky_chat_scroll()

    query_execution = _query_value("execution_id")
    active_execution = query_execution or st.session_state.get("active_execution_id")
    if active_execution:
        st.session_state.active_execution_id = active_execution
        st.query_params["execution_id"] = active_execution
        if not _observe_execution(client, active_execution):
            time.sleep(0.2)
            st.rerun()

    question = st.chat_input(
        "Pergunte algo sobre os dados...",
        disabled=bool(st.session_state.get("active_execution_id")),
    )
    if not question:
        return

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


if __name__ == "__main__":
    main()
