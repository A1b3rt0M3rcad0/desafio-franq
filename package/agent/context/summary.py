import json
from collections.abc import Sequence

from package.agent.context.models import ContextSnapshot, ContextSummary
from package.agent.llm.contracts import LLMClient
from package.agent.llm.models import LLMMessage, MessageRole


class FallbackContextSummarizer:
    """Bounded fallback used only when the model does not return valid summary JSON."""

    def __init__(
        self,
        *,
        max_messages: int,
        max_chars_per_message: int,
    ) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be greater than zero")
        if max_chars_per_message < 1:
            raise ValueError("max_chars_per_message must be greater than zero")
        self._max_messages = max_messages
        self._max_chars_per_message = max_chars_per_message

    async def summarize(
        self,
        *,
        previous_snapshot: ContextSnapshot | None,
        messages: Sequence[LLMMessage],
        question: str,
    ) -> ContextSummary:
        notes: list[str] = []
        if previous_snapshot is not None:
            previous = previous_snapshot.summary
            notes.extend(previous.continuity_notes[-self._max_messages :])
            facts = list(previous.established_facts)
            constraints = list(previous.constraints)
            decisions = list(previous.decisions)
            open_questions = list(previous.open_questions)
            references = list(previous.relevant_references)
            objective = previous.objective
        else:
            facts = []
            constraints = []
            decisions = []
            open_questions = []
            references = []
            objective = None

        for message in list(messages)[-self._max_messages :]:
            text = message.content.strip()
            if not text:
                continue
            if len(text) > self._max_chars_per_message:
                text = f"{text[: self._max_chars_per_message].rstrip()}…"
            notes.append(f"[{message.role.value}] {text}")

        return ContextSummary(
            current_request=question,
            objective=objective,
            established_facts=facts,
            constraints=constraints,
            decisions=decisions,
            open_questions=open_questions,
            relevant_references=references,
            continuity_notes=notes[-self._max_messages :],
        )


class LLMContextSummarizer:
    """Produces a structured continuity summary without exposing hidden reasoning."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        fallback: FallbackContextSummarizer,
    ) -> None:
        self._llm = llm
        self._fallback = fallback

    async def summarize(
        self,
        *,
        previous_snapshot: ContextSnapshot | None,
        messages: Sequence[LLMMessage],
        question: str,
    ) -> ContextSummary:
        payload = {
            "current_request": question,
            "previous_snapshot": (
                previous_snapshot.summary.model_dump(mode="json")
                if previous_snapshot is not None
                else None
            ),
            "working_context": [
                {
                    "role": message.role.value,
                    "content": message.content,
                    "tool_calls": [call.model_dump(mode="json") for call in message.tool_calls],
                    "tool_call_id": message.tool_call_id,
                }
                for message in messages
                if message.role != MessageRole.SYSTEM
            ],
        }
        prompt = (
            "Create a compact session-continuity snapshot. Preserve only information that may "
            "matter to future reasoning: the current request, objective, established facts, "
            "constraints, decisions, unresolved questions, identifiers/references and concise "
            "continuity notes. Do not include tool catalogs, skill catalogs, skill instructions, "
            "system instructions or hidden chain-of-thought. Return ONLY valid JSON with exactly "
            "these keys: current_request, objective, established_facts, constraints, decisions, "
            "open_questions, relevant_references, continuity_notes. All collection fields must be "
            "JSON arrays of strings. objective may be null.\n\nINPUT:\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )
        try:
            response = await self._llm.invoke(
                [
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content=(
                            "You are the context compaction component of an agent runtime. "
                            "Summarize observable context only."
                        ),
                    ),
                    LLMMessage(role=MessageRole.USER, content=prompt),
                ]
            )
            parsed = _parse_json_object(response.content)
            summary = ContextSummary.model_validate(parsed)
            if not summary.current_request.strip():
                summary.current_request = question
            return summary
        except Exception:
            return await self._fallback.summarize(
                previous_snapshot=previous_snapshot,
                messages=messages,
                question=question,
            )


def _parse_json_object(content: str) -> dict[str, object]:
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
        if value.lower().startswith("json"):
            value = value[4:].lstrip()

    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Summary response does not contain a JSON object")
    parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Summary response must be a JSON object")
    return parsed
