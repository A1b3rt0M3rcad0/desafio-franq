from redis.asyncio import Redis


def create_redis_connection(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)
