# Lead Finder | LangGraph Multi-Agent Outreach Tool

A multi-agent system that finds local businesses via Google Places, researches
each one's website for a real, specific signal (outdated site, no online
booking, no automation, etc.), drafts a personalized cold outreach email
referencing that signal, and runs the draft through a critic agent that
checks it for genericness or factual mismatches before it's approved.

This is a from-scratch LangGraph rebuild of an existing n8n automation
(Google Places -> signal extraction -> Gemini personalization -> Gmail
draft), used here to learn multi-agent orchestration properly rather than
as a brand-new idea.

## Architecture

```
        ┌──────────────┐
        │  Researcher  │   Google Places search + website scrape +
        │    Agent     │   Gemini signal extraction
        └──────┬───────┘
               │  leads with signals
               ▼
        ┌──────────────┐
        │ Personalizer │   Drafts one outreach email per lead,
        │    Agent     │   referencing the specific signal found
        └──────┬───────┘
               │  draft email
               ▼
        ┌──────────────┐
   ┌───►│    Critic    │   Checks draft against lead data:
   │    │    Agent     │   generic? factually wrong? too pushy?
   │    └──────┬───────┘
   │           │
   │     approved?───No──► back to Personalizer (max 2 revisions)
   │           │
   │          Yes
   │           ▼
   │    ┌──────────────┐
   └────┤   Output     │   Writes approved leads + drafts to CSV
        └──────────────┘
```

The Personalizer -> Critic loop is the actual multi-agent pattern being
practiced here: one agent evaluates and sends work back to another, rather
than a straight-line pipeline.

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   - `GOOGLE_API_KEY` 
   - `GOOGLE_PLACES_API_KEY` 

3. Run it:

   ```bash
   python run.py --query "real estate agencies" --location "Lahore, Pakistan" --limit 5
   ```

4. Check `output/leads.csv` for the results - reviewed drafts, not auto-sent.

## Notes on cost

- Google Places free monthly threshold covers small runs (a handful to a
  few dozen searches) at no cost. Check current limits on Google's pricing
  page before running large batches.
- Gemini calls are cheap at this scale (a few calls per lead).
- LangSmith tracing is optional and has a free tier (5,000 traces/month);
  leave `LANGCHAIN_TRACING_V2=false` in `.env` to skip it entirely.

## What this intentionally does NOT do (v1 scope)

- Does not auto-send emails -output is a CSV of drafts for manual review.
- Does not touch LinkedIn or Upwork.
- Does not do bulk/high-volume sending - built for quality over volume.
