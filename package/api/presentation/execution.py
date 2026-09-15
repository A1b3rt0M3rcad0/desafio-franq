from package.agent.database.models.execution import AgentExecution
from package.api.http.schemas.execution import ExecutionResponse


def present_execution(execution: AgentExecution) -> ExecutionResponse:
    return ExecutionResponse(
        id=execution.id,
        session_id=execution.session_id,
        question=execution.question,
        status=execution.status,
        answer=execution.answer,
        error=execution.error,
        result=execution.result,
        created_at=execution.created_at,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )
