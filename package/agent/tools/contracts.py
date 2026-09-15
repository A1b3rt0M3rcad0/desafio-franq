from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str

    async def invoke(self, arguments: dict[str, Any]) -> Any: ...
