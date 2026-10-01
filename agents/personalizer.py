"""
Personalizer agent.

Takes the current lead (with its signal, if found) and drafts a short,
specific cold outreach email. If critic_feedback is present on the lead
(i.e. this is a revision), it rewrites addressing that feedback instead
of starting fresh.
"""

import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from state import GraphState
from llm_utils import invoke_with_retry, get_text
from progress import emit

DRAFT_MODEL = "gemini-3.5-flash-lite"

SENDER_NAME = os.environ.get("SENDER_NAME", "Ibbad")

# Two different offers depending on whether the business has a website.
# No website -> pitch building one. Has a website (with or without a
# specific signal) -> pitch an automation/booking agent on top of it.
OFFER_NO_WEBSITE = (
    "I build websites for small businesses. I noticed this business doesn't "
    "have one online yet, and I could put one together for them."
)
OFFER_HAS_WEBSITE = (
    "I build AI-powered automation systems (booking agents, lead handling, "
    "customer inquiry automation) that plug into an existing website, so "
    "customers can book or ask questions without anyone manually replying."
)


def _build_prompt(lead: dict) -> str:
    has_website = bool(lead.get("website"))

    if not has_website:
        offer = OFFER_NO_WEBSITE
        signal_line = "This business does not appear to have a website listed."
    else:
        offer = OFFER_HAS_WEBSITE
        if lead.get("signal_found"):
            signal_line = f'A specific thing I noticed about their business: "{lead["signal"]}"'
        elif lead.get("category"):
            signal_line = (
                f'I could not find a specific signal from their website. Their business '
                f'category is "{lead["category"]}". Anchor the email on a real, common '
                f'pain point for that specific type of business (e.g. missed calls, manual '
                f'booking, slow quote turnaround) rather than being vague. Do not claim this '
                f'business has that problem specifically, frame it as a common issue in that '
                f'line of work and ask if it applies to them.'
            )
        else:
            signal_line = (
                "I could not find a specific signal from their website, so keep this "
                "general but still genuine and non-generic, reference the business by "
                "name and industry, don't pretend to know something you don't."
            )

    revision_note = ""
    if lead.get("critic_feedback"):
        revision_note = f"""
IMPORTANT: this is a revision. A reviewer rejected the previous draft
for this reason: "{lead['critic_feedback']}"
Fix that specific problem in this new draft.
"""

    return f"""Write a short, genuine-sounding cold outreach email from {SENDER_NAME},
an AI automation freelancer, to the business below.

Business name: {lead['name']}
{signal_line}

What {SENDER_NAME} offers: {offer}
{revision_note}
Rules:
- 4-6 sentences max. No corporate fluff, no "I hope this email finds you well."
- Reference the specific signal naturally, don't just list it like a report.
- End with a low-pressure call to action (a quick reply or short call), not
  a hard sell.
- Do not use em dashes.
- Output format exactly:
Subject: <subject line>
Body: <email body>
"""


def _parse_draft(raw: str) -> tuple[str, str]:
    subject = ""
    body = ""
    lines = raw.strip().split("\n")
    body_lines: list[str] = []
    in_body = False
    for line in lines:
        if line.strip().lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
        elif line.strip().lower().startswith("body:"):
            in_body = True
            rest = line.split(":", 1)[1].strip()
            if rest:
                body_lines.append(rest)
        elif in_body:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return subject or "Quick question", body or raw.strip()


def personalizer_node(state: GraphState) -> GraphState:
    idx = state["current_lead_index"]
    lead = state["leads"][idx]

    action = "Revising" if lead.get("critic_feedback") else "Drafting"
    print(f"[PERSONALIZER] {action} email for {lead['name']}...")
    emit(
        "agent_active", agent="personalizer",
        detail=f'{action} email for {lead["name"]}',
        lead_name=lead["name"], revision=lead.get("revision_count", 0),
    )

    llm = ChatGoogleGenerativeAI(model=DRAFT_MODEL, temperature=0.6)
    prompt = _build_prompt(lead)
    response = invoke_with_retry(llm, [HumanMessage(content=prompt)])

    subject, body = _parse_draft(get_text(response))
    lead["email_subject"] = subject
    lead["email_body"] = body
    print(f"    -> subject: {subject}")
    emit("personalizer_drafted", name=lead["name"], subject=subject)
    emit("agent_idle", agent="personalizer")

    state["leads"][idx] = lead
    return state