import asyncio
import signal

from package.agent.cache.runner_health import RunnerHealthStore
from package.agent.composer.agent import compose_default_skills, compose_tools
from package.agent.composer.runtime import compose_agent_program
from package.runner.composition.agent import AgentRuntimeFactory
from package.runner.composition.context import compose_context_manager
from package.runner.composition.database import compose_agent_database
from package.runner.composition.llm import compose_llm
from package.runner.composition.redis import compose_redis
from package.runner.composition.tools import compose_user_database_tool
from package.runner.composition.worker import compose_worker
from package.runner.runtime.health import RunnerHealthReporter
from package.runner.runtime.lifecycle import ShutdownSignal
from package.runner.runtime.unavailable import UnavailableRuntimeFactory
from package.runner.settings import RunnerSettings


async def run() -> None:
    settings = RunnerSettings()
    engine, session_factory = compose_agent_database(settings.agent_database_url)
    redis, hot_state, event_stream = compose_redis(
        redis_url=settings.redis_url,
        key_prefix=settings.redis_key_prefix,
        ttl_seconds=settings.execution_hot_state_ttl_seconds,
        stream_maxlen=settings.redis_stream_maxlen,
        stream_read_block_ms=settings.redis_stream_read_block_ms,
        stream_read_count=settings.redis_stream_read_count,
    )

    shutdown = ShutdownSignal()
    _install_shutdown_handlers(shutdown)
    health_store = RunnerHealthStore(
        redis,
        key_prefix=settings.redis_key_prefix,
        ttl_seconds=settings.runner_health_ttl_seconds,
    )
    health_reporter = RunnerHealthReporter(
        store=health_store,
        runner_id=settings.runner_id,
        heartbeat_seconds=settings.runner_health_heartbeat_seconds,
    )

    provider_name = settings.llm_provider.value
    try:
        database_tool = compose_user_database_tool(
            path=settings.user_database_path,
            connection_timeout_seconds=settings.user_database_connection_timeout_seconds,
            query_timeout_seconds=settings.user_database_query_timeout_seconds,
            max_rows=settings.user_database_max_rows,
            progress_handler_steps=settings.user_database_progress_handler_steps,
        )
        tools = compose_tools(database_tool)
        skills = compose_default_skills()
        llm = compose_llm(settings)
        profile = llm.profile
        context_manager = compose_context_manager(
            llm=llm,
            skills=skills,
            session_factory=session_factory,
            context_budget_percent=settings.agent_context_budget_percent,
            summary_fallback_max_messages=settings.agent_context_summary_fallback_max_messages,
            summary_fallback_max_chars_per_message=(
                settings.agent_context_summary_fallback_max_chars_per_message
            ),
            retriever_default_limit=settings.agent_context_retriever_default_limit,
            retriever_max_limit=settings.agent_context_retriever_max_limit,
        )
        program = compose_agent_program(
            llm=llm,
            tools=tools,
            context_manager=context_manager,
        )
        runtime_factory = AgentRuntimeFactory(
            program=program,
            hot_state=hot_state,
            event_stream=event_stream,
            session_factory=session_factory,
            max_iterations=settings.agent_runtime_max_iterations,
            max_sql_retries=settings.agent_runtime_max_sql_retries,
            max_parallel_tool_calls_per_tool=settings.agent_tool_max_concurrency_per_tool,
            projection_max_activities=settings.observer_projection_max_activities,
        )
        await health_reporter.mark_ready(
            provider=profile.provider,
            model=profile.model,
        )
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        runtime_factory = UnavailableRuntimeFactory(
            f"Agente indisponível: não foi possível inicializar o provider LLM: {error}"
        )
        await health_reporter.mark_unavailable(
            provider=provider_name,
            model=None,
            error=error,
        )

    worker = compose_worker(
        session_factory=session_factory,
        runtime_factory=runtime_factory,
        runner_id=settings.runner_id,
        batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
        poll_interval_seconds=settings.outbox_poll_interval_seconds,
        retry_base_delay_seconds=settings.outbox_retry_base_delay_seconds,
        retry_max_delay_seconds=settings.outbox_retry_max_delay_seconds,
        retry_exponent_cap=settings.outbox_retry_exponent_cap,
        health_reporter=health_reporter,
        shutdown=shutdown,
    )
    health_task = asyncio.create_task(health_reporter.run(shutdown))

    try:
        await worker.run()
    finally:
        shutdown.request()
        await health_task
        await health_reporter.clear()
        await redis.aclose()
        await engine.dispose()


def _install_shutdown_handlers(shutdown: ShutdownSignal) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown.request)
        except (NotImplementedError, RuntimeError):
            pass


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
