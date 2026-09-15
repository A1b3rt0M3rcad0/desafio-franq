from typing import Any

import pandas as pd
import streamlit as st

from package.ui.visualization import prepare_visualization


def render_result(result: dict[str, Any] | None) -> None:
    visualization = prepare_visualization(result)
    if visualization is None:
        return

    if visualization.title:
        st.markdown(f"**{visualization.title}**")

    frame = pd.DataFrame(list(visualization.rows))
    if visualization.type == "table":
        st.dataframe(frame, use_container_width=True, hide_index=True)
        return

    y = list(visualization.y)
    if visualization.type == "bar":
        st.bar_chart(frame, x=visualization.x, y=y, use_container_width=True)
    elif visualization.type == "line":
        st.line_chart(frame, x=visualization.x, y=y, use_container_width=True)
    elif visualization.type == "scatter":
        st.scatter_chart(frame, x=visualization.x, y=y[0], use_container_width=True)
