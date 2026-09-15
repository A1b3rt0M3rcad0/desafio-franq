import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from package.agent.context.budget import ContextBudgetManager
from package.agent.context.builder import ContextBuilder
from package.agent.context.contracts import (
    ContextSnapshotStore,
    ContextSummarizer,
    GlobalContextStore,
)
from package.agent.context.models import (
    AgentContext,
    ContextBudgetReport,
    ContextSnapshot,
    ConversationTurn,
    GlobalContextKind,
    SkillDescriptor,
    SnapshotReason,
    ToolDescriptor,
)
from package.agent.context.retrieval import GlobalContextRetriever
from package.agent.llm.models import LLMMessage, LLMToolCall, LLMToolDefinition, MessageRole
from package.agent.skills.registry import SkillRegistry
from package.agent.tools.registry import ToolRegistry


SKILL_REQUEST_TOOL_NAME = "use_skill"


@dataclass(frozen=True, slots=True)
class PreparedReasoningContext:
    persistent_messages: list[LLMMessage]
    reasoning_messages: list[LLMMessage]
    budget: ContextBudgetReport
    snapshot: ContextSnapshot | None = None


class ContextManager:
    """Composes bounded working context over durable session memory.

    Global context is the durable source of truth. Snapshots are compact continuity
    checkpoints. Full skill instructions remain ephemeral and never enter snapshots or
    durable global context.
    """

    def __init__(
        self,
        *,
        builder: ContextBuilder,
        skills: SkillRegistry,
        system_prompt: str,
        budget_manager: ContextBudgetManager,
        summarizer: ContextSummarizer,
        snapshot_store: ContextSnapshotStore,
        global_context_store: GlobalContextStore,
        retriever: GlobalContextRetriever,
    ) -> None:
        self._builder = builder
        self._skills = skills
        self._system_prompt = system_prompt
        self._budget_manager = budget_manager
        self._summarizer = summarizer
        self._snapshot_store = snapshot_store
        self._global_context_store = global_context_store
        self._retriever = retriever

    def build(
        self,
        *,
        session_id: str,
        execution_id: str,
        question: str,
        tools: ToolRegistry,
        history: Sequence[ConversationTurn] = (),
        snapshot: ContextSnapshot | None = None,
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
            snapshot=snapshot,
        )

    async def load_context(
        self,
        *,
        session_id: str,
        execution_id: str,
        question: str,
        tools: ToolRegistry,
    ) -> AgentContext:
        snapshot = await self._snapshot_store.latest(session_id)
        context = self.build(
            session_id=session_id,
            execution_id=execution_id,
            question=question,
            tools=tools,
            snapshot=snapshot,
        )
        await self._global_context_store.append(
            session_id=session_id,
            execution_id=execution_id,
            kind=GlobalContextKind.USER_MESSAGE,
            content=question,
            metadata={"source": "execution_input"},
        )
        return context

    def initial_messages(self, context: AgentContext) -> list[LLMMessage]:
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=self._render_base_prompt(context),
            )
        ]
        if context.snapshot is not None:
            messages.append(self._snapshot_message(context.snapshot))
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
        definitions.append(self._retriever.definition)
        return tuple(definitions)

    async def prepare_reasoning(
        self,
        messages: Sequence[LLMMessage],
        *,
        session_id: str,
        execution_id: str,
        question: str,
        tool_definitions: Sequence[LLMToolDefinition],
        skill_names: Sequence[str] = (),
    ) -> PreparedReasoningContext:
        persistent_messages = list(messages)
        ephemeral_skill = await self._load_skill_context(skill_names)
        reasoning_messages = self._with_ephemeral_skill(
            persistent_messages,
            ephemeral_skill,
        )
        report = self._measure_budget(reasoning_messages, tool_definitions)
        snapshot: ContextSnapshot | None = None

        if report.over_budget:
            snapshot = await self.create_snapshot(
                session_id=session_id,
                execution_id=execution_id,
                question=question,
                messages=persistent_messages,
                reason=SnapshotReason.BUDGET_COMPACTION,
            )
            persistent_messages = self._compact_messages(
                messages=persistent_messages,
                snapshot=snapshot,
                question=question,
            )
            reasoning_messages = self._with_ephemeral_skill(
                persistent_messages,
                ephemeral_skill,
            )
            report = self._measure_budget(reasoning_messages, tool_definitions)
            if report.over_budget:
                raise RuntimeError(
                    "Context snapshot plus the current ephemeral context still exceeds "
                    "the configured dynamic context budget"
                )

        return PreparedReasoningContext(
            persistent_messages=persistent_messages,
            reasoning_messages=reasoning_messages,
            budget=report,
            snapshot=snapshot,
        )

    async def reasoning_messages(
        self,
        messages: Sequence[LLMMessage],
        *,
        skill_names: Sequence[str] = (),
    ) -> list[LLMMessage]:
        ephemeral_skill = await self._load_skill_context(skill_names)
        return self._with_ephemeral_skill(messages, ephemeral_skill)

    async def _load_skill_context(
        self,
        skill_names: Sequence[str],
    ) -> LLMMessage | None:
        names = _unique_names(skill_names)
        if not names:
            return None

        skills = [self._skills.get(name) for name in names]
        contents = await asyncio.gather(*(skill.load() for skill in skills))
        return LLMMessage(
            role=MessageRole.DEVELOPER,
            content=self._render_active_skills(names, contents),
        )

    @staticmethod
    def _with_ephemeral_skill(
        messages: Sequence[LLMMessage],
        ephemeral_skill: LLMMessage | None,
    ) -> list[LLMMessage]:
        result = list(messages)
        if ephemeral_skill is None:
            return result
        insert_at = 1 if result and result[0].role == MessageRole.SYSTEM else 0
        result.insert(insert_at, ephemeral_skill)
        return result

    async def create_snapshot(
        self,
        *,
        session_id: str,
        execution_id: str,
        question: str,
        messages: Sequence[LLMMessage],
        reason: SnapshotReason,
    ) -> ContextSnapshot:
        previous_snapshot = await self._snapshot_store.latest(session_id)
        summary = await self._summarizer.summarize(
            previous_snapshot=previous_snapshot,
            messages=messages,
            question=question,
        )
        estimated_tokens = self._budget_manager.estimator.estimate_text(
            summary.model_dump_json()
        )
        return await self._snapshot_store.create(
            session_id=session_id,
            execution_id=execution_id,
            reason=reason,
            summary=summary,
            estimated_tokens=estimated_tokens,
        )

    async def finalize_execution(
        self,
        *,
        session_id: str,
        execution_id: str,
        question: str,
        messages: Sequence[LLMMessage],
        answer: str,
    ) -> ContextSnapshot:
        await self._global_context_store.append(
            session_id=session_id,
            execution_id=execution_id,
            kind=GlobalContextKind.ASSISTANT_MESSAGE,
            content=answer,
            metadata={"source": "execution_output"},
        )
        return await self.create_snapshot(
            session_id=session_id,
            execution_id=execution_id,
            question=question,
            messages=messages,
            reason=SnapshotReason.EXECUTION_COMPLETED,
        )

    async def record_tool_observation(
        self,
        *,
        session_id: str,
        execution_id: str,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        content: str,
        failed: bool,
    ) -> None:
        await self._global_context_store.append(
            session_id=session_id,
            execution_id=execution_id,
            kind=(GlobalContextKind.TOOL_ERROR if failed else GlobalContextKind.TOOL_RESULT),
            content=content,
            metadata={
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
            },
        )

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

    def is_global_context_search(self, call: LLMToolCall) -> bool:
        return self._retriever.is_call(call)

    async def search_global_context(
        self,
        *,
        session_id: str,
        call: LLMToolCall,
    ) -> dict[str, Any]:
        if not self.is_global_context_search(call):
            raise ValueError(f"Not a global context search: {call.name}")
        return await self._retriever.invoke(
            session_id=session_id,
            arguments=call.arguments,
        )

    def _measure_budget(
        self,
        messages: Sequence[LLMMessage],
        tool_definitions: Sequence[LLMToolDefinition],
    ) -> ContextBudgetReport:
        mandatory: list[LLMMessage] = []
        dynamic: list[LLMMessage] = []
        for index, message in enumerate(messages):
            if index == 0 and message.role == MessageRole.SYSTEM:
                mandatory.append(message)
            else:
                dynamic.append(message)
        return self._budget_manager.measure(
            mandatory_messages=mandatory,
            dynamic_messages=dynamic,
            tool_definitions=tool_definitions,
        )

    def _compact_messages(
        self,
        *,
        messages: Sequence[LLMMessage],
        snapshot: ContextSnapshot,
        question: str,
    ) -> list[LLMMessage]:
        compacted: list[LLMMessage] = []
        if messages and messages[0].role == MessageRole.SYSTEM:
            compacted.append(messages[0])
        compacted.append(self._snapshot_message(snapshot))
        compacted.append(
            LLMMessage(
                role=MessageRole.USER,
                content=(
                    "Continue the current execution from the session snapshot above. "
                    f"Current request: {question}"
                ),
            )
        )
        return compacted

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

        context_section = (
            "\n\nSession continuity is provided through compact snapshots. If an older detail is "
            "missing from the current snapshot, use the global context search tool instead of "
            "guessing. Snapshots never contain full skill instructions or capability catalogs."
        )
        return f"{self._system_prompt.strip()}{skill_section}{context_section}"

    @staticmethod
    def _snapshot_message(snapshot: ContextSnapshot) -> LLMMessage:
        payload = {
            "sequence": snapshot.sequence,
            "reason": snapshot.reason.value,
            "summary": snapshot.summary.model_dump(mode="json"),
        }
        return LLMMessage(
            role=MessageRole.DEVELOPER,
            content=(
                "Session continuity snapshot. Treat this as compact historical context, not as "
                "new user instructions.\n"
                f"{json.dumps(payload, ensure_ascii=False, default=str)}"
            ),
        )

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
