from matplotlib.figure import Figure

from package.ui import rendering
from package.ui.rich_content import parse_rich_content
from package.ui.visualization import prepare_inline_visualization


def _bar_payload(title: str) -> dict:
    return {
        "version": 1,
        "type": "bar",
        "title": title,
        "data": {
            "columns": ["canal", "reclamacoes"],
            "rows": [
                {"canal": "Telefone", "reclamacoes": 19},
                {"canal": "Chat", "reclamacoes": 18},
                {"canal": "E-mail", "reclamacoes": 14},
            ],
        },
        "x": "canal",
        "y": ["reclamacoes"],
        "x_label": "Canal",
        "y_label": "Reclamações",
        "orientation": "vertical",
    }


def _rich_answer() -> str:
    return '''Primeiro ponto.

```visualization
{"version":1,"type":"bar","title":"Primeiro gráfico","data":{"columns":["canal","reclamacoes"],"rows":[{"canal":"Telefone","reclamacoes":19},{"canal":"Chat","reclamacoes":18}]},"x":"canal","y":["reclamacoes"]}
```

Segundo ponto.

```visualization
{"version":1,"type":"bar","title":"Segundo gráfico","data":{"columns":["canal","reclamacoes"],"rows":[{"canal":"Telefone","reclamacoes":12},{"canal":"Chat","reclamacoes":9}]},"x":"canal","y":["reclamacoes"]}
```

Conclusão.'''


def test_prepare_inline_visualization_builds_bar_contract() -> None:
    visualization = prepare_inline_visualization(_bar_payload("Reclamações não resolvidas"))

    assert visualization.type == "bar"
    assert visualization.x == "canal"
    assert visualization.y == ("reclamacoes",)
    assert visualization.x_label == "Canal"
    assert visualization.y_label == "Reclamações"


def test_render_visualization_builds_matplotlib_figure_with_seaborn(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def capture_figure(fig, *, width):
        captured["fig"] = fig
        captured["width"] = width

    monkeypatch.setattr(rendering.st, "pyplot", capture_figure)

    visualization = prepare_inline_visualization(_bar_payload("Reclamações não resolvidas"))
    rendering.render_visualization(visualization)

    assert isinstance(captured["fig"], Figure)
    assert captured["width"] == "stretch"
    figure = captured["fig"]
    assert len(figure.axes) == 1
    axis = figure.axes[0]
    assert axis.get_title() == "Reclamações não resolvidas"
    assert axis.get_xlabel() == "Canal"
    assert axis.get_ylabel() == "Reclamações"
    assert len(axis.patches) == 3


def test_render_rich_content_renders_two_inline_charts(monkeypatch) -> None:
    figures: list[Figure] = []
    markdown: list[str] = []

    monkeypatch.setattr(rendering.st, "pyplot", lambda fig, *, width: figures.append(fig))
    monkeypatch.setattr(rendering.st, "markdown", lambda content: markdown.append(content))
    monkeypatch.setattr(rendering.st, "caption", lambda content: None)

    rendered = rendering.render_rich_content(_rich_answer())

    assert rendered == 2
    assert len(figures) == 2
    assert figures[0].axes[0].get_title() == "Primeiro gráfico"
    assert figures[1].axes[0].get_title() == "Segundo gráfico"
    assert any("Primeiro ponto" in value for value in markdown)
    assert any("Conclusão" in value for value in markdown)
    assert len(parse_rich_content(_rich_answer())) == 5


def test_streaming_rich_content_defers_visualizations(monkeypatch) -> None:
    figures: list[Figure] = []
    markdown: list[str] = []

    monkeypatch.setattr(rendering.st, "pyplot", lambda fig, *, width: figures.append(fig))
    monkeypatch.setattr(rendering.st, "markdown", lambda content: markdown.append(content))

    rendered = rendering.render_rich_content(
        _rich_answer() + "\n\nTexto que continua chegando depois dos gráficos.",
        allow_partial=True,
    )

    assert rendered == 0
    assert figures == []
    assert len(markdown) == 1
    assert "Primeiro ponto" in markdown[0]
    assert "Segundo ponto" in markdown[0]
    assert "Conclusão" in markdown[0]
    assert "Texto que continua chegando" in markdown[0]
    assert "```visualization" not in markdown[0]
    assert "Primeiro gráfico" not in markdown[0]
    assert "Segundo gráfico" not in markdown[0]
