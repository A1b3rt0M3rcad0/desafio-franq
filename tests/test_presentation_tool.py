import pytest
from pydantic import ValidationError

from package.agent.tools.contracts import ToolInvocationResult
from package.agent.tools.presentation.tool import PresentationTool


@pytest.mark.asyncio
async def test_presentation_tool_accepts_valid_bar_chart() -> None:
    tool = PresentationTool()

    result = await tool.invoke(
        {
            "data": {
                "columns": [" canal ", "reclamacoes"],
                "rows": [
                    {" canal ": "Telefone", "reclamacoes": 19},
                    {" canal ": "Chat", "reclamacoes": 18},
                ],
            },
            "visualization": {
                "type": "bar",
                "title": " Reclamações não resolvidas ",
                "x": " canal ",
                "y": ["reclamacoes"],
                "x_label": " Canal ",
                "y_label": " Reclamações ",
            },
        }
    )

    assert isinstance(result, ToolInvocationResult)
    assert result.observation == {
        "accepted": True,
        "type": "bar",
        "title": "Reclamações não resolvidas",
        "row_count": 2,
    }
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.kind == "presentation"
    assert artifact.payload["data"]["columns"] == ["canal", "reclamacoes"]
    assert artifact.payload["visualization"]["x"] == "canal"
    assert artifact.payload["visualization"]["y"] == ["reclamacoes"]


@pytest.mark.asyncio
async def test_presentation_tool_rejects_unknown_chart_field() -> None:
    tool = PresentationTool()

    with pytest.raises(ValidationError, match="does not exist in the data"):
        await tool.invoke(
            {
                "data": {
                    "columns": ["canal", "reclamacoes"],
                    "rows": [{"canal": "Telefone", "reclamacoes": 19}],
                },
                "visualization": {
                    "type": "bar",
                    "x": "canal",
                    "y": ["total_inexistente"],
                },
            }
        )


@pytest.mark.asyncio
async def test_presentation_tool_requires_preaggregated_bar_grain() -> None:
    tool = PresentationTool()

    with pytest.raises(ValidationError, match="already be aggregated"):
        await tool.invoke(
            {
                "data": {
                    "columns": ["canal", "reclamacoes"],
                    "rows": [
                        {"canal": "Telefone", "reclamacoes": 10},
                        {"canal": "Telefone", "reclamacoes": 9},
                    ],
                },
                "visualization": {
                    "type": "bar",
                    "x": "canal",
                    "y": ["reclamacoes"],
                },
            }
        )


@pytest.mark.asyncio
async def test_presentation_tool_rejects_non_numeric_scatter_axis() -> None:
    tool = PresentationTool()

    with pytest.raises(ValidationError, match="must contain numeric values"):
        await tool.invoke(
            {
                "data": {
                    "columns": ["cliente", "valor"],
                    "rows": [{"cliente": "A", "valor": 10}],
                },
                "visualization": {
                    "type": "scatter",
                    "x": "cliente",
                    "y": ["valor"],
                },
            }
        )


@pytest.mark.asyncio
async def test_presentation_tool_accepts_table_without_axes() -> None:
    tool = PresentationTool()

    result = await tool.invoke(
        {
            "data": {
                "columns": ["estado", "clientes"],
                "rows": [{"estado": "SC", "clientes": 13}],
            },
            "visualization": {
                "type": "table",
                "title": "Clientes por estado",
            },
        }
    )

    assert result.artifacts[0].payload["visualization"]["type"] == "table"
