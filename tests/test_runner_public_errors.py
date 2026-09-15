from sqlalchemy.exc import IntegrityError

from package.runner.consumers.execution import _public_execution_error


def test_database_internals_are_not_exposed_as_chat_errors() -> None:
    error = IntegrityError("statement", {}, Exception("duplicate key"))
    assert _public_execution_error(error) == "Falha interna de persistência durante a execução."


def test_non_database_runtime_errors_keep_their_actionable_message() -> None:
    error = RuntimeError("provider indisponível")
    assert _public_execution_error(error) == "provider indisponível"
