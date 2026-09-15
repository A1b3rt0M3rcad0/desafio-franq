from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedisConfig:
    url: str
    key_prefix: str
    hot_state_ttl_seconds: int
    stream_maxlen: int
    stream_read_block_ms: int
    stream_read_count: int
