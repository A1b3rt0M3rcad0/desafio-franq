from package.runner.runtime.retry import OutboxRetryPolicy


def test_outbox_retry_policy_uses_configured_exponential_backoff() -> None:
    policy = OutboxRetryPolicy(
        base_delay_seconds=2.0,
        max_delay_seconds=60.0,
        exponent_cap=5,
    )

    assert policy.delay(1) == 2.0
    assert policy.delay(2) == 4.0
    assert policy.delay(5) == 32.0
    assert policy.delay(6) == 60.0
    assert policy.delay(100) == 60.0
