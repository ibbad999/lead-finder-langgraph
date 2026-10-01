"""
Builds the LangGraph StateGraph wiring together Researcher -> Personalizer
-> Critic, with a revise-loop back from Critic to Personalizer, and a
per-lead loop that advances until all leads are processed.
"""

from langgraph.graph import StateGraph, END

from state import GraphState
from agents.researcher import researcher_node
from agents.personalizer import personalizer_node
from agents.critic import critic_node, route_after_critic, advance_or_finish, next_lead_node


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("research", researcher_node)
    graph.add_node("personalize", personalizer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("next_lead", next_lead_node)

    graph.set_entry_point("research")
    graph.add_edge("research", "personalize")
    graph.add_edge("personalize", "critic")

    # After critic: either loop back to personalize (revise), or move to
    # the next lead (approved, or gave up after max_revisions).
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"revise": "personalize", "next_lead": "next_lead"},
    )

    # After advancing the index: either personalize the next lead, or end.
    graph.add_conditional_edges(
        "next_lead",
        advance_or_finish,
        {"personalize": "personalize", "done": END},
    )

    return graph.compile()
