def outbox_retry_delay(attempt: int) -> float:
    return min(60.0, 2.0 ** min(attempt, 6))
