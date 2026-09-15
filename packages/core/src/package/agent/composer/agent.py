from pathlib import Path

from package.agent.skills.contracts import Skill
from package.agent.skills.reader import SkillReader
from package.agent.skills.registry import SkillRegistry
from package.agent.tools.contracts import Tool
from package.agent.tools.registry import ToolRegistry


DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"


def compose_tools(*tools: Tool) -> ToolRegistry:
    return ToolRegistry(list(tools))


def compose_skills(*skills: Skill) -> SkillRegistry:
    return SkillRegistry(list(skills))


def compose_default_skills(
    *,
    root: Path = DEFAULT_SKILLS_ROOT,
    reader: SkillReader | None = None,
) -> SkillRegistry:
    skill_reader = reader or SkillReader()
    return SkillRegistry(list(skill_reader.discover(root)))
