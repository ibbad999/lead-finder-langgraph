"""
Entrypoint.

Usage:
    python run.py --query "real estate agencies" --location "Lahore, Pakistan" --limit 5

Requires .env populated (copy .env.example -> .env and fill in keys).
"""

import argparse
import os
from dotenv import load_dotenv

load_dotenv()

# Optional LangSmith tracing - only turns on if the env vars are set.
if os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true":
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

from graph import build_graph
from output_writer import write_leads_csv
from report import generate_report


def main():
    parser = argparse.ArgumentParser(description="LangGraph multi-agent lead finder")
    parser.add_argument("--query", required=True, help='e.g. "real estate agencies"')
    parser.add_argument("--location", required=True, help='e.g. "Lahore, Pakistan"')
    parser.add_argument("--limit", type=int, default=5, help="max businesses to process")
    parser.add_argument("--max-revisions", type=int, default=2)
    args = parser.parse_args()

    required_keys = ["GOOGLE_API_KEY", "GOOGLE_PLACES_API_KEY"]
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )

    app = build_graph()

    initial_state = {
        "search_query": args.query,
        "location": args.location,
        "limit": args.limit,
        "max_revisions": args.max_revisions,
    }

    print(f"Searching for '{args.query}' in '{args.location}' (limit {args.limit})...")
    final_state = app.invoke(initial_state, config={"recursion_limit": 100})

    approved = final_state.get("approved_leads", [])
    print(f"\nDone. {len(approved)}/{len(final_state.get('leads', []))} leads approved.")

    csv_path = write_leads_csv(approved)
    print(f"Written to {csv_path}")

    report_path = generate_report(final_state)
    print(f"Written to {report_path}  (open this in a browser - it's the shareable one)")


if __name__ == "__main__":
    main()