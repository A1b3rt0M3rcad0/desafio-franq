from package.agent.database.models.session import AgentSession
from package.api.http.schemas.session import SessionResponse


def present_session(session: AgentSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        metadata=session.metadata_json,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
