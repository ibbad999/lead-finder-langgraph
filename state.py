"""
Shared state schema for the LangGraph lead-finder pipeline.

Keeping this in one file so every agent node reads/writes the same shape
and it's obvious at a glance what data flows through the graph.
"""

from typing import TypedDict, Optional, List


class Lead(TypedDict, total=False):
    """One business found by the Researcher agent."""

    name: str
    address: str
    website: Optional[str]
    phone: Optional[str]
    place_id: str
    category: Optional[str]        # e.g. "Plumber", from Places - fallback context
                                    # when no specific signal is found

    # Filled in by the Researcher after scraping the website
    signal: Optional[str]          # the specific, concrete thing worth mentioning
    signal_found: bool             # False if we couldn't find anything usable

    # Filled in by the Personalizer
    email_subject: Optional[str]
    email_body: Optional[str]

    # Filled in by the Critic
    critic_verdict: Optional[str]      # "approved" | "revise"
    critic_feedback: Optional[str]     # why, if "revise"
    revision_count: int


class GraphState(TypedDict, total=False):
    """The full state object passed between LangGraph nodes."""

    # Inputs (set once at the start)
    search_query: str      # e.g. "real estate agencies"
    location: str           # e.g. "Lahore, Pakistan"
    limit: int              # max number of leads to process

    # Working data
    leads: List[Lead]
    current_lead_index: int   # which lead in `leads` is being processed right now

    # Output
    approved_leads: List[Lead]
    max_revisions: int