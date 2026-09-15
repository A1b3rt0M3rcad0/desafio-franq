from pathlib import Path

import pytest

from package.agent.composer.agent import compose_default_skills
from package.agent.skills.reader import SKILL_SEPARATOR, SkillReader
from package.agent.skills.registry import SkillRegistry


def _write_skill(path: Path, *, name: str = "test", description: str = "Descrição") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            f"{SKILL_SEPARATOR}\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"{SKILL_SEPARATOR}\n\n"
            "# Instruções\n\n"
            "CONTEÚDO COMPLETO DA SKILL\n"
        ),
        encoding="utf-8",
    )


def test_skill_reader_discovers_only_metadata_until_load(tmp_path: Path) -> None:
    path = tmp_path / "test" / "SKILL.md"
    _write_skill(path)

    reader = SkillReader()
    skill = reader.read(path)

    assert skill.name == "test"
    assert skill.description == "Descrição"
    assert skill.path == path


@pytest.mark.asyncio
async def test_file_skill_loads_body_on_demand(tmp_path: Path) -> None:
    path = tmp_path / "test" / "SKILL.md"
    _write_skill(path)

    skill = SkillReader().read(path)
    body = await skill.load()

    assert body.startswith("# Instruções")
    assert "CONTEÚDO COMPLETO DA SKILL" in body
    assert "name: test" not in body
    assert SKILL_SEPARATOR not in body


def test_skill_reader_rejects_invalid_header(tmp_path: Path) -> None:
    path = tmp_path / "broken" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("name: broken\ndescription: inválida\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must start"):
        SkillReader().read(path)


def test_skill_registry_rejects_duplicate_names(tmp_path: Path) -> None:
    first_path = tmp_path / "first" / "SKILL.md"
    second_path = tmp_path / "second" / "SKILL.md"
    _write_skill(first_path, name="duplicate")
    _write_skill(second_path, name="duplicate")
    reader = SkillReader()

    with pytest.raises(ValueError, match="already registered"):
        SkillRegistry([reader.read(first_path), reader.read(second_path)])


def test_default_skills_are_discovered_from_files() -> None:
    registry = compose_default_skills()

    assert {skill.name for skill in registry.all()} == {
        "planning",
        "sql",
        "analysis",
        "visualization",
    }
    assert all(skill.description.strip() for skill in registry.all())
