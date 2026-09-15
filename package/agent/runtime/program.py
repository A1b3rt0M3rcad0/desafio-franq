import json
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import (
    LLMMessage,
    LLMToolDefinition,
    MessageRole,
)
from package.agent.observer.events import ExecutionEvent, ExecutionEventType
from package.agent.prompt.system import SYSTEM_PROMPT
from package.agent.runtime.loop import RuntimePolicy
from package.agent.runtime.state import AgentGraphState
from package.agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class LangGraphAgentProgramResult:
    answer: str
    result: dict[str, Any]


class LangGraphAgentProgram:
    """Generic iterative AgentProgram orchestrated by LangGraph.

    Cycle:
        agent -> reasoning -> tool -> agent -> ...
                            -> answer -> client/end

    Hidden chain-of-thought is never persisted or emitted. The observer receives only
    structured lifecycle, decision and tool execution events.
    """

    _AGENT = "agent"
    _REASONING = "reasoning"
    _TOOL = "tool"
    _ANSWER = "answer"

    def __init__(
        self,
        *,
        llm: LLMClient,
        tools: ToolRegistry,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._system_prompt = system_prompt
        self._tool_definitions = tuple(
            LLMToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools.all()
        )
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node(self._AGENT, self._agent_node)
        graph.add_node(self._REASONING, self._reasoning_node)
        graph.add_node(self._TOOL, self._tool_node)
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
                self._TOOL: self._TOOL,
                self._ANSWER: self._ANSWER,
            },
        )
        graph.add_edge(self._TOOL, self._AGENT)
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
        initial_state: AgentGraphState = {
            "execution_id": execution_id,
            "session_id": session_id,
            "question": question,
            "messages": [],
            "iteration": 0,
            "max_iterations": policy.max_iterations,
            "pending_tool_calls": [],
            "tool_call_count": 0,
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
                "stop_reason": final_state["stop_reason"],
            },
        )

    async def _agent_node(self, state: AgentGraphState) -> dict[str, Any]:
        messages = list(state["messages"])
        if not messages:
            messages.extend(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=self._system_prompt),
                    LLMMessage(role=MessageRole.USER, content=state["question"]),
                ]
            )

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
                "messages": messages,
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
            "messages": messages,
            "iteration": iteration,
            "pending_tool_calls": [],
        }

    def _route_after_agent(self, state: AgentGraphState) -> Literal["reasoning", "answer"]:
        if state["stop_reason"] == "max_iterations":
            return self._ANSWER
        return self._REASONING

    async def _reasoning_node(self, state: AgentGraphState) -> dict[str, Any]:
        await state["observer"].emit(
            ExecutionEvent(
                execution_id=state["execution_id"],
                type=ExecutionEventType.LLM_STARTED,
                payload={"iteration": state["iteration"]},
            )
        )
        response = await self._llm.invoke(
            state["messages"],
            tools=self._tool_definitions,
        )
        assistant_message = LLMMessage(
            role=MessageRole.ASSISTANT,
            content=response.content,
            tool_calls=response.tool_calls,
        )
        messages = [*state["messages"], assistant_message]

        decision = "tool" if response.tool_calls else "answer"
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
                    "tools": [call.name for call in response.tool_calls],
                },
            )
        )

        if response.tool_calls:
            return {
                "messages": messages,
                "pending_tool_calls": list(response.tool_calls),
            }
        return {
            "messages": messages,
            "answer": response.content.strip(),
            "stop_reason": "answer",
        }

    def _route_after_reasoning(self, state: AgentGraphState) -> Literal["tool", "answer"]:
        if state["pending_tool_calls"]:
            return self._TOOL
        return self._ANSWER

    async def _tool_node(self, state: AgentGraphState) -> dict[str, Any]:
        messages = list(state["messages"])
        calls = list(state["pending_tool_calls"])

        for call in calls:
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
            except Exception as exc:
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

            messages.append(
                LLMMessage(
                    role=MessageRole.TOOL,
                    content=content,
                    tool_call_id=call.id,
                )
            )

        return {
            "messages": messages,
            "pending_tool_calls": [],
            "tool_call_count": state["tool_call_count"] + len(calls),
        }

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
