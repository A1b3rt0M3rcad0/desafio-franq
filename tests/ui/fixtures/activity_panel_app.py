import streamlit as st

from package.ui.components.activity_panel import ActivityPanel
from package.ui.observation import ActivityPresentation


st.set_page_config(page_title="Activity Panel Fixture")

count = int(st.session_state.get("activity_count", 20))
if st.button("Adicionar evento"):
    count += 1
    st.session_state.activity_count = count

activities = [
    ActivityPresentation(
        sequence=index,
        event_type="tool.completed",
        title=f"Atividade de validação {index}",
        detail=(
            "SELECT categoria, COUNT(*) AS quantidade FROM compras "
            "GROUP BY categoria ORDER BY quantidade DESC"
            if index == 3
            else f"detalhe da atividade {index}"
        ),
        status="success",
    )
    for index in range(1, count + 1)
]

ActivityPanel(
    execution_id="fixture-execution",
    label="Análise concluída",
    state="complete",
    activities=activities,
)
