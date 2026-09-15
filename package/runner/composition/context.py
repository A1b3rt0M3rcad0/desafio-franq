from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from package.agent.context.budget import (
    ApproximateTokenEstimator,
    ContextBudgetManager,
    ContextBudgetPolicy,
)
from package.agent.context.builder import ContextBuilder
from package.agent.context.manager import ContextManager
from package.agent.context.retrieval import GlobalContextRetriever
from package.agent.context.summary import FallbackContextSummarizer, LLMContextSummarizer
from package.agent.database.repositories.context import (
    ContextSnapshotRepository,
    GlobalContextRepository,
)
from package.agent.llm.contracts import LLMClient
from package.agent.prompt.system import SYSTEM_PROMPT
from package.agent.skills.registry import SkillRegistry


def compose_context_manager(
    *,
    llm: LLMClient,
    skills: SkillRegistry,
    session_factory: async_sessionmaker[AsyncSession],
    context_window_tokens: int,
    context_budget_percent: float,
    chars_per_token: float,
    summary_fallback_max_messages: int,
    summary_fallback_max_chars_per_message: int,
    retriever_default_limit: int,
    retriever_max_limit: int,
) -> ContextManager:
    estimator = ApproximateTokenEstimator(chars_per_token=chars_per_token)
    budget_manager = ContextBudgetManager(
        estimator=estimator,
        policy=ContextBudgetPolicy(
            model_context_window_tokens=context_window_tokens,
            dynamic_context_percentage=context_budget_percent,
        ),
    )
    snapshot_store = ContextSnapshotRepository(session_factory)
    global_context_store = GlobalContextRepository(session_factory)
    retriever = GlobalContextRetriever(
        store=global_context_store,
        default_limit=retriever_default_limit,
        max_limit=retriever_max_limit,
    )
    summarizer = LLMContextSummarizer(
        llm=llm,
        fallback=FallbackContextSummarizer(
            max_messages=summary_fallback_max_messages,
            max_chars_per_message=summary_fallback_max_chars_per_message,
        ),
    )
    return ContextManager(
        builder=ContextBuilder(),
        skills=skills,
        system_prompt=SYSTEM_PROMPT,
        budget_manager=budget_manager,
        summarizer=summarizer,
        snapshot_store=snapshot_store,
        global_context_store=global_context_store,
        retriever=retriever,
    )
