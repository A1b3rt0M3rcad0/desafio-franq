import pytest

from package.agent.session_title import build_session_title


def test_short_question_becomes_title_without_modification() -> None:
    assert build_session_title("Quais estados mais compraram em maio?") == (
        "Quais estados mais compraram em maio?"
    )


def test_title_normalizes_whitespace_and_truncates_with_ellipsis() -> None:
    question = (
        "  Quero   descobrir\nquais foram os estados brasileiros com maior quantidade "
        "de clientes comprando pelo aplicativo durante o mês de maio.  "
    )

    title = build_session_title(question, max_length=48)

    assert len(title) <= 48
    assert title.endswith("...")
    assert "  " not in title
    assert "\n" not in title


def test_empty_question_is_rejected() -> None:
    with pytest.raises(ValueError, match="question"):
        build_session_title("   ")
