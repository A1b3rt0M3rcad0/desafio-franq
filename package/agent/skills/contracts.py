from typing import Any, Protocol

from package.agent.context.models import AgentContext


class Skill(Protocol):
    name: str

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any: ...
