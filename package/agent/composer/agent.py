from package.agent.skills.contracts import Skill
from package.agent.skills.registry import SkillRegistry
from package.agent.tools.contracts import Tool
from package.agent.tools.registry import ToolRegistry


def compose_tools(*tools: Tool) -> ToolRegistry:
    return ToolRegistry(list(tools))


def compose_skills(*skills: Skill) -> SkillRegistry:
    return SkillRegistry(list(skills))
