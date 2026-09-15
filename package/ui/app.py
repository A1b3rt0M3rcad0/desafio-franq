import time
from collections.abc import Iterator
from typing import Any

import httpx
import streamlit as st

from package.ui.client import FranqApiClient, ObservedFrame
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


def _clear_active_execution() -> None:
    st.session_state.active_execution_id = None
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
        elif status in {"pending", "running"}:
            active_execution_id = execution_id

    st.session_state.messages = messages
    st.session_state.active_execution_id = active_execution_id
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
            st.markdown(message["content"])
            if message["role"] == "assistant":
                render_result(message.get("result"))


def _status_label(frame: ObservedFrame) -> str | None:
    if frame.type == "execution.state":
        stage = str(frame.payload.get("stage") or frame.payload.get("status") or "")
        return {
            "pending": "Aguardando o agente...",
            "context": "Carregando contexto...",
            "agent": "Analisando a solicitação...",
            "reasoning": "Analisando a solicitação...",
            "skill": "Carregando conhecimento necessário...",
            "tool": "Consultando os dados...",
            "answer": "Preparando a resposta...",
            "completed": "Concluído",
            "failed": "Falha na execução",
        }.get(stage)
    if frame.type == "context.loaded":
        return "Contexto carregado"
    if frame.type == "agent.iteration.started":
        return "Analisando a solicitação..."
    if frame.type == "skill.requested":
        return "Carregando conhecimento necessário..."
    if frame.type == "tool.started":
        tool = frame.payload.get("tool")
        return f"Executando {tool}..." if tool else "Executando ferramenta..."
    if frame.type == "tool.failed":
        return "Ajustando a investigação após uma falha..."
    if frame.type == "tool.completed":
        return "Dados coletados. Continuando análise..."
    if frame.type == "answer.generated":
        return "Preparando a resposta..."
    if frame.type == "execution.completed":
        return "Concluído"
    if frame.type == "execution.failed":
        return "Falha na execução"
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


def _observe_execution(client: FranqApiClient, execution_id: str) -> bool:
    answer = ""
    displayed_answer = ""
    result: dict[str, Any] | None = None
    terminal_status: str | None = None
    error: str | None = None

    with st.chat_message("assistant"):
        status_view = st.status("Aguardando o agente...", expanded=False)

        def answer_stream() -> Iterator[str]:
            nonlocal answer, displayed_answer, result, terminal_status, error
            for frame in client.observe_execution(
                execution_id,
                last_sequence=st.session_state.get("last_sequence"),
            ):
                if frame.sequence is not None:
                    st.session_state.last_sequence = frame.sequence

                label = _status_label(frame)
                if label:
                    status_view.update(label=label)

                if frame.type == "execution.state":
                    state_answer = frame.payload.get("partial_answer") or frame.payload.get("answer")
                    if state_answer:
                        candidate = str(state_answer)
                        if not answer:
                            answer = candidate
                            displayed_answer += candidate
                            yield candidate
                        elif candidate.startswith(answer) and len(candidate) > len(answer):
                            suffix = candidate[len(answer) :]
                            answer = candidate
                            displayed_answer += suffix
                            yield suffix
                    if isinstance(frame.payload.get("result"), dict):
                        result = frame.payload["result"]
                    state_status = str(frame.payload.get("status") or "")
                    if state_status in {"completed", "failed"}:
                        terminal_status = state_status
                        error = frame.payload.get("error")
                elif frame.type == "assistant.delta":
                    content = str(frame.payload.get("content") or "")
                    if content:
                        answer += content
                        displayed_answer += content
                        yield content
                elif frame.type == "execution.completed":
                    terminal_status = "completed"
                    final_answer = str(frame.payload.get("answer") or answer)
                    if final_answer and not answer:
                        answer = final_answer
                        displayed_answer += final_answer
                        yield final_answer
                    elif final_answer.startswith(answer) and len(final_answer) > len(answer):
                        suffix = final_answer[len(answer) :]
                        answer = final_answer
                        displayed_answer += suffix
                        yield suffix
                    else:
                        answer = final_answer or answer
                    if isinstance(frame.payload.get("result"), dict):
                        result = frame.payload["result"]
                elif frame.type == "execution.failed":
                    terminal_status = "failed"
                    error = str(frame.payload.get("error") or "erro desconhecido")
                elif frame.type == "execution.realtime_unavailable":
                    status_view.update(label="Recuperando estado durável...")

        try:
            st.write_stream(answer_stream())
        except (httpx.HTTPError, ValueError) as exc:
            status_view.update(label="Recuperando estado da execução...")
            terminal_status, answer, result, durable_error = _refresh_durable_result(
                client,
                execution_id,
                current_answer=answer,
                current_result=result,
            )
            error = durable_error or error
            if terminal_status is None:
                st.error(f"Não foi possível acompanhar a execução: {exc}")
                return False

        if terminal_status not in {"completed", "failed"}:
            status_view.update(label="Finalizando execução...")
            for _ in range(40):
                durable_status, durable_answer, durable_result, durable_error = (
                    _refresh_durable_result(
                        client,
                        execution_id,
                        current_answer=answer,
                        current_result=result,
                    )
                )
                answer = durable_answer
                result = durable_result
                error = durable_error or error
                if durable_status in {"completed", "failed"}:
                    terminal_status = durable_status
                    break
                time.sleep(0.25)

        if terminal_status == "completed":
            final_answer = answer or "Execução concluída sem conteúdo textual."
            if not displayed_answer:
                st.markdown(final_answer)
            render_result(result)
            status_view.update(label="Concluído", state="complete")
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": final_answer,
                    "result": result,
                    "execution_id": execution_id,
                }
            )
            _clear_active_execution()
            return True

        if terminal_status == "failed":
            final_error = f"Não foi possível concluir a execução: {error or 'erro desconhecido'}"
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

        status_view.update(label="Execução ainda em andamento", state="running")
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

    query_execution = _query_value("execution_id")
    active_execution = query_execution or st.session_state.get("active_execution_id")
    if active_execution:
        st.session_state.active_execution_id = active_execution
        st.query_params["execution_id"] = active_execution
        if not _observe_execution(client, active_execution):
            time.sleep(0.5)
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
    with st.chat_message("user"):
        st.markdown(question)

    st.session_state.active_execution_id = execution_id
    st.session_state.last_sequence = None
    st.query_params["execution_id"] = execution_id
    if not _observe_execution(client, execution_id):
        time.sleep(0.5)
        st.rerun()


if __name__ == "__main__":
    main()
