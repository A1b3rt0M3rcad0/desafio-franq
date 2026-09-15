import re
from typing import Any

from package.agent.context.contracts import GlobalContextStore
from package.agent.llm.models import LLMToolCall, LLMToolDefinition


GLOBAL_CONTEXT_SEARCH_TOOL_NAME = "global_context_search"
_WORD_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)


class GlobalContextRetriever:
    """Session-scoped lexical retrieval exposed to the Agent as an internal Tool."""

    def __init__(
        self,
        *,
        store: GlobalContextStore,
        default_limit: int,
        max_limit: int,
    ) -> None:
        if default_limit < 1:
            raise ValueError("default_limit must be greater than zero")
        if max_limit < default_limit:
            raise ValueError("max_limit must be greater than or equal to default_limit")
        self._store = store
        self._default_limit = default_limit
        self._max_limit = max_limit

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name=GLOBAL_CONTEXT_SEARCH_TOOL_NAME,
            description=(
                "Search the complete durable context of the current session using lexical terms. "
                "Use it when relevant information may have been compacted out of the current "
                "snapshot or when the user refers to an older detail that is not currently visible."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Lexical search query for prior session information.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": self._max_limit,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )

    def is_call(self, call: LLMToolCall) -> bool:
        return call.name == GLOBAL_CONTEXT_SEARCH_TOOL_NAME

    async def invoke(self, *, session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_query = arguments.get("query")
        if not isinstance(raw_query, str) or not raw_query.strip():
            raise ValueError("Global context search requires a non-empty 'query'")
        raw_limit = arguments.get("limit", self._default_limit)
        if not isinstance(raw_limit, int) or isinstance(raw_limit, bool):
            raise ValueError("Global context search 'limit' must be an integer")
        if raw_limit < 1 or raw_limit > self._max_limit:
            raise ValueError(f"Global context search 'limit' must be between 1 and {self._max_limit}")

        matches = await self._store.search(
            session_id=session_id,
            query=raw_query.strip(),
            limit=raw_limit,
        )
        return {
            "query": raw_query.strip(),
            "matches": [
                {
                    "score": match.score,
                    "sequence": match.entry.sequence,
                    "execution_id": match.entry.execution_id,
                    "kind": match.entry.kind.value,
                    "content": match.entry.content,
                    "metadata": match.entry.metadata,
                    "created_at": (
                        match.entry.created_at.isoformat()
                        if match.entry.created_at is not None
                        else None
                    ),
                }
                for match in matches
            ],
        }


def lexical_terms(value: str) -> tuple[str, ...]:
    terms: list[str] = []
    for token in _WORD_RE.findall(value.casefold()):
        if token and token not in terms:
            terms.append(token)
    return tuple(terms)


def lexical_score(*, query: str, content: str) -> float:
    terms = lexical_terms(query)
    if not terms:
        return 0.0
    normalized = content.casefold()
    score = float(sum(normalized.count(term) for term in terms))
    exact = query.strip().casefold()
    if exact and exact in normalized:
        score += float(len(terms) + 1)
    return score
