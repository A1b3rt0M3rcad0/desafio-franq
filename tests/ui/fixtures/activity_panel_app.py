import time

import streamlit as st

from package.ui.components.activity_panel import ActivityPanel
from package.ui.observation import ActivityPresentation


st.set_page_config(page_title="Activity Panel Fixture")


def _activity(index: int) -> ActivityPresentation:
    return ActivityPresentation(
        sequence=index,
        event_type="sql.generated" if index == 3 else "tool.completed",
        title=f"Atividade de validação {index}",
        detail=(
            "SELECT categoria, COUNT(*) AS quantidade FROM compras "
            "GROUP BY categoria ORDER BY quantidade DESC"
            if index == 3
            else f"detalhe da atividade {index}"
        ),
        status="success",
    )


panel = ActivityPanel(
    execution_id="fixture-execution",
    label="Preparando execução...",
    state="running",
    activities=[_activity(1)],
)

if st.button("Simular stream incremental"):
    for index in range(2, 21):
        panel.append(_activity(index))
        panel.update(label=f"Analisando evidências {index}...", state="running")
        time.sleep(0.03)
    panel.update(label="Análise concluída", state="complete")
