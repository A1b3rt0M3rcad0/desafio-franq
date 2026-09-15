from package.ui.rich_content import (
    InvalidVisualizationBlock,
    MarkdownBlock,
    PendingVisualizationBlock,
    VisualizationBlock,
    parse_rich_content,
    strip_visualization_blocks,
)


def _bar_block(title: str, a: int, b: int) -> str:
    return f'''```visualization
{{"version":1,"type":"bar","title":"{title}","data":{{"columns":["canal","valor"],"rows":[{{"canal":"A","valor":{a}}},{{"canal":"B","valor":{b}}}]}},"x":"canal","y":["valor"]}}
```'''


def test_parser_preserves_text_and_multiple_visualizations_in_order() -> None:
    content = (
        "Primeira análise.\n\n"
        + _bar_block("Primeiro", 10, 5)
        + "\n\nInterpretação intermediária.\n\n"
        + _bar_block("Segundo", 7, 3)
        + "\n\nConclusão final."
    )

    blocks = parse_rich_content(content)

    assert [type(block) for block in blocks] == [
        MarkdownBlock,
        VisualizationBlock,
        MarkdownBlock,
        VisualizationBlock,
        MarkdownBlock,
    ]
    visualizations = [block for block in blocks if isinstance(block, VisualizationBlock)]
    assert [block.visualization.title for block in visualizations] == ["Primeiro", "Segundo"]


def test_partial_visualization_is_hidden_while_streaming() -> None:
    content = "Análise pronta.\n\n```visualization\n{\"version\":1,\"type\":\"bar\""

    blocks = parse_rich_content(content, allow_partial=True)

    assert isinstance(blocks[0], MarkdownBlock)
    assert blocks[0].content.strip() == "Análise pronta."
    assert isinstance(blocks[1], PendingVisualizationBlock)
    assert all("version" not in getattr(block, "content", "") for block in blocks)


def test_partial_opening_fence_is_not_exposed_as_markdown() -> None:
    blocks = parse_rich_content("Texto antes.\n```visua", allow_partial=True)

    assert isinstance(blocks[0], MarkdownBlock)
    assert blocks[0].content.strip() == "Texto antes."
    assert isinstance(blocks[1], PendingVisualizationBlock)


def test_regular_json_code_block_is_plain_markdown() -> None:
    content = 'Exemplo:\n```json\n{"a": 1}\n```'

    blocks = parse_rich_content(content)

    assert blocks == (MarkdownBlock(content=content),)


def test_closed_invalid_visualization_does_not_break_surrounding_text() -> None:
    content = "Antes.\n```visualization\n{invalid}\n```\nDepois."

    blocks = parse_rich_content(content)

    assert isinstance(blocks[0], MarkdownBlock)
    assert isinstance(blocks[1], InvalidVisualizationBlock)
    assert isinstance(blocks[2], MarkdownBlock)
    assert blocks[2].content.strip() == "Depois."


def test_parser_enforces_visualization_limit() -> None:
    content = "\n".join(_bar_block(str(index), index + 1, index) for index in range(6))

    blocks = parse_rich_content(content)

    assert sum(isinstance(block, VisualizationBlock) for block in blocks) == 5
    assert sum(isinstance(block, InvalidVisualizationBlock) for block in blocks) == 1


def test_strip_visualization_blocks_keeps_only_narrative_text() -> None:
    content = "Antes.\n\n" + _bar_block("Gráfico", 10, 5) + "\n\nDepois."

    stripped = strip_visualization_blocks(content)

    assert "```visualization" not in stripped
    assert "Antes." in stripped
    assert "Depois." in stripped
