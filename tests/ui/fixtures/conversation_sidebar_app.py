import streamlit as st

from package.ui.components.conversation_sidebar import render_conversation_sidebar


st.set_page_config(page_title="Conversation Sidebar Fixture", layout="centered")

SESSIONS = [
    {"id": "session-1", "title": "Me fale qual cliente mais compra"},
    {"id": "session-2", "title": "Qual cidade mais vende?"},
    {"id": "session-3", "title": "Qual cidade tem mais gasto e qual produto?"},
]

with st.sidebar:
    st.subheader("Conversas")
    render_conversation_sidebar(
        SESSIONS,
        active_session_id="session-1",
        current_limit=20,
        has_more=False,
    )

st.write("Fixture da sidebar de conversas")
