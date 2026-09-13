"""Phase 2 scaffold.
The current phase intentionally keeps the runtime passive. Add the OpenAI Agents SDK
orchestrator and specialist agents here after Phase 0/1 acceptance criteria pass.
"""

try:
    from agents import Agent
except ImportError:
    Agent = None


def build_orchestrator():
    if Agent is None:
        raise RuntimeError("Install openai-agents to enable the agent runtime")
    return Agent(
        name="JobHub Job Enrichment Orchestrator",
        instructions=(
            "Phase 2 placeholder. Coordinate JobHub job validation, duplicate, metadata, "
            "skills and taxonomy specialists through approved tools only. Never access PostgreSQL directly."
        ),
    )
