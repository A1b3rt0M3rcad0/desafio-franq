from package.agent.prompt.system import SYSTEM_PROMPT, SystemPrompt


def test_system_prompt_is_structured_and_rendered_in_pt_br() -> None:
    assert isinstance(SYSTEM_PROMPT, SystemPrompt)
    assert SYSTEM_PROMPT.name == "Assistente Virtual de Dados"
    assert SYSTEM_PROMPT.description.strip()
    assert SYSTEM_PROMPT.objective.strip()

    rendered = SYSTEM_PROMPT.render()

    assert "# Identidade do agente" in rendered
    assert "## Descrição" in rendered
    assert "## Objetivo" in rendered
    assert SYSTEM_PROMPT.name in rendered
    assert "perguntas de negócio" in rendered
    assert "Não invente" in rendered
    assert "```visualization" in rendered
    assert '"type": "bar"' in rendered
    assert "até 5 blocos de visualização" in rendered


def test_system_prompt_strip_returns_rendered_prompt() -> None:
    assert SYSTEM_PROMPT.strip() == SYSTEM_PROMPT.render().strip()
