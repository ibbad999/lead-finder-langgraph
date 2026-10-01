"""
Researcher agent.

Responsibilities:
1. Search Google Places for businesses matching the query + location.
2. For each business with a website, fetch the homepage and extract a
   concrete, specific "signal" worth mentioning in outreach (e.g. no
   online booking, no visible automation, outdated design, no clear
   contact form) using Gemini.

If a business has no website, or the site can't be reached, it's kept
in the list but marked signal_found=False so downstream agents know to
either skip it or fall back to a generic angle.
"""

import os
import requests
from bs4 import BeautifulSoup
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from state import GraphState, Lead
from llm_utils import invoke_with_retry, get_text
from progress import emit

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
SIGNAL_MODEL = "gemini-3.5-flash-lite"


def _search_places(query: str, location: str, limit: int) -> list[dict]:
    api_key = os.environ["GOOGLE_PLACES_API_KEY"]
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # Field mask kept minimal (Essentials/Pro tier fields only) to
        # avoid tripping the more expensive Enterprise SKU tiers.
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,"
            "places.websiteUri,places.nationalPhoneNumber,places.id,"
            "places.primaryTypeDisplayName"
        ),
    }
    payload = {
        "textQuery": f"{query} in {location}",
        "maxResultCount": min(limit, 20),
    }
    resp = requests.post(PLACES_SEARCH_URL, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("places", [])


def _fetch_homepage_text(url: str, max_chars: int = 4000) -> str | None:
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadFinderBot/1.0)"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:max_chars] if text else None


def _extract_signal(business_name: str, homepage_text: str, llm: ChatGoogleGenerativeAI) -> str | None:
    prompt = f"""You're helping a freelance automation/AI engineer find a genuine,
specific reason to reach out to a local business about improving their
online presence or workflows.

Business: {business_name}

Here is text extracted from their homepage:
---
{homepage_text}
---

Look for ONE concrete, specific, true observation from this text that would
justify a personalized outreach email. Examples of good signals:
- "No online booking or contact form visible, just a phone number"
- "Site mentions manually replying to WhatsApp inquiries"
- "No mention of automation, CRM, or online scheduling anywhere"
- "Business relies on manual quote requests via email"

Do NOT invent anything not supported by the text. If you genuinely cannot
find a specific, concrete signal, respond with exactly: NONE

Respond with either NONE, or one sentence describing the signal. Nothing else."""

    response = invoke_with_retry(llm, [HumanMessage(content=prompt)])
    text = get_text(response).strip()
    if text.upper() == "NONE" or not text:
        return None
    return text


def researcher_node(state: GraphState) -> GraphState:
    query = state["search_query"]
    location = state["location"]
    limit = state.get("limit", 5)

    emit("agent_active", agent="researcher", detail=f'Searching Places for "{query}" in {location}')
    places = _search_places(query, location, limit)
    print(f"[RESEARCHER] Found {len(places)} businesses. Checking each website...")
    emit("researcher_found", count=len(places))

    llm = ChatGoogleGenerativeAI(model=SIGNAL_MODEL, temperature=0.2)

    leads: list[Lead] = []
    for i, place in enumerate(places, 1):
        website = place.get("websiteUri")
        name = place.get("displayName", {}).get("text", "Unknown")
        print(f"[RESEARCHER] ({i}/{len(places)}) {name}")
        emit("researcher_checking", index=i, total=len(places), name=name)

        category = (place.get("primaryTypeDisplayName") or {}).get("text")

        lead: Lead = {
            "name": name,
            "address": place.get("formattedAddress", ""),
            "website": website,
            "phone": place.get("nationalPhoneNumber"),
            "place_id": place.get("id", ""),
            "category": category,
            "signal": None,
            "signal_found": False,
            "revision_count": 0,
        }

        if website:
            homepage_text = _fetch_homepage_text(website)
            if homepage_text:
                signal = _extract_signal(lead["name"], homepage_text, llm)
                if signal:
                    lead["signal"] = signal
                    lead["signal_found"] = True
                    print(f"    -> signal found: {signal}")
                    emit("researcher_signal", name=name, signal=signal)
                else:
                    print(f"    -> no specific signal found on site")
                    emit("researcher_no_signal", name=name, category=category)
            else:
                print(f"    -> could not fetch website content")
                emit("researcher_no_signal", name=name, category=category)
        else:
            print(f"    -> no website listed")
            emit("researcher_no_website", name=name, category=category)

        leads.append(lead)

    state["leads"] = leads
    state["current_lead_index"] = 0
    state["approved_leads"] = []
    emit("agent_idle", agent="researcher")
    return state