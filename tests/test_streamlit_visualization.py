from package.ui.visualization import extract_rows, prepare_visualization


def test_prepare_bar_visualization_from_columns_and_rows() -> None:
    result = {
        "data": {
            "columns": ["estado", "clientes"],
            "rows": [["SP", 18], ["SC", 13]],
        },
        "visualization": {
            "type": "bar",
            "title": "Clientes por estado",
            "x": "estado",
            "y": ["clientes"],
        },
    }

    visualization = prepare_visualization(result)

    assert visualization is not None
    assert visualization.type == "bar"
    assert visualization.x == "estado"
    assert visualization.y == ("clientes",)
    assert visualization.rows[0] == {"estado": "SP", "clientes": 18}


def test_prepare_visualization_defaults_to_table_when_agent_returns_rows_only() -> None:
    result = {
        "data": [
            {"categoria": "A", "total": 10},
            {"categoria": "B", "total": 5},
        ]
    }

    visualization = prepare_visualization(result)

    assert visualization is not None
    assert visualization.type == "table"
    assert len(visualization.rows) == 2


def test_invalid_chart_columns_degrade_to_table_instead_of_crashing() -> None:
    result = {
        "data": [{"categoria": "A", "total": 10}],
        "visualization": {
            "type": "line",
            "x": "mes_inexistente",
            "y": "total",
        },
    }

    visualization = prepare_visualization(result)

    assert visualization is not None
    assert visualization.type == "table"


def test_extract_rows_supports_top_level_columns_and_rows() -> None:
    rows = extract_rows(
        {
            "columns": ["canal", "reclamacoes"],
            "rows": [["email", 3], ["telefone", 5]],
        }
    )

    assert rows == [
        {"canal": "email", "reclamacoes": 3},
        {"canal": "telefone", "reclamacoes": 5},
    ]


def test_visualization_type_none_does_not_render_data() -> None:
    result = {
        "data": [{"a": 1}],
        "visualization": {"type": "none"},
    }

    assert prepare_visualization(result) is None
