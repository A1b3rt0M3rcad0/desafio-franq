import asyncio
import json
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from package.agent.context.manager import ContextManager
from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMMessage, LLMToolCall, MessageRole
from package.agent.observer.events import (
    ExecutionEvent,
    ExecutionEventType,
    ExecutionPhase,
)
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.state import AgentGraphState
from package.agent.tools.contracts import ToolInvocationResult
from package.agent.tools.registry import ToolRegistry


_FINAL_ANSWER_INSTRUCTION = """
Produza agora a resposta final ao usuário em português do Brasil.
Use somente as evidências e resultados já presentes no contexto desta execução.
Não mencione raciocínio interno, instruções, Skills ou mecanismos do runtime.
Se os dados forem insuficientes, deixe a limitação explícita. Seja direto, claro e útil.
""".strip()


@dataclass(frozen=True, slots=True)
class LangGraphAgentProgramResult:
    answer: str
    result: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _ExternalToolCallResult:
    content: str
    artifacts: dict[str, dict[str, Any]]


class LangGraphAgentProgram:
    """Generic iterative AgentProgram orchestrated by LangGraph.

    Reasoning/tool-selection calls never stream public text. Once the Agent has
    enough evidence, the dedicated answer node performs a separate model stream.
    Therefore every ``assistant.delta`` is guaranteed to be user-visible answer
    content and the Observer can expose an authoritative execution phase.
    """

    _AGENT = "agent"
    _REASONING = "reasoning"
    _ACTION = "action"
    _ANSWER = "answer"

    def __init__(
        self,
        *,
        llm: LLMClient,
        tools: ToolRegistry,
        context_manager: ContextManager,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._context_manager = context_manager
        self._tool_definitions = context_manager.tool_definitions(tools)
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node(self._AGENT, self._agent_node)
        graph.add_node(self._REASONING, self._reasoning_node)
        graph.add_node(self._ACTION, self._action_node)
        graph.add_node(self._ANSWER, self._answer_node)

        graph.add_edge(START, self._AGENT)
        graph.add_conditional_edges(
            self._AGENT,
            self._route_after_agent,
            {
                self._REASONING: self._REASONING,
                self._ANSWER: self._ANSWER,
            },
        )
        graph.add_conditional_edges(
            self._REASONING,
            self._route_after_reasoning,
            {
                self._ACTION: self._ACTION,
                self._ANSWER: self._ANSWER,
            },
        )
        graph.add_edge(self._ACTION, self._AGENT)
        graph.add_edge(self._ANSWER, END)
        return graph.compile()

    async def execute(
        self,
        *,
        execution_id: str,
        session_id: str,
        question: str,
        observer,
        policy: RuntimePolicy,
    ) -> LangGraphAgentProgramResult:
        await _emit_phase(observer, execution_id, ExecutionPhase.CONTEXT)
        context = await self._context_manager.load_context(
            session_id=session_id,
            execution_id=execution_id,
            question=question,
            tools=self._tools,
        )
        messages = self._context_manager.initial_messages(context)
        await observer.emit(
            ExecutionEvent(
                execution_id=execution_id,
                type=ExecutionEventType.CONTEXT_LOADED,
                payload={
                    "history_turns": len(context.history),
                    "snapshot_sequence": (
                        context.snapshot.sequence if context.snapshot is not None else None
                    ),
                    "skills": [skill.name for skill in context.skills],
                    "tools": [tool.name for tool in context.tools],
                },
            )
        )

        initial_state: AgentGraphState = {
            "execution_id": execution_id,
            "session_id": session_id,
            "question": question,
            "messages": messages,
            "iteration": 0,
            "max_iterations": policy.max_iterations,
            "pending_tool_calls": [],
            "active_skill_names": [],
            "tool_call_count": 0,
            "skill_use_count": 0,
            "max_parallel_tool_calls_per_tool": policy.max_parallel_tool_calls_per_tool,
            "artifacts": {},
            "answer": "",
            "stop_reason": None,
            "observer": observer,
            "metadata": {"max_sql_retries": policy.max_sql_retries},
        }
        recursion_limit = max(32, policy.max_iterations * 4 + 8)
        final_state = await self._graph.ainvoke(
            initial_state,
            config={"recursion_limit": recursion_limit},
        )

        await _emit_phase(observer, execution_id, ExecutionPhase.FINALIZING)
        final_snapshot = await self._context_manager.finalize_execution(
            session_id=session_id,
            execution_id=execution_id,
            question=question,
            messages=final_state["messages"],
            answer=final_state["answer"],
        )
        await observer.emit(
            ExecutionEvent(
                execution_id=execution_id,
                type=ExecutionEventType.CONTEXT_SNAPSHOT_CREATED,
                payload={
                    "sequence": final_snapshot.sequence,
                    "reason": final_snapshot.reason.value,
                    "estimated_tokens": final_snapshot.estimated_tokens,
                },
            )
        )

        result: dict[str, Any] = {
            "iterations": final_state["iteration"],
            "tool_calls": final_state["tool_call_count"],
            "skill_uses": final_state["skill_use_count"],
            "stop_reason": final_state["stop_reason"],
        }
        presentation = final_state["artifacts"].get("presentation")
        if presentation is not None:
            result["presentation"] = presentation

        return LangGraphAgentProgramResult(
            answer=final_state["answer"],
            result=result,
        )

    async def _agent_node(self, state: AgentGraphState) -> dict[str, Any]:
        if state["iteration"] >= state["max_iterations"]:
            answer = state["answer"].strip() or (
                "Não foi possível concluir a solicitação dentro do limite de iterações."
            )
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.AGENT_MAX_ITERATIONS_REACHED,
                    payload={
                        "iterations": state["iteration"],
                        "max_iterations": state["max_iterations"],
                    },
                )
            )
            return {
                "answer": answer,
                "stop_reason": "max_iterations",
            }

        await _emit_phase(
            state["observer"],
            state["execution_id"],
            ExecutionPhase.REASONING,
        )
        iteration = state["iteration"] + 1
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.AGENT_ITERATION_STARTED,
                payload={
                    "iteration": iteration,
                    "max_iterations": state["max_iterations"],
                },
            )
        )
        return {
            "iteration": iteration,
            "pending_tool_calls": [],
        }

    def _route_after_agent(self, state: AgentGraphState) -> Literal["reasoning", "answer"]:
        if state["stop_reason"] == "max_iterations":
            return self._ANSWER
        return self._REASONING

    async def _reasoning_node(self, state: AgentGraphState) -> dict[str, Any]:
        active_skills = tuple(state["active_skill_names"])
        if active_skills:
            await _emit_phase(
                state["observer"],
                state["execution_id"],
                ExecutionPhase.SKILL,
            )
        else:
            await _emit_phase(
                state["observer"],
                state["execution_id"],
                ExecutionPhase.REASONING,
            )

        prepared = await self._context_manager.prepare_reasoning(
            state["messages"],
            session_id=state["session_id"],
            execution_id=state["execution_id"],
            question=state["question"],
            tool_definitions=self._tool_definitions,
            skill_names=active_skills,
        )
        if prepared.snapshot is not None:
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.CONTEXT_BUDGET_EXCEEDED,
                    payload={
                        "iteration": state["iteration"],
                        "dynamic_budget_tokens": prepared.budget.dynamic_budget_tokens,
                        "dynamic_tokens_after_compaction": prepared.budget.dynamic_tokens,
                    },
                )
            )
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.CONTEXT_SNAPSHOT_CREATED,
                    payload={
                        "sequence": prepared.snapshot.sequence,
                        "reason": prepared.snapshot.reason.value,
                        "estimated_tokens": prepared.snapshot.estimated_tokens,
                    },
                )
            )

        if active_skills:
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.SKILL_CONTEXT_LOADED,
                    payload={
                        "iteration": state["iteration"],
                        "skills": list(active_skills),
                    },
                )
            )

        await _emit_phase(
            state["observer"],
            state["execution_id"],
            ExecutionPhase.REASONING,
        )
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.LLM_STARTED,
                payload={
                    "iteration": state["iteration"],
                    "context_dynamic_tokens": prepared.budget.dynamic_tokens,
                    "context_dynamic_budget_tokens": prepared.budget.dynamic_budget_tokens,
                },
            )
        )
        try:
            response = await self._llm.invoke(
                prepared.reasoning_messages,
                tools=self._tool_definitions,
            )
        finally:
            if active_skills:
                await state["observer"].emit(
                    ExecutionEvent(
                        execution_id=state["execution_id"],
                        type=ExecutionEventType.SKILL_CONTEXT_RELEASED,
                        payload={
                            "iteration": state["iteration"],
                            "skills": list(active_skills),
                        },
                    )
                )

        assistant_message = LLMMessage(
            role=MessageRole.ASSISTANT,
            content=response.content,
            tool_calls=response.tool_calls,
        )
        messages = [*prepared.persistent_messages, assistant_message]

        decision = "action" if response.tool_calls else "answer"
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.LLM_COMPLETED,
                payload={
                    "iteration": state["iteration"],
                    "content_length": len(response.content),
                    "tool_call_count": len(response.tool_calls),
                },
            )
        )
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.AGENT_DECISION,
                payload={
                    "iteration": state["iteration"],
                    "decision": decision,
                    "actions": [call.name for call in response.tool_calls],
                },
            )
        )

        if response.tool_calls:
            return {
                "messages": messages,
                "pending_tool_calls": list(response.tool_calls),
                "active_skill_names": [],
            }
        return {
            "messages": messages,
            "active_skill_names": [],
            "answer": response.content.strip(),
            "stop_reason": "answer",
        }

    def _route_after_reasoning(self, state: AgentGraphState) -> Literal["action", "answer"]:
        if state["pending_tool_calls"]:
            return self._ACTION
        return self._ANSWER

    async def _action_node(self, state: AgentGraphState) -> dict[str, Any]:
        calls = list(state["pending_tool_calls"])
        contents: dict[str, str] = {}
        artifacts = dict(state["artifacts"])
        active_skill_names: list[str] = []
        skill_use_count = 0
        external_calls: list[LLMToolCall] = []
        context_search_calls: list[LLMToolCall] = []

        for call in calls:
            if self._context_manager.is_skill_request(call):
                try:
                    names = self._context_manager.requested_skills(call)
                    for name in names:
                        if name not in active_skill_names:
                            active_skill_names.append(name)
                    skill_use_count += len(names)
                    contents[call.id] = _serialize_tool_message(
                        ok=True,
                        result={
                            "skills": list(names),
                            "scope": "next_reasoning_step",
                        },
                    )
                    await state["observer"].emit(
                        ExecutionEvent(
                            execution_id=state["execution_id"],
                            type=ExecutionEventType.SKILL_REQUESTED,
                            payload={
                                "iteration": state["iteration"],
                                "skills": list(names),
                                "tool_call_id": call.id,
                            },
                        )
                    )
                except Exception as exc:
                    contents[call.id] = _serialize_tool_message(ok=False, error=str(exc))
                    await state["observer"].emit(
                        ExecutionEvent(
                            execution_id=state["execution_id"],
                            type=ExecutionEventType.TOOL_FAILED,
                            payload={
                                "iteration": state["iteration"],
                                "tool": call.name,
                                "tool_call_id": call.id,
                                "error": str(exc),
                            },
                        )
                    )
                continue

            if self._context_manager.is_global_context_search(call):
                context_search_calls.append(call)
                continue

            external_calls.append(call)

        if context_search_calls:
            results = await asyncio.gather(
                *(self._execute_context_search_call(state, call) for call in context_search_calls)
            )
            contents.update(dict(results))

        if external_calls:
            external_contents, external_artifacts = await self._execute_external_calls(
                state,
                external_calls,
            )
            contents.update(external_contents)
            artifacts.update(external_artifacts)

        messages = list(state["messages"])
        for call in calls:
            messages.append(
                LLMMessage(
                    role=MessageRole.TOOL,
                    content=contents[call.id],
                    tool_call_id=call.id,
                )
            )

        return {
            "messages": messages,
            "pending_tool_calls": [],
            "active_skill_names": active_skill_names,
            "tool_call_count": (
                state["tool_call_count"] + len(external_calls) + len(context_search_calls)
            ),
            "skill_use_count": state["skill_use_count"] + skill_use_count,
            "artifacts": artifacts,
        }

    async def _execute_context_search_call(
        self,
        state: AgentGraphState,
        call: LLMToolCall,
    ) -> tuple[str, str]:
        await _emit_phase(
            state["observer"],
            state["execution_id"],
            ExecutionPhase.TOOL,
        )
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.TOOL_STARTED,
                payload={
                    "iteration": state["iteration"],
                    "tool": call.name,
                    "tool_call_id": call.id,
                    "arguments": call.arguments,
                },
            )
        )
        try:
            result = await self._context_manager.search_global_context(
                session_id=state["session_id"],
                call=call,
            )
            content = _serialize_tool_message(ok=True, result=result)
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.CONTEXT_RETRIEVED,
                    payload={
                        "iteration": state["iteration"],
                        "query": result["query"],
                        "matches": len(result["matches"]),
                    },
                )
            )
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.TOOL_COMPLETED,
                    payload={
                        "iteration": state["iteration"],
                        "tool": call.name,
                        "tool_call_id": call.id,
                        "result": {"matches": len(result["matches"])},
                    },
                )
            )
            return call.id, content
        except Exception as exc:
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.TOOL_FAILED,
                    payload={
                        "iteration": state["iteration"],
                        "tool": call.name,
                        "tool_call_id": call.id,
                        "error": str(exc),
                    },
                )
            )
            return call.id, _serialize_tool_message(ok=False, error=str(exc))

    async def _execute_external_calls(
        self,
        state: AgentGraphState,
        calls: list[LLMToolCall],
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        semaphores: dict[str, asyncio.Semaphore] = {}

        async def execute(call: LLMToolCall) -> tuple[str, _ExternalToolCallResult]:
            semaphore = semaphores.setdefault(
                call.name,
                asyncio.Semaphore(state["max_parallel_tool_calls_per_tool"]),
            )
            async with semaphore:
                return call.id, await self._execute_external_call(state, call)

        pairs = await asyncio.gather(*(execute(call) for call in calls))
        contents: dict[str, str] = {}
        artifacts: dict[str, dict[str, Any]] = {}
        for call_id, result in pairs:
            contents[call_id] = result.content
            artifacts.update(result.artifacts)
        return contents, artifacts

    async def _execute_external_call(
        self,
        state: AgentGraphState,
        call: LLMToolCall,
    ) -> _ExternalToolCallResult:
        await _emit_phase(
            state["observer"],
            state["execution_id"],
            ExecutionPhase.TOOL,
        )
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.TOOL_STARTED,
                payload={
                    "iteration": state["iteration"],
                    "tool": call.name,
                    "tool_call_id": call.id,
                    "arguments": call.arguments,
                },
            )
        )
        failed = False
        artifacts: dict[str, dict[str, Any]] = {}
        try:
            tool = self._tools.get(call.name)
            invocation_result = await tool.invoke(call.arguments)
            result, artifacts = _unwrap_tool_result(invocation_result)
            content = _serialize_tool_message(ok=True, result=result)
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.TOOL_COMPLETED,
                    payload={
                        "iteration": state["iteration"],
                        "tool": call.name,
                        "tool_call_id": call.id,
                        "result": _summarize_tool_result(result),
                    },
                )
            )
            presentation = artifacts.get("presentation")
            if presentation is not None:
                visualization = presentation.get("visualization")
                visualization = visualization if isinstance(visualization, dict) else {}
                await state["observer"].emit(
                    ExecutionEvent(
                        execution_id=state["execution_id"],
                        type=ExecutionEventType.VISUALIZATION_SELECTED,
                        payload={
                            "iteration": state["iteration"],
                            "type": visualization.get("type"),
                            "title": visualization.get("title"),
                            "x": visualization.get("x"),
                            "y": visualization.get("y"),
                            "hue": visualization.get("hue"),
                        },
                    )
                )
        except Exception as exc:
            failed = True
            artifacts = {}
            content = _serialize_tool_message(ok=False, error=str(exc))
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.TOOL_FAILED,
                    payload={
                        "iteration": state["iteration"],
                        "tool": call.name,
                        "tool_call_id": call.id,
                        "error": str(exc),
                    },
                )
            )

        await self._context_manager.record_tool_observation(
            session_id=state["session_id"],
            execution_id=state["execution_id"],
            tool_name=call.name,
            tool_call_id=call.id,
            arguments=call.arguments,
            content=content,
            failed=failed,
        )
        return _ExternalToolCallResult(content=content, artifacts=artifacts)

    async def _answer_node(self, state: AgentGraphState) -> dict[str, Any]:
        draft = state["answer"].strip()
        stop_reason = state["stop_reason"] or "answer"

        await _emit_phase(
            state["observer"],
            state["execution_id"],
            ExecutionPhase.RESPONSE_PREPARING,
        )

        if stop_reason == "max_iterations":
            answer = draft or "Não foi possível gerar uma resposta final."
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.ANSWER_STARTED,
                    payload={"iteration": state["iteration"]},
                )
            )
            await _emit_phase(
                state["observer"],
                state["execution_id"],
                ExecutionPhase.RESPONSE_STREAMING,
            )
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.ASSISTANT_DELTA,
                    payload={"content": answer},
                )
            )
        else:
            final_messages = [
                *state["messages"],
                LLMMessage(
                    role=MessageRole.DEVELOPER,
                    content=_FINAL_ANSWER_INSTRUCTION,
                ),
            ]
            await state["observer"].emit(
                ExecutionEvent(
                    execution_id=state["execution_id"],
                    type=ExecutionEventType.ANSWER_STARTED,
                    payload={"iteration": state["iteration"]},
                )
            )
            await _emit_phase(
                state["observer"],
                state["execution_id"],
                ExecutionPhase.RESPONSE_STREAMING,
            )

            chunks: list[str] = []
            async for chunk in self._llm.stream(final_messages):
                content = chunk.content
                if not content:
                    continue
                chunks.append(content)
                await state["observer"].emit(
                    ExecutionEvent(
                        execution_id=state["execution_id"],
                        type=ExecutionEventType.ASSISTANT_DELTA,
                        payload={"content": content},
                    )
                )

            answer = "".join(chunks).strip()
            if not answer:
                answer = draft or "Não foi possível gerar uma resposta final."
                await state["observer"].emit(
                    ExecutionEvent(
                        execution_id=state["execution_id"],
                        type=ExecutionEventType.ASSISTANT_DELTA,
                        payload={"content": answer},
                    )
                )

        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.ANSWER_GENERATED,
                payload={
                    "iterations": state["iteration"],
                    "stop_reason": stop_reason,
                },
            )
        )
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.ANSWER_COMPLETED,
                payload={
                    "iteration": state["iteration"],
                    "content_length": len(answer),
                },
            )
        )
        await _emit_phase(
            state["observer"],
            state["execution_id"],
            ExecutionPhase.FINALIZING,
        )

        messages = list(state["messages"])
        if messages and messages[-1].role == MessageRole.ASSISTANT and not messages[-1].tool_calls:
            messages[-1] = LLMMessage(role=MessageRole.ASSISTANT, content=answer)
        else:
            messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=answer))

        return {
            "messages": messages,
            "answer": answer,
            "stop_reason": stop_reason,
        }


