from package.agent.tools.contracts import Tool
from package.agent.tools.registry import ToolRegistry


def compose_tools(*tools: Tool) -> ToolRegistry:
    return ToolRegistry(list(tools))
