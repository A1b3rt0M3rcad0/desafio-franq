from matplotlib.figure import Figure

from package.ui import rendering
from package.ui.visualization import prepare_visualization


def _bar_result() -> dict:
    return {
        "iterations": 3,
        "presentation": {
            "version": 1,
            "data": {
                "columns": ["canal", "reclamacoes"],
                "rows": [
                    {"canal": "Telefone", "reclamacoes": 19},
                    {"canal": "Chat", "reclamacoes": 18},
                    {"canal": "E-mail", "reclamacoes": 14},
                ],
            },
            "visualization": {
                "type": "bar",
                "title": "Reclamações não resolvidas por canal",
                "x": "canal",
                "y": ["reclamacoes"],
                "x_label": "Canal",
                "y_label": "Reclamações",
                "orientation": "vertical",
            },
        },
    }


def test_prepare_visualization_reads_nested_execution_presentation() -> None:
    visualization = prepare_visualization(_bar_result())

    assert visualization is not None
    assert visualization.type == "bar"
    assert visualization.x == "canal"
    assert visualization.y == ("reclamacoes",)
    assert visualization.x_label == "Canal"
    assert visualization.y_label == "Reclamações"


def test_render_result_builds_matplotlib_figure_with_seaborn(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def capture_figure(fig, *, width):
        captured["fig"] = fig
        captured["width"] = width

    monkeypatch.setattr(rendering.st, "pyplot", capture_figure)

    rendering.render_result(_bar_result())

    assert isinstance(captured["fig"], Figure)
    assert captured["width"] == "stretch"
    figure = captured["fig"]
    assert len(figure.axes) == 1
    axis = figure.axes[0]
    assert axis.get_title() == "Reclamações não resolvidas por canal"
    assert axis.get_xlabel() == "Canal"
    assert axis.get_ylabel() == "Reclamações"
    assert len(axis.patches) == 3