async def _emit_phase(observer, execution_id: str, phase: ExecutionPhase) -> None:
    await observer.emit(
        ExecutionEvent(
            execution_id=execution_id,
            type=ExecutionEventType.EXECUTION_PHASE_CHANGED,
            payload={"phase": phase.value},
        )
    )


def _unwrap_tool_result(result: Any) -> tuple[Any, dict[str, dict[str, Any]]]:
    if not isinstance(result, ToolInvocationResult):
        return result, {}

    artifacts: dict[str, dict[str, Any]] = {}
    for artifact in result.artifacts:
        kind = artifact.kind.strip()
        if not kind:
            raise ValueError("Tool artifact kind cannot be empty")
        if kind in artifacts:
            raise ValueError(f"Tool returned duplicate artifact kind: {kind}")
        artifacts[kind] = dict(artifact.payload)
    return result.observation, artifacts


def _serialize_tool_message(
    *,
    ok: bool,
    result: Any | None = None,
    error: str | None = None,
) -> str:
    payload: dict[str, Any] = {"ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error
    return json.dumps(payload, ensure_ascii=False, default=str)


def _summarize_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        summary: dict[str, Any] = {"keys": sorted(result.keys())}
        rows = result.get("rows")
        if isinstance(rows, (list, tuple)):
            summary["row_count"] = len(rows)
        if "truncated" in result:
            summary["truncated"] = bool(result["truncated"])
        return summary
    if isinstance(result, (list, tuple)):
        return {"type": type(result).__name__, "items": len(result)}
    return {"type": type(result).__name__}
