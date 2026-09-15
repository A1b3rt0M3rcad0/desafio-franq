from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedisConfig:
    url: str
    hot_state_ttl_seconds: int = 21_600
    stream_maxlen: int = 5_000
