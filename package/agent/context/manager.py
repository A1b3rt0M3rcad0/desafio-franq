import asyncio
from collections.abc import Sequence

from package.agent.context.builder import ContextBuilder
from package.agent.context.models import (
    AgentContext,
    ConversationTurn,
    SkillDescriptor,
    ToolDescriptor,
)
from package.agent.llm.models import LLMMessage, LLMToolCall, LLMToolDefinition, MessageRole
from package.agent.skills.registry import SkillRegistry
from package.agent.tools.registry import ToolRegistry


SKILL_REQUEST_TOOL_NAME = "use_skill"


class ContextManager:
    """Builds the Agent working context without persisting loaded skill contents.

    Skill metadata is always present in the base prompt. Full skill instructions are
    fetched only when the Agent explicitly requests them and are injected into a copy
    of the messages for a single reasoning call. They are never appended to the
    persistent graph/conversation messages.
    """

    def __init__(
        self,
        *,
        builder: ContextBuilder,
        skills: SkillRegistry,
        system_prompt: str,
    ) -> None:
        self._builder = builder
        self._skills = skills
        self._system_prompt = system_prompt

    def build(
        self,
        *,
        session_id: str,
        execution_id: str,
        question: str,
        tools: ToolRegistry,
        history: Sequence[ConversationTurn] = (),
    ) -> AgentContext:
        return self._builder.build(
            session_id=session_id,
            execution_id=execution_id,
            question=question,
            history=history,
            skills=[
                SkillDescriptor(name=skill.name, description=skill.description)
                for skill in self._skills.all()
            ],
            tools=[
                ToolDescriptor(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
                for tool in tools.all()
            ],
        )

    def initial_messages(self, context: AgentContext) -> list[LLMMessage]:
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=self._render_base_prompt(context),
            )
        ]
        for turn in context.history:
            try:
                role = MessageRole(turn.role)
            except ValueError as exc:
                raise ValueError(f"Unsupported conversation role: {turn.role}") from exc
            messages.append(LLMMessage(role=role, content=turn.content))
        messages.append(LLMMessage(role=MessageRole.USER, content=context.question))
        return messages

    def tool_definitions(self, tools: ToolRegistry) -> tuple[LLMToolDefinition, ...]:
        definitions = [
            LLMToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools.all()
        ]
        skill_names = [skill.name for skill in self._skills.all()]
        if skill_names:
            definitions.append(
                LLMToolDefinition(
                    name=SKILL_REQUEST_TOOL_NAME,
                    description=(
                        "Load one or more available skills for the next reasoning step only. "
                        "Use this before relying on a skill's detailed instructions."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "skills": {
                                "type": "array",
                                "items": {"type": "string", "enum": skill_names},
                                "minItems": 1,
                                "uniqueItems": True,
                            }
                        },
                        "required": ["skills"],
                        "additionalProperties": False,
                    },
                )
            )
        return tuple(definitions)

    async def reasoning_messages(
        self,
        messages: Sequence[LLMMessage],
        *,
        skill_names: Sequence[str] = (),
    ) -> list[LLMMessage]:
        result = list(messages)
        names = _unique_names(skill_names)
        if not names:
            return result

        skills = [self._skills.get(name) for name in names]
        contents = await asyncio.gather(*(skill.load() for skill in skills))
        ephemeral = LLMMessage(
            role=MessageRole.DEVELOPER,
            content=self._render_active_skills(names, contents),
        )

        insert_at = 1 if result and result[0].role == MessageRole.SYSTEM else 0
        result.insert(insert_at, ephemeral)
        return result

    def is_skill_request(self, call: LLMToolCall) -> bool:
        return call.name == SKILL_REQUEST_TOOL_NAME

    def requested_skills(self, call: LLMToolCall) -> tuple[str, ...]:
        if not self.is_skill_request(call):
            raise ValueError(f"Not a skill request: {call.name}")

        raw_names = call.arguments.get("skills")
        if not isinstance(raw_names, list) or not raw_names:
            raise ValueError("Skill request requires a non-empty 'skills' array")

        names: list[str] = []
        for item in raw_names:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Skill names must be non-empty strings")
            name = item.strip()
            self._skills.get(name)
            if name not in names:
                names.append(name)
        return tuple(names)

    def _render_base_prompt(self, context: AgentContext) -> str:
        if context.skills:
            skill_catalog = "\n".join(
                f"- {skill.name}: {skill.description}" for skill in context.skills
            )
            skill_section = (
                "\n\nAvailable skills (metadata only):\n"
                f"{skill_catalog}\n\n"
                f"To use a skill, call `{SKILL_REQUEST_TOOL_NAME}` with the required skill names. "
                "The full skill instructions are injected only into the next reasoning step and "
                "are removed immediately afterwards. Request the skill again if it is needed later."
            )
        else:
            skill_section = "\n\nNo contextual skills are currently registered."

        return f"{self._system_prompt.strip()}{skill_section}"

    @staticmethod
    def _render_active_skills(names: Sequence[str], contents: Sequence[str]) -> str:
        blocks = [
            "The following skill instructions are active for this reasoning step only. "
            "They will not be retained after this model call."
        ]
        for name, content in zip(names, contents, strict=True):
            blocks.append(f"\n<skill name=\"{name}\">\n{content.strip()}\n</skill>")
        return "\n".join(blocks)


def _unique_names(names: Sequence[str]) -> tuple[str, ...]:
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return tuple(unique)
