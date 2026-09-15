import pytest

from package.agent.context.builder import ContextBuilder
from package.agent.context.manager import ContextManager, SKILL_REQUEST_TOOL_NAME
from package.agent.llm.models import LLMMessage, LLMToolCall, MessageRole
from package.agent.skills.registry import SkillRegistry
from package.agent.tools.registry import ToolRegistry


class Skill:
    name = "analysis"
    description = "Advanced analytical guidance"

    def __init__(self, content: str = "SECRET SKILL INSTRUCTIONS") -> None:
        self.content = content
        self.load_count = 0

    async def load(self) -> str:
        self.load_count += 1
        return self.content


class Tool:
    name = "database"
    description = "Query the database"
    input_schema = {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    }

    async def invoke(self, arguments):
        return arguments


def _manager(skill: Skill) -> ContextManager:
    return ContextManager(
        builder=ContextBuilder(),
        skills=SkillRegistry([skill]),
        system_prompt="Base system prompt.",
    )


def test_base_context_contains_only_skill_metadata() -> None:
    skill = Skill()
    manager = _manager(skill)
    tools = ToolRegistry([Tool()])
    context = manager.build(
        session_id="session-1",
        execution_id="execution-1",
        question="Analise",
        tools=tools,
    )

    messages = manager.initial_messages(context)
    prompt = messages[0].content

    assert skill.name in prompt
    assert skill.description in prompt
    assert skill.content not in prompt
    assert skill.load_count == 0
    assert context.tools[0].name == "database"


def test_skill_request_is_exposed_as_internal_llm_tool() -> None:
    skill = Skill()
    manager = _manager(skill)
    definitions = manager.tool_definitions(ToolRegistry([Tool()]))

    assert [definition.name for definition in definitions] == [
        "database",
        SKILL_REQUEST_TOOL_NAME,
    ]
    skill_definition = definitions[1]
    assert skill_definition.input_schema["properties"]["skills"]["items"]["enum"] == [
        skill.name
    ]


@pytest.mark.asyncio
async def test_loaded_skill_content_is_not_persisted_in_messages() -> None:
    skill = Skill()
    manager = _manager(skill)
    persistent_messages = [
        LLMMessage(role=MessageRole.SYSTEM, content="base"),
        LLMMessage(role=MessageRole.USER, content="question"),
    ]

    reasoning_messages = await manager.reasoning_messages(
        persistent_messages,
        skill_names=[skill.name],
    )

    assert skill.load_count == 1
    assert any(skill.content in message.content for message in reasoning_messages)
    assert all(skill.content not in message.content for message in persistent_messages)

    next_reasoning = await manager.reasoning_messages(persistent_messages)
    assert all(skill.content not in message.content for message in next_reasoning)
    assert skill.load_count == 1


@pytest.mark.asyncio
async def test_multiple_skills_can_be_loaded_for_same_reasoning_step() -> None:
    first = Skill("FIRST CONTENT")
    first.name = "first"
    first.description = "First skill"
    second = Skill("SECOND CONTENT")
    second.name = "second"
    second.description = "Second skill"
    manager = ContextManager(
        builder=ContextBuilder(),
        skills=SkillRegistry([first, second]),
        system_prompt="base",
    )

    messages = await manager.reasoning_messages(
        [LLMMessage(role=MessageRole.SYSTEM, content="base")],
        skill_names=["first", "second"],
    )

    content = "\n".join(message.content for message in messages)
    assert "FIRST CONTENT" in content
    assert "SECOND CONTENT" in content
    assert first.load_count == 1
    assert second.load_count == 1


def test_unknown_skill_request_is_rejected() -> None:
    manager = _manager(Skill())
    call = LLMToolCall(
        id="skill-1",
        name=SKILL_REQUEST_TOOL_NAME,
        arguments={"skills": ["missing"]},
    )

    with pytest.raises(KeyError, match="Unknown skill"):
        manager.requested_skills(call)
