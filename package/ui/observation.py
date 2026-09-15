import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from package.ui.client import ObservedFrame


class FrameKind(StrEnum):
    STATE = "state"
    ACTIVITY = "activity"
    RESPONSE = "response"
    TRANSPORT = "transport"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class ActivityPresentation:
    sequence: int | None
    event_type: str
    title: str
    detail: str | None = None
    status: str = "info"

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ObservationUpdate:
    kind: FrameKind
    content_changed: bool = False
    terminal_status: str | None = None
    response_started: bool = False
    response_completed: bool = False
    transport_degraded: bool = False
    new_activities: tuple[ActivityPresentation, ...] = ()


_RESPONSE_EVENTS = {
    "answer.started",
    "answer.generated",
    "answer.completed",
    "assistant.delta",
}
_TERMINAL_EVENTS = {
    "execution.completed": "completed",
    "execution.failed": "failed",
    "execution.cancelled": "cancelled",
}
_TRANSPORT_EVENTS = {"heartbeat", "execution.realtime_unavailable"}


_PHASE_LABELS = {
    "pending": "Aguardando o agente...",
    "context": "Carregando contexto...",
    "reasoning": "Analisando a solicitação...",
    "skill": "Carregando conhecimento necessário...",
    "tool": "Consultando os dados...",
    "response_preparing": "Preparando a resposta...",
    "response_streaming": "Respondendo...",
    "finalizing": "Finalizando a sessão...",
    "cancel_requested": "Interrompendo a resposta...",
    "cancelled": "Interrompido",
    "completed": "Concluído",
    "failed": "Falha na execução",
}


def new_observation_state(execution_id: str) -> dict[str, Any]:
    return {
        "execution_id": execution_id,
        "content": "",
        "phase": "pending",
        "result": None,
        "error": None,
        "cancel_requested": False,
        "response_started": False,
        "response_completed": False,
        "activities": [],
        "seen_activity_sequences": set(),
        "realtime_degraded": False,
    }


def phase_label(phase: str) -> str | None:
    return _PHASE_LABELS.get(phase)


def classify_frame(frame: ObservedFrame) -> FrameKind:
    if frame.type == "execution.state":
        return FrameKind.STATE
    if frame.type in _TERMINAL_EVENTS:
        return FrameKind.TERMINAL
    if frame.type in _TRANSPORT_EVENTS:
        return FrameKind.TRANSPORT
    if frame.type in _RESPONSE_EVENTS:
        return FrameKind.RESPONSE
    return FrameKind.ACTIVITY


def apply_observed_frame(active: dict[str, Any], frame: ObservedFrame) -> ObservationUpdate:
    kind = classify_frame(frame)
    content_changed = False
    terminal_status: str | None = None
    response_started = bool(active.get("response_started"))
    response_completed = bool(active.get("response_completed"))
    transport_degraded = False
    new_activities: list[ActivityPresentation] = []

    if kind == FrameKind.STATE:
        phase = str(
            frame.payload.get("phase")
            or frame.payload.get("stage")
            or frame.payload.get("status")
            or active.get("phase")
            or "pending"
        )
        active["phase"] = phase
        candidate = frame.payload.get("partial_answer") or frame.payload.get("answer")
        if candidate:
            content_changed = _apply_state_answer(active, str(candidate))
        if isinstance(frame.payload.get("result"), dict):
            active["result"] = frame.payload["result"]
        if frame.payload.get("error"):
            active["error"] = str(frame.payload["error"])
        activities = frame.payload.get("activities")
        if isinstance(activities, list):
            for activity in activities:
                if not isinstance(activity, dict):
                    continue
                presentation = present_activity_record(activity)
                if presentation is not None and _remember_activity(active, presentation):
                    new_activities.append(presentation)
        status = str(frame.payload.get("status") or "")
        if status in {"completed", "failed", "cancelled"}:
            terminal_status = status
        if phase in {"response_streaming", "finalizing", "completed"} or active.get("content"):
            response_started = True
        if phase in {"finalizing", "completed"}:
            response_completed = bool(active.get("content")) or phase == "completed"
        active["realtime_degraded"] = not bool(frame.payload.get("realtime_available", True))

    elif frame.type == "assistant.delta":
        content = str(frame.payload.get("content") or "")
        if content:
            active["content"] = f"{active.get('content') or ''}{content}"
            content_changed = True
        response_started = True
        active["phase"] = "response_streaming"

    elif frame.type == "answer.started":
        response_started = True
        active["phase"] = "response_streaming"
        presentation = present_activity_frame(frame)
        if presentation is not None and _remember_activity(active, presentation):
            new_activities.append(presentation)

    elif frame.type == "answer.completed":
        response_started = True
        response_completed = True
        active["phase"] = "finalizing"
        presentation = present_activity_frame(frame)
        if presentation is not None and _remember_activity(active, presentation):
            new_activities.append(presentation)

    elif frame.type == "answer.generated":
        response_started = True
        presentation = present_activity_frame(frame)
        if presentation is not None and _remember_activity(active, presentation):
            new_activities.append(presentation)

    elif kind == FrameKind.TERMINAL:
        terminal_status = _TERMINAL_EVENTS[frame.type]
        active["phase"] = terminal_status
        if frame.type == "execution.completed":
            answer = str(frame.payload.get("answer") or "")
            if answer:
                content_changed = _apply_state_answer(active, answer) or content_changed
            if isinstance(frame.payload.get("result"), dict):
                active["result"] = frame.payload["result"]
            response_started = True
            response_completed = True
        elif frame.type == "execution.failed":
            active["error"] = str(frame.payload.get("error") or "erro desconhecido")
        elif frame.type == "execution.cancelled":
            partial = frame.payload.get("partial_answer")
            if partial:
                content_changed = _apply_state_answer(active, str(partial)) or content_changed
        presentation = present_activity_frame(frame)
        if presentation is not None and _remember_activity(active, presentation):
            new_activities.append(presentation)

    elif kind == FrameKind.TRANSPORT:
        if frame.type == "execution.realtime_unavailable":
            transport_degraded = True
            active["realtime_degraded"] = True

    else:
        if frame.type == "execution.phase.changed":
            phase = str(frame.payload.get("phase") or "")
            if phase:
                active["phase"] = phase
                if phase == "response_streaming":
                    response_started = True
                elif phase == "finalizing" and active.get("content"):
                    response_started = True
                    response_completed = True
                elif phase == "cancel_requested":
                    active["cancel_requested"] = True
        elif frame.type == "execution.cancel_requested":
            active["phase"] = "cancel_requested"
            active["cancel_requested"] = True
        presentation = present_activity_frame(frame)
        if presentation is not None and _remember_activity(active, presentation):
            new_activities.append(presentation)

    active["response_started"] = response_started
    active["response_completed"] = response_completed
    return ObservationUpdate(
        kind=kind,
        content_changed=content_changed,
        terminal_status=terminal_status,
        response_started=response_started,
        response_completed=response_completed,
        transport_degraded=transport_degraded,
        new_activities=tuple(new_activities),
    )


def present_activity_frame(frame: ObservedFrame) -> ActivityPresentation | None:
    return _present_activity(frame.type, frame.sequence, frame.payload)


def present_activity_record(record: dict[str, Any]) -> ActivityPresentation | None:
    event_type = str(record.get("type") or "")
    sequence = record.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        sequence = None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return _present_activity(event_type, sequence, payload)


def _present_activity(
    event_type: str,
    sequence: int | None,
    payload: dict[str, Any],
) -> ActivityPresentation | None:
    if event_type in {"assistant.delta", "heartbeat", "execution.state", "execution.realtime_unavailable"}:
        return None

    if event_type == "execution.started":
        return ActivityPresentation(sequence, event_type, "Execução iniciada", status="success")
    if event_type == "execution.phase.changed":
        phase = str(payload.get("phase") or "")
        label = phase_label(phase)
        if not label:
            return None
        status = "success" if phase in {"response_streaming", "finalizing", "completed"} else "running"
        return ActivityPresentation(sequence, event_type, label.rstrip("."), status=status)
    if event_type == "agent.iteration.started":
        iteration = payload.get("iteration")
        maximum = payload.get("max_iterations")
        return ActivityPresentation(
            sequence,
            event_type,
            f"Análise · iteração {iteration} de {maximum}",
            status="running",
        )
    if event_type == "agent.decision":
        actions = [str(value) for value in payload.get("actions") or []]
        decision = str(payload.get("decision") or "")
        title = "Próxima ação definida"
        detail = ", ".join(actions) if actions else decision or None
        return ActivityPresentation(sequence, event_type, title, detail=detail, status="success")
    if event_type == "agent.max_iterations_reached":
        return ActivityPresentation(
            sequence,
            event_type,
            "Limite de iterações atingido",
            detail=f"{payload.get('iterations')} de {payload.get('max_iterations')}",
            status="error",
        )
    if event_type == "context.loaded":
        turns = payload.get("history_turns")
        return ActivityPresentation(
            sequence,
            event_type,
            "Contexto carregado",
            detail=f"{turns} turnos de histórico" if turns is not None else None,
            status="success",
        )
    if event_type == "context.budget.exceeded":
        return ActivityPresentation(
            sequence,
            event_type,
            "Contexto compactado para respeitar o budget",
            status="success",
        )
    if event_type == "context.snapshot.created":
        return ActivityPresentation(
            sequence,
            event_type,
            "Snapshot de contexto criado",
            detail=f"motivo: {payload.get('reason')}" if payload.get("reason") else None,
            status="success",
        )
    if event_type == "context.retrieved":
        return ActivityPresentation(
            sequence,
            event_type,
            "Contexto global recuperado",
            detail=f"{payload.get('matches', 0)} correspondências",
            status="success",
        )
    if event_type == "skill.requested":
        names = ", ".join(str(value) for value in payload.get("skills") or [])
        return ActivityPresentation(
            sequence,
            event_type,
            "Skill solicitada",
            detail=names or None,
            status="running",
        )
    if event_type == "skill.context.loaded":
        names = ", ".join(str(value) for value in payload.get("skills") or [])
        return ActivityPresentation(
            sequence,
            event_type,
            "Conhecimento da skill carregado",
            detail=names or None,
            status="success",
        )
    if event_type == "skill.context.released":
        names = ", ".join(str(value) for value in payload.get("skills") or [])
        return ActivityPresentation(
            sequence,
            event_type,
            "Contexto temporário da skill liberado",
            detail=names or None,
            status="success",
        )
    if event_type == "schema.inspected":
        return ActivityPresentation(
            sequence,
            event_type,
            "Schema do banco inspecionado",
            detail=f"{payload.get('table_count', 0)} tabelas",
            status="success",
        )
    if event_type == "plan.created":
        return ActivityPresentation(
            sequence,
            event_type,
            "Plano de análise criado",
            detail=f"{payload.get('step_count', 0)} etapas",
            status="success",
        )
    if event_type == "llm.started":
        return ActivityPresentation(sequence, event_type, "Analisando evidências", status="running")
    if event_type == "llm.completed":
        return ActivityPresentation(sequence, event_type, "Análise do modelo concluída", status="success")
    if event_type == "tool.started":
        tool = str(payload.get("tool") or "ferramenta")
        arguments = payload.get("arguments")
        detail = _format_detail(arguments)
        title = "Consultando o banco de dados" if tool == "database" else f"Executando ferramenta: {tool}"
        return ActivityPresentation(sequence, event_type, title, detail=detail, status="running")
    if event_type == "tool.completed":
        tool = str(payload.get("tool") or "ferramenta")
        result = payload.get("result")
        return ActivityPresentation(
            sequence,
            event_type,
            f"Ferramenta concluída: {tool}",
            detail=_format_detail(result),
            status="success",
        )
    if event_type == "tool.failed":
        tool = str(payload.get("tool") or "ferramenta")
        return ActivityPresentation(
            sequence,
            event_type,
            f"Falha na ferramenta: {tool}",
            detail=str(payload.get("error") or "erro desconhecido"),
            status="error",
        )
    if event_type == "sql.generated":
        return ActivityPresentation(
            sequence,
            event_type,
            "Consulta SQL preparada",
            detail=str(payload.get("sql") or "") or None,
            status="success",
        )
    if event_type == "sql.executed":
        detail = f"{payload.get('row_count', 0)} linhas"
        if payload.get("truncated"):
            detail += " · resultado truncado"
        return ActivityPresentation(
            sequence,
            event_type,
            "Consulta SQL executada",
            detail=detail,
            status="success",
        )
    if event_type == "visualization.selected":
        title = str(payload.get("title") or payload.get("type") or "Visualização")
        return ActivityPresentation(
            sequence,
            event_type,
            "Visualização selecionada",
            detail=title,
            status="success",
        )
    if event_type == "answer.started":
        return ActivityPresentation(sequence, event_type, "Resposta iniciada", status="success")
    if event_type == "answer.generated":
        return ActivityPresentation(sequence, event_type, "Resposta gerada", status="success")
    if event_type == "answer.completed":
        return ActivityPresentation(sequence, event_type, "Resposta concluída", status="success")
    if event_type == "execution.cancel_requested":
        return ActivityPresentation(sequence, event_type, "Cancelamento solicitado", status="running")
    if event_type == "execution.cancelled":
        return ActivityPresentation(sequence, event_type, "Execução interrompida", status="success")
    if event_type == "execution.completed":
        return ActivityPresentation(sequence, event_type, "Execução concluída", status="success")
    if event_type == "execution.failed":
        return ActivityPresentation(
            sequence,
            event_type,
            "Execução falhou",
            detail=str(payload.get("error") or "erro desconhecido"),
            status="error",
        )
    return ActivityPresentation(sequence, event_type, event_type, detail=_format_detail(payload))


def _remember_activity(active: dict[str, Any], presentation: ActivityPresentation) -> bool:
    seen = active.setdefault("seen_activity_sequences", set())
    sequence = presentation.sequence
    if sequence is not None and sequence in seen:
        return False
    if sequence is not None:
        seen.add(sequence)
    active.setdefault("activities", []).append(presentation.as_dict())
    return True


def _apply_state_answer(active: dict[str, Any], candidate: str) -> bool:
    current = str(active.get("content") or "")
    if not candidate or candidate == current:
        return False
    if candidate.startswith(current):
        active["content"] = candidate
        return True
    if current.startswith(candidate):
        return False
    active["content"] = candidate
    return True


def _format_detail(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    try:
        return json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except (TypeError, ValueError):
        return str(value)
