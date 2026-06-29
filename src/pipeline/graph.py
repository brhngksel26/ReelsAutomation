from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from src.pipeline.nodes.idea import generate_idea, validate_idea
from src.pipeline.nodes.memory import memory_enrichment
from src.pipeline.nodes.news import select_news
from src.pipeline.nodes.publish import publish
from src.pipeline.nodes.script import generate_script
from src.pipeline.nodes.storage import persist_metadata
from src.pipeline.nodes.video import produce_video
from src.pipeline.routers import idea_quality_router, news_availability_router
from src.pipeline.state import PipelineState

_LLM_RETRY = RetryPolicy(max_attempts=3)
_MPT_RETRY = RetryPolicy(max_attempts=3)


def build_pipeline(checkpointer: AsyncPostgresSaver) -> CompiledStateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("memory_enrichment", memory_enrichment)
    graph.add_node("select_news", select_news)
    graph.add_node("generate_idea", generate_idea, retry_policy=_LLM_RETRY)
    graph.add_node("validate_idea", validate_idea, retry_policy=_LLM_RETRY)
    graph.add_node("generate_script", generate_script, retry_policy=_LLM_RETRY)
    graph.add_node("persist_metadata", persist_metadata)
    graph.add_node("produce_video", produce_video, retry_policy=_MPT_RETRY)
    graph.add_node("publish", publish)

    graph.add_edge(START, "memory_enrichment")
    graph.add_edge("memory_enrichment", "select_news")
    graph.add_conditional_edges(
        "select_news",
        news_availability_router,
        {
            "continue": "generate_idea",
            "skip": END,
        },
    )
    graph.add_edge("generate_idea", "validate_idea")
    graph.add_conditional_edges(
        "validate_idea",
        idea_quality_router,
        {
            "continue": "generate_script",
            "retry": "generate_idea",
            "reject": END,
        },
    )
    graph.add_edge("generate_script", "persist_metadata")
    graph.add_edge("persist_metadata", "produce_video")
    graph.add_edge("produce_video", "publish")
    graph.add_edge("publish", END)

    return graph.compile(checkpointer=checkpointer)
