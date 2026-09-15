from enum import StrEnum

import streamlit as st


class ComposerMode(StrEnum):
    SEND = "send"
    STOP = "stop"


def composer_mode(active_execution_id: str | None) -> ComposerMode:
    return ComposerMode.STOP if active_execution_id else ComposerMode.SEND


def action_label(mode: ComposerMode) -> str:
    return "■" if mode == ComposerMode.STOP else "➤"


def render_chat_composer(
    *,
    active_execution_id: str | None,
) -> tuple[str | None, bool]:
    """Render one composer action slot that switches Send <-> Stop.

    Returns (question, stop_requested). Only one value can be active per render.
    """
    mode = composer_mode(active_execution_id)
    st.markdown(
        """
        <style>
        div[data-testid="stForm"] {
            position: sticky;
            bottom: 0;
            z-index: 20;
            background: var(--background-color);
            padding-top: 0.35rem;
            padding-bottom: 0.5rem;
            border: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.form("chat_composer", clear_on_submit=True, border=False):
        input_column, action_column = st.columns([12, 1], vertical_alignment="bottom")
        with input_column:
            question = st.text_input(
                "Mensagem",
                placeholder=(
                    "Agente respondendo..."
                    if mode == ComposerMode.STOP
                    else "Pergunte algo sobre os dados..."
                ),
                disabled=mode == ComposerMode.STOP,
                label_visibility="collapsed",
            )
        with action_column:
            submitted = st.form_submit_button(
                action_label(mode),
                use_container_width=True,
                help=(
                    "Parar resposta"
                    if mode == ComposerMode.STOP
                    else "Enviar mensagem"
                ),
            )

    if not submitted:
        return None, False
    if mode == ComposerMode.STOP:
        return None, True

    normalized = question.strip()
    return (normalized or None), False
