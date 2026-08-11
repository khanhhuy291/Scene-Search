from agents.state import AgentState


async def analyze_node(state: AgentState) -> dict:
    """Analyze the query and return analysis."""
    query = state.get("query", "")

    # TODO(agent): Replace the scaffold response with scene-aware query analysis.

    analysis = f"Analysis: {query}"

    return {"analysis": analysis}


async def respond_node(state: AgentState) -> dict:
    """Create a response from the analysis."""
    analysis = state.get("analysis", "")
    error = state.get("error")

    if error:
        return {"response": f"Error: {error}"}

    # TODO(agent): Generate responses from retrieved scene context.
    response = f"Result based on analysis: {analysis}"

    return {"response": response}
