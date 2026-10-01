"""
Builds a shareable HTML report from a completed pipeline run.

This is the "wow, look at the agent reasoning" artifact - it doesn't just
list output emails, it shows the Critic's actual judgment on every lead:
what got approved, what got revised and re-approved, what got dropped and
why. That's the part that's actually interesting to show someone, versus
a CSV of email drafts.

Usage: called automatically by run.py after each pipeline run. Can also be
run standalone against nothing (it's just a function) - see generate_report().
"""

import os
import html as html_escape
from datetime import datetime

STATUS_STYLES = {
    "approved": {"label": "Approved", "bg": "rgba(12,163,12,0.12)", "fg": "#0ca30c", "icon": "✓"},
    "approved_after_revision": {
        "label": "Approved (revised)", "bg": "rgba(12,163,12,0.12)", "fg": "#0ca30c", "icon": "↻",
    },
    "dropped": {"label": "Dropped", "bg": "rgba(208,59,59,0.12)", "fg": "#d03b3b", "icon": "✕"},
}

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Lead Finder Run Report</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --gridline: #e1e0d9;
    --border: rgba(11,11,11,0.10);
    --accent: #2a78d6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --gridline: #2c2c2a;
      --border: rgba(255,255,255,0.10);
      --accent: #3987e5;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --gridline: #2c2c2a;
    --border: rgba(255,255,255,0.10);
    --accent: #3987e5;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 40px 16px 80px;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  header {{ margin-bottom: 28px; }}
  h1 {{ font-size: 22px; font-weight: 650; margin: 0 0 6px; }}
  .meta {{ color: var(--text-secondary); font-size: 14px; }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin: 24px 0 32px;
  }}
  .stat-tile {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
  }}
  .stat-tile .value {{
    font-size: 28px;
    font-weight: 650;
    font-variant-numeric: proportional-nums;
  }}
  .stat-tile .label {{
    font-size: 12px;
    color: var(--muted);
    margin-top: 2px;
  }}
  .lead-card {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
  }}
  .lead-head {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .lead-name {{ font-size: 16px; font-weight: 600; }}
  .lead-sub {{ color: var(--muted); font-size: 13px; margin-top: 2px; }}
  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    white-space: nowrap;
  }}
  .signal-block {{
    margin-top: 14px;
    padding: 10px 12px;
    border-left: 2px solid var(--gridline);
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.5;
  }}
  .email-block {{
    margin-top: 14px;
    border-top: 1px solid var(--gridline);
    padding-top: 14px;
  }}
  .email-subject {{ font-weight: 600; font-size: 14px; margin-bottom: 6px; }}
  .email-body {{
    font-size: 13.5px;
    line-height: 1.6;
    color: var(--text-primary);
    white-space: pre-wrap;
  }}
  .feedback-block {{
    margin-top: 14px;
    padding: 10px 12px;
    background: rgba(208,59,59,0.08);
    border-radius: 8px;
    font-size: 13px;
    color: var(--text-secondary);
  }}
  .feedback-block b {{ color: var(--text-primary); }}
  footer {{
    margin-top: 32px;
    color: var(--muted);
    font-size: 12px;
    text-align: center;
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Lead Finder Run Report</h1>
    <div class="meta">"{query}" in {location} &middot; {timestamp}</div>
  </header>

  <div class="stats">
    <div class="stat-tile"><div class="value">{total}</div><div class="label">Leads processed</div></div>
    <div class="stat-tile"><div class="value">{approved}</div><div class="label">Approved</div></div>
    <div class="stat-tile"><div class="value">{approval_rate}%</div><div class="label">Approval rate</div></div>
    <div class="stat-tile"><div class="value">{avg_revisions}</div><div class="label">Avg. revisions</div></div>
  </div>

  {lead_cards}

  <footer>Generated by report.py &middot; multi-agent pipeline: Researcher &rarr; Personalizer &rarr; Critic</footer>
</div>
</body>
</html>
"""

LEAD_CARD_TEMPLATE = """  <div class="lead-card">
    <div class="lead-head">
      <div>
        <div class="lead-name">{name}</div>
        <div class="lead-sub">{sub}</div>
      </div>
      <span class="badge" style="background:{badge_bg}; color:{badge_fg};">{badge_icon} {badge_label}</span>
    </div>
    {signal_block}
    {email_block}
    {feedback_block}
  </div>
"""


def _esc(value) -> str:
    return html_escape.escape(str(value)) if value else ""


def _lead_status(lead: dict) -> str:
    if lead.get("critic_verdict") == "approved":
        return "approved_after_revision" if lead.get("revision_count", 0) > 0 else "approved"
    return "dropped"


def _render_lead_card(lead: dict) -> str:
    status = _lead_status(lead)
    style = STATUS_STYLES[status]

    sub_parts = []
    if lead.get("category"):
        sub_parts.append(lead["category"])
    if lead.get("website"):
        sub_parts.append(lead["website"])
    else:
        sub_parts.append("no website listed")
    sub = " &middot; ".join(_esc(p) for p in sub_parts)

    if lead.get("signal_found"):
        signal_block = f'<div class="signal-block">Signal: {_esc(lead["signal"])}</div>'
    elif lead.get("category"):
        signal_block = (
            f'<div class="signal-block">No website signal found &mdash; '
            f'drafted around a common "{_esc(lead["category"])}" pain point instead.</div>'
        )
    else:
        signal_block = '<div class="signal-block">No website or category signal available.</div>'

    email_block = ""
    if lead.get("email_subject") or lead.get("email_body"):
        email_block = (
            '<div class="email-block">'
            f'<div class="email-subject">{_esc(lead.get("email_subject"))}</div>'
            f'<div class="email-body">{_esc(lead.get("email_body"))}</div>'
            "</div>"
        )

    feedback_block = ""
    if status == "dropped" and lead.get("critic_feedback"):
        feedback_block = (
            '<div class="feedback-block"><b>Critic feedback (final):</b> '
            f'{_esc(lead["critic_feedback"])}</div>'
        )

    return LEAD_CARD_TEMPLATE.format(
        name=_esc(lead.get("name", "Unknown")),
        sub=sub,
        badge_bg=style["bg"],
        badge_fg=style["fg"],
        badge_icon=style["icon"],
        badge_label=style["label"],
        signal_block=signal_block,
        email_block=email_block,
        feedback_block=feedback_block,
    )


def generate_report(state: dict, path: str | None = None) -> str:
    """Builds the HTML run report from a finished GraphState and writes it
    to disk. Returns the path written to."""
    leads = state.get("leads", [])
    approved = state.get("approved_leads", [])

    total = len(leads)
    approved_count = len(approved)
    approval_rate = round((approved_count / total) * 100) if total else 0
    avg_revisions = round(sum(l.get("revision_count", 0) for l in leads) / total, 1) if total else 0

    # Sort: approved first, then dropped - so the wins lead the page.
    ordered = sorted(leads, key=lambda l: _lead_status(l) == "dropped")
    lead_cards = "\n".join(_render_lead_card(lead) for lead in ordered)

    html_out = PAGE_TEMPLATE.format(
        query=_esc(state.get("search_query", "")),
        location=_esc(state.get("location", "")),
        timestamp=datetime.now().strftime("%b %d, %Y %H:%M"),
        total=total,
        approved=approved_count,
        approval_rate=approval_rate,
        avg_revisions=avg_revisions,
        lead_cards=lead_cards,
    )

    if path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"output/report_{stamp}.html"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_out)

    return path
