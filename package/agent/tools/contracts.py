from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]

    async def invoke(self, arguments: dict[str, Any]) -> Any: ...
