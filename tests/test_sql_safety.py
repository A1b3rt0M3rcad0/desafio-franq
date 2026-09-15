import pytest

from package.agent.tools.database.safety import UnsafeQueryError, validate_read_only_sql


def test_accepts_select() -> None:
    assert validate_read_only_sql("SELECT * FROM clientes;") == "SELECT * FROM clientes"


def test_accepts_cte() -> None:
    sql = "WITH totals AS (SELECT 1 AS n) SELECT n FROM totals"
    assert validate_read_only_sql(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM clientes",
        "DROP TABLE clientes",
        "SELECT 1; SELECT 2",
        "PRAGMA table_info(clientes)",
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)
