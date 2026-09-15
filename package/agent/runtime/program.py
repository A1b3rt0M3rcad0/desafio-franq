import asyncio
import json
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from package.agent.context.manager import ContextManager
from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMMessage, LLMToolCall, MessageRole
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.state import AgentGraphState
from package.agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class LangGraphAgentProgramResult:
    answer: str
    result: dict[str, Any]


class LangGraphAgentProgram:
    """Generic iterative AgentProgram orchestrated by LangGraph.

    The persistent graph state keeps conversation/tool results, but never the full
    content of a loaded skill. Skill instructions are injected by ContextManager into
    a temporary message list for exactly one reasoning call.
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
        context = self._context_manager.build(
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
        return LangGraphAgentProgramResult(
            answer=final_state["answer"],
            result={
                "iterations": final_state["iteration"],
                "tool_calls": final_state["tool_call_count"],
                "skill_uses": final_state["skill_use_count"],
                "stop_reason": final_state["stop_reason"],
            },
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
        reasoning_messages = await self._context_manager.reasoning_messages(
            state["messages"],
            skill_names=active_skills,
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

        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.LLM_STARTED,
                payload={"iteration": state["iteration"]},
            )
        )
        try:
            response = await self._llm.invoke(
                reasoning_messages,
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
        messages = [*state["messages"], assistant_message]

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
        active_skill_names: list[str] = []
        skill_use_count = 0
        external_calls: list[LLMToolCall] = []

        for call in calls:
            if not self._context_manager.is_skill_request(call):
                external_calls.append(call)
                continue
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

        if external_calls:
            results = await self._execute_external_calls(state, external_calls)
            contents.update(results)

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
            "tool_call_count": state["tool_call_count"] + len(external_calls),
            "skill_use_count": state["skill_use_count"] + skill_use_count,
        }

    async def _execute_external_calls(
        self,
        state: AgentGraphState,
        calls: list[LLMToolCall],
    ) -> dict[str, str]:
        semaphores: dict[str, asyncio.Semaphore] = {}

        async def execute(call: LLMToolCall) -> tuple[str, str]:
            semaphore = semaphores.setdefault(
                call.name,
                asyncio.Semaphore(state["max_parallel_tool_calls_per_tool"]),
            )
            async with semaphore:
                return call.id, await self._execute_external_call(state, call)

        pairs = await asyncio.gather(*(execute(call) for call in calls))
        return dict(pairs)

    async def _execute_external_call(
        self,
        state: AgentGraphState,
        call: LLMToolCall,
    ) -> str:
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
            tool = self._tools.get(call.name)
            result = await tool.invoke(call.arguments)
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
            return _serialize_tool_message(ok=True, result=result)
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
            return _serialize_tool_message(ok=False, error=str(exc))

    async def _answer_node(self, state: AgentGraphState) -> dict[str, Any]:
        answer = state["answer"].strip() or "Não foi possível gerar uma resposta final."
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.ANSWER_GENERATED,
                payload={
                    "iterations": state["iteration"],
                    "stop_reason": state["stop_reason"] or "answer",
                },
            )
        )
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.ASSISTANT_DELTA,
                payload={"content": answer},
            )
        )
        return {
            "answer": answer,
            "stop_reason": state["stop_reason"] or "answer",
        }


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
