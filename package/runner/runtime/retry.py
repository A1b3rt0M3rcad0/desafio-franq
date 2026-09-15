from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutboxRetryPolicy:
    base_delay_seconds: float
    max_delay_seconds: float
    exponent_cap: int

    def delay(self, attempt: int) -> float:
        normalized_attempt = max(attempt, 1)
        exponent = min(normalized_attempt - 1, self.exponent_cap)
        return min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2**exponent),
        )
