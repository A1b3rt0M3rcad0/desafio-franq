from typing import Protocol


class Skill(Protocol):
    """Lazy contextual capability.

    Only ``name`` and ``description`` belong to the Agent's base context. The full
    skill instructions are loaded on demand and must not be persisted in the
    conversation state after the reasoning step that requested them.
    """

    name: str
    description: str

    async def load(self) -> str: ...
