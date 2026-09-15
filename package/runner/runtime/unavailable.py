from package.agent.runtime.execution import AgentRuntime


class AgentUnavailableError(RuntimeError):
    """The Runner is alive but cannot compose a usable agent runtime."""


class UnavailableRuntimeFactory:
    def __init__(self, error: str) -> None:
        self._error = error

    def create(self) -> AgentRuntime:
        raise AgentUnavailableError(self._error)
