import pytest

from package.agent.context.budget import (
    ApproximateTokenEstimator,
    ContextBudgetManager,
    ContextBudgetPolicy,
)
from package.agent.context.builder import ContextBuilder
from package.agent.context.manager import ContextManager, SKILL_REQUEST_TOOL_NAME
from package.agent.context.memory import (
    InMemoryContextSnapshotStore,
    InMemoryGlobalContextStore,
)
from package.agent.context.models import ContextSummary, SnapshotReason
from package.agent.context.retrieval import (
    GLOBAL_CONTEXT_SEARCH_TOOL_NAME,
    GlobalContextRetriever,
)
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


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls = 0

    async def summarize(self, *, previous_snapshot, messages, question):
        self.calls += 1
        return ContextSummary(
            current_request=question,
            objective="preserve execution continuity",
            established_facts=["compressed fact"],
            continuity_notes=["continue from compacted context"],
        )


def _manager(
    skill: Skill | None = None,
    *,
    window_tokens: int = 1_000_000,
    budget_percent: float = 25.0,
    chars_per_token: float = 4.0,
):
    snapshots = InMemoryContextSnapshotStore()
    global_context = InMemoryGlobalContextStore()
    summarizer = FakeSummarizer()
    manager = ContextManager(
        builder=ContextBuilder(),
        skills=SkillRegistry([skill] if skill is not None else []),
        system_prompt="Base system prompt.",
        budget_manager=ContextBudgetManager(
            estimator=ApproximateTokenEstimator(chars_per_token=chars_per_token),
            policy=ContextBudgetPolicy(
                model_context_window_tokens=window_tokens,
                dynamic_context_percentage=budget_percent,
            ),
        ),
        summarizer=summarizer,
        snapshot_store=snapshots,
        global_context_store=global_context,
        retriever=GlobalContextRetriever(
            store=global_context,
            default_limit=5,
            max_limit=10,
        ),
    )
    return manager, snapshots, global_context, summarizer


def test_base_context_contains_only_skill_metadata() -> None:
    skill = Skill()
    manager, _, _, _ = _manager(skill)
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


def test_skill_and_global_retrieval_are_exposed_as_internal_llm_tools() -> None:
    skill = Skill()
    manager, _, _, _ = _manager(skill)
    definitions = manager.tool_definitions(ToolRegistry([Tool()]))

    assert [definition.name for definition in definitions] == [
        "database",
        SKILL_REQUEST_TOOL_NAME,
        GLOBAL_CONTEXT_SEARCH_TOOL_NAME,
    ]
    skill_definition = definitions[1]
    assert skill_definition.input_schema["properties"]["skills"]["items"]["enum"] == [
        skill.name
    ]


@pytest.mark.asyncio
async def test_loaded_skill_content_is_not_persisted_in_messages() -> None:
    skill = Skill()
    manager, _, _, _ = _manager(skill)
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

    snapshots = InMemoryContextSnapshotStore()
    global_context = InMemoryGlobalContextStore()
    manager = ContextManager(
        builder=ContextBuilder(),
        skills=SkillRegistry([first, second]),
        system_prompt="base",
        budget_manager=ContextBudgetManager(
            estimator=ApproximateTokenEstimator(chars_per_token=4.0),
            policy=ContextBudgetPolicy(
                model_context_window_tokens=1_000_000,
                dynamic_context_percentage=25.0,
            ),
        ),
        summarizer=FakeSummarizer(),
        snapshot_store=snapshots,
        global_context_store=global_context,
        retriever=GlobalContextRetriever(
            store=global_context,
            default_limit=5,
            max_limit=10,
        ),
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
    manager, _, _, _ = _manager(Skill())
    call = LLMToolCall(
        id="skill-1",
        name=SKILL_REQUEST_TOOL_NAME,
        arguments={"skills": ["missing"]},
    )

    with pytest.raises(KeyError, match="Unknown skill"):
        manager.requested_skills(call)


@pytest.mark.asyncio
async def test_latest_snapshot_is_the_starting_point_for_subsequent_execution() -> None:
    skill = Skill()
    manager, snapshots, _, _ = _manager(skill)
    await snapshots.create(
        session_id="session-1",
        execution_id="execution-old",
        reason=SnapshotReason.EXECUTION_COMPLETED,
        summary=ContextSummary(
            current_request="pedido anterior",
            established_facts=["cliente preferiu filtro de maio"],
        ),
        estimated_tokens=30,
    )

    context = await manager.load_context(
        session_id="session-1",
        execution_id="execution-new",
        question="continue a análise",
        tools=ToolRegistry([Tool()]),
    )
    messages = manager.initial_messages(context)
    rendered = "\n".join(message.content for message in messages)

    assert context.snapshot is not None
    assert context.snapshot.sequence == 1
    assert "cliente preferiu filtro de maio" in rendered
    assert skill.name in messages[0].content
    assert skill.content not in rendered


@pytest.mark.asyncio
async def test_budget_overflow_creates_snapshot_and_compacts_working_context() -> None:
    manager, snapshots, _, summarizer = _manager(
        None,
        window_tokens=4000,
        budget_percent=25.0,
        chars_per_token=1.0,
    )
    old_payload = "OLD-CONTEXT-" + ("x" * 2400)
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content="mandatory"),
        LLMMessage(role=MessageRole.USER, content=old_payload),
    ]

    prepared = await manager.prepare_reasoning(
        messages,
        session_id="session-1",
        execution_id="execution-1",
        question="continue",
        tool_definitions=(),
    )

    assert prepared.snapshot is not None
    assert prepared.snapshot.reason == SnapshotReason.BUDGET_COMPACTION
    assert summarizer.calls == 1
    assert len(snapshots.snapshots) == 1
    assert prepared.budget.over_budget is False
    compacted = "\n".join(message.content for message in prepared.persistent_messages)
    assert old_payload not in compacted
    assert "compressed fact" in compacted
