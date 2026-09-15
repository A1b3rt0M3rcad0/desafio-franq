from collections.abc import Sequence

from package.agent.context.models import (
    AgentContext,
    ConversationTurn,
    SkillDescriptor,
    ToolDescriptor,
)


class ContextBuilder:
    def build(
        self,
        *,
        session_id: str,
        execution_id: str,
        question: str,
        history: Sequence[ConversationTurn] = (),
        skills: Sequence[SkillDescriptor] = (),
        tools: Sequence[ToolDescriptor] = (),
    ) -> AgentContext:
        return AgentContext(
            session_id=session_id,
            execution_id=execution_id,
            question=question,
            history=list(history),
            skills=list(skills),
            tools=list(tools),
        )
