"""
Critic agent.

Reviews the Personalizer's draft against the lead's actual data and
decides: approved, or sent back for revision with concrete feedback.

This is the node that makes the pipeline genuinely "multi-agent" rather
than a straight-line script: one agent's job is entirely to judge and
gate another agent's output.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from state import GraphState
from llm_utils import invoke_with_retry, get_text
from progress import emit

CRITIC_MODEL = "gemini-3.5-flash-lite"


def _build_prompt(lead: dict) -> str:
    has_signal = bool(lead.get("signal_found"))
    signal_line = lead.get("signal") or "(no specific signal was found for this lead)"

    if has_signal:
        checks = """1. Does it sound generic / templated, like it could be sent to anyone?
2. Does it claim anything about the business that isn't supported by the signal above?
3. Is it too long, too salesy, or too pushy?
4. Does it use em dashes (not allowed)?"""
    else:
        # No website signal exists for this lead, so the draft was written to
        # anchor on the business's category/industry instead (see personalizer).
        # Don't penalize it for being "generic" in the sense of not citing a
        # specific website detail - that detail doesn't exist. Only flag it if
        # it invents a claim ABOUT THIS BUSINESS SPECIFICALLY that isn't
        # supported (industry-wide pain points framed as common/possible are fine).
        checks = """1. Does it invent a specific claim about THIS business (not the industry in
   general) that isn't supported by anything known about it? Framing a common
   industry pain point as something that "often happens" or asking if it
   applies to them is fine and should NOT be flagged.
2. Does it fail to reference the business by name or industry at all (i.e. it's
   truly copy-paste boilerplate with no business-specific framing)?
3. Is it too long, too salesy, or too pushy?
4. Does it use em dashes (not allowed)?"""

    return f"""You are a strict reviewer checking a cold outreach email draft
before it goes out to a real business. Be honest and critical, not
lenient.

Business: {lead['name']}
Signal the email is supposed to reference: {signal_line}

Draft subject: {lead.get('email_subject', '')}
Draft body:
{lead.get('email_body', '')}

Check for these problems:
{checks}

If the draft has NONE of these problems, respond with exactly:
APPROVED

If it has any problem, respond with:
REVISE: <one or two sentences of concrete, specific feedback on what to fix>
"""


def critic_node(state: GraphState) -> GraphState:
    idx = state["current_lead_index"]
    lead = state["leads"][idx]

    print(f"[CRITIC] Reviewing draft for {lead['name']}...")
    emit("agent_active", agent="critic", detail=f'Reviewing draft for {lead["name"]}', lead_name=lead["name"])

    llm = ChatGoogleGenerativeAI(model=CRITIC_MODEL, temperature=0.0)
    response = invoke_with_retry(llm, [HumanMessage(content=_build_prompt(lead))])
    verdict_text = get_text(response).strip()

    if verdict_text.upper().startswith("APPROVED"):
        lead["critic_verdict"] = "approved"
        lead["critic_feedback"] = None
        print(f"    -> APPROVED")
        emit("critic_verdict", name=lead["name"], verdict="approved")
    else:
        lead["critic_verdict"] = "revise"
        feedback = verdict_text.split(":", 1)[1].strip() if ":" in verdict_text else verdict_text
        lead["critic_feedback"] = feedback
        lead["revision_count"] = lead.get("revision_count", 0) + 1
        print(f"    -> REVISE: {feedback}")
        emit("critic_verdict", name=lead["name"], verdict="revise", feedback=feedback)

    state["leads"][idx] = lead
    emit("agent_idle", agent="critic")
    return state


def route_after_critic(state: GraphState) -> str:
    """Conditional edge: decide whether to loop back to the Personalizer,
    give up and move on, or advance to the next lead."""
    idx = state["current_lead_index"]
    lead = state["leads"][idx]
    max_revisions = state.get("max_revisions", 2)

    if lead["critic_verdict"] == "approved":
        state.setdefault("approved_leads", []).append(lead)
        return "next_lead"

    if lead.get("revision_count", 0) >= max_revisions:
        # Give up on this lead after max_revisions - don't loop forever.
        return "next_lead"

    return "revise"


def advance_or_finish(state: GraphState) -> str:
    """Conditional edge after moving to the next lead: more leads to
    process, or done."""
    if state["current_lead_index"] < len(state["leads"]):
        return "personalize"
    return "done"


def next_lead_node(state: GraphState) -> GraphState:
    state["current_lead_index"] += 1
    return state