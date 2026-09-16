from threading import RLock
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

from package.ui.rich_content import (
    InvalidVisualizationBlock,
    MarkdownBlock,
    PendingVisualizationBlock,
    VisualizationBlock,
    parse_rich_content,
    strip_visualization_blocks,
)
from package.ui.visualization import PreparedVisualization, prepare_visualization


_PLOT_LOCK = RLock()


def render_rich_content(content: str, *, allow_partial: bool = False) -> int:
    """Render assistant rich content.

    While the answer is still streaming, only narrative Markdown is rendered.
    Visualization directives are withheld until the final render so completed
    charts are not rebuilt for every subsequent model delta.
    """
    if allow_partial:
        narrative = strip_visualization_blocks(content)
        if narrative:
            st.markdown(narrative)
        return 0

    rendered_visualizations = 0
    for block in parse_rich_content(content, allow_partial=False):
        if isinstance(block, MarkdownBlock):
            if block.content.strip():
                st.markdown(block.content)
        elif isinstance(block, VisualizationBlock):
            render_visualization(block.visualization)
            rendered_visualizations += 1
        elif isinstance(block, PendingVisualizationBlock):
            st.caption("Preparando visualização...")
        elif isinstance(block, InvalidVisualizationBlock):
            st.caption("Não foi possível renderizar uma visualização desta resposta.")
    return rendered_visualizations


def render_result(result: dict[str, Any] | None) -> None:
    """Backward-compatible renderer for the original result visualization contract."""
    visualization = prepare_visualization(result)
    if visualization is not None:
        render_visualization(visualization)


def render_visualization(visualization: PreparedVisualization) -> None:
    frame = pd.DataFrame(list(visualization.rows))
    if visualization.type == "table":
        if visualization.title:
            st.markdown(f"**{visualization.title}**")
        st.dataframe(frame, use_container_width=True, hide_index=True)
        return

    with _PLOT_LOCK:
        fig, ax = plt.subplots(figsize=(10, 5))
        try:
            _render_chart(ax=ax, frame=frame, visualization=visualization)
            fig.tight_layout()
            st.pyplot(fig, width="stretch")
        finally:
            plt.close(fig)


def _render_chart(*, ax, frame: pd.DataFrame, visualization: PreparedVisualization) -> None:
    if visualization.type == "bar":
        _render_bar(ax=ax, frame=frame, visualization=visualization)
    elif visualization.type == "line":
        _render_line(ax=ax, frame=frame, visualization=visualization)
    elif visualization.type == "scatter":
        _render_scatter(ax=ax, frame=frame, visualization=visualization)
    else:
        raise ValueError(f"Unsupported chart type: {visualization.type}")

    if visualization.title:
        ax.set_title(visualization.title)

    if visualization.type == "bar" and visualization.orientation == "horizontal":
        if visualization.y_label:
            ax.set_xlabel(visualization.y_label)
        if visualization.x_label:
            ax.set_ylabel(visualization.x_label)
    else:
        if visualization.x_label:
            ax.set_xlabel(visualization.x_label)
        if visualization.y_label:
            ax.set_ylabel(visualization.y_label)


def _render_bar(*, ax, frame: pd.DataFrame, visualization: PreparedVisualization) -> None:
    x = _required_x(visualization)
    y = list(visualization.y)

    if len(y) == 1:
        if visualization.orientation == "horizontal":
            sns.barplot(
                data=frame,
                x=y[0],
                y=x,
                hue=visualization.hue,
                errorbar=None,
                ax=ax,
            )
        else:
            sns.barplot(
                data=frame,
                x=x,
                y=y[0],
                hue=visualization.hue,
                errorbar=None,
                ax=ax,
            )
        return

    melted = _melt_series(frame=frame, x=x, y=y)
    if visualization.orientation == "horizontal":
        sns.barplot(
            data=melted,
            x="_value",
            y=x,
            hue="_series",
            errorbar=None,
            ax=ax,
        )
    else:
        sns.barplot(
            data=melted,
            x=x,
            y="_value",
            hue="_series",
            errorbar=None,
            ax=ax,
        )


def _render_line(*, ax, frame: pd.DataFrame, visualization: PreparedVisualization) -> None:
    x = _required_x(visualization)
    y = list(visualization.y)

    if len(y) == 1:
        sns.lineplot(
            data=frame,
            x=x,
            y=y[0],
            hue=visualization.hue,
            estimator=None,
            errorbar=None,
            sort=False,
            marker="o",
            ax=ax,
        )
        return

    melted = _melt_series(frame=frame, x=x, y=y)
    sns.lineplot(
        data=melted,
        x=x,
        y="_value",
        hue="_series",
        estimator=None,
        errorbar=None,
        sort=False,
        marker="o",
        ax=ax,
    )


def _render_scatter(*, ax, frame: pd.DataFrame, visualization: PreparedVisualization) -> None:
    x = _required_x(visualization)
    sns.scatterplot(
        data=frame,
        x=x,
        y=visualization.y[0],
        hue=visualization.hue,
        ax=ax,
    )


def _melt_series(*, frame: pd.DataFrame, x: str, y: list[str]) -> pd.DataFrame:
    return frame.melt(
        id_vars=[x],
        value_vars=y,
        var_name="_series",
        value_name="_value",
    )


def _required_x(visualization: PreparedVisualization) -> str:
    if visualization.x is None:
        raise ValueError("Chart visualization requires an x field")
    return visualization.x
