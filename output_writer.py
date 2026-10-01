"""Writes approved leads (with their final draft) to a CSV for manual review."""

import csv
import os
from datetime import datetime


def write_leads_csv(leads: list[dict], path: str | None = None) -> str:
    """Writes leads to a timestamped CSV so each run doesn't overwrite the
    last one. Returns the path actually written to.

    If `path` is given explicitly, it's used as-is (still overwrites) -
    that's for callers that want a fixed file on purpose.
    """
    if path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"output/leads_{stamp}.csv"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fieldnames = [
        "name", "address", "website", "phone", "category", "signal",
        "email_subject", "email_body", "revision_count",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow({k: lead.get(k, "") for k in fieldnames})

    return path