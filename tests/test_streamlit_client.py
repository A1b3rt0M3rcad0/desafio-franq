from package.ui.client import parse_sse_frames


def test_parse_sse_frames_uses_logical_sequence_and_payload() -> None:
    lines = [
        "id: 12",
        "event: tool.completed",
        'data: {"execution_id":"execution-1","type":"tool.completed","sequence":12,"payload":{"tool":"database","result":{"row_count":5}}}',
        "",
    ]

    frames = list(parse_sse_frames(lines))

    assert len(frames) == 1
    assert frames[0].execution_id == "execution-1"
    assert frames[0].type == "tool.completed"
    assert frames[0].sequence == 12
    assert frames[0].payload == {"tool": "database", "result": {"row_count": 5}}


def test_parse_sse_frames_ignores_heartbeat_comments() -> None:
    lines = [
        ": keep-alive",
        "",
        "event: heartbeat",
        'data: {"execution_id":"execution-1","type":"heartbeat","sequence":null,"payload":{"timestamp":"now"}}',
        "",
    ]

    frames = list(parse_sse_frames(lines))

    assert len(frames) == 1
    assert frames[0].type == "heartbeat"
    assert frames[0].sequence is None


def test_parse_sse_frames_falls_back_to_event_id_for_sequence() -> None:
    lines = [
        "id: 7",
        "event: assistant.delta",
        'data: {"execution_id":"execution-1","type":"assistant.delta","payload":{"content":"Olá"}}',
        "",
    ]

    [frame] = list(parse_sse_frames(lines))

    assert frame.sequence == 7
    assert frame.payload["content"] == "Olá"
