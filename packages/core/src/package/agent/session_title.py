DEFAULT_SESSION_TITLE_MAX_LENGTH = 56


def build_session_title(question: str, *, max_length: int = DEFAULT_SESSION_TITLE_MAX_LENGTH) -> str:
    if max_length < 4:
        raise ValueError("max_length must be at least 4")

    normalized = " ".join(question.split()).strip()
    if not normalized:
        raise ValueError("question cannot be empty")
    if len(normalized) <= max_length:
        return normalized

    prefix = normalized[: max_length - 3].rstrip()
    return f"{prefix}..."
