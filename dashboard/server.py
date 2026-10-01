"""
Local dashboard server for the Lead Finder pipeline.

Serves the dashboard UI, runs the real pipeline in the background when you
hit "Run", and streams real progress events to the browser as the agents
actually work (via progress.py - not scripted/fake data, genuine node-level
events from the running LangGraph pipeline).

Start it with:
    python dashboard/server.py
(or double-click run_dashboard.bat from the project root on Windows)

Then open http://127.0.0.1:8000 - it opens automatically.
"""

import json
import os
import queue
import sys
import threading
import traceback
import webbrowser

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Allow running this file directly (python dashboard/server.py) by putting
# the project root on sys.path so `import graph`, `import progress` etc. work.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from graph import build_graph          # noqa: E402
from output_writer import write_leads_csv  # noqa: E402
from report import generate_report     # noqa: E402
import progress                        # noqa: E402

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI()
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

_run_lock = threading.Lock()
_run_in_progress = False


def _to_web_path(path: str) -> str:
    """Turn an absolute or relative output file path into a URL under /output/."""
    filename = os.path.basename(path)
    return f"/output/{filename}"


def _run_pipeline(query: str, location: str, limit: int, max_revisions: int) -> None:
    global _run_in_progress
    try:
        progress.emit("run_started", query=query, location=location, limit=limit)

        compiled_graph = build_graph()
        initial_state = {
            "search_query": query,
            "location": location,
            "limit": limit,
            "max_revisions": max_revisions,
        }
        final_state = compiled_graph.invoke(initial_state, config={"recursion_limit": 100})

        approved = final_state.get("approved_leads", [])
        total = len(final_state.get("leads", []))

        csv_path = write_leads_csv(approved)
        report_path = generate_report(final_state)

        progress.emit(
            "run_complete",
            approved=len(approved),
            total=total,
            csv_url=_to_web_path(csv_path),
            report_url=_to_web_path(report_path),
        )
    except Exception as e:  # noqa: BLE001 - surfacing any failure to the UI
        traceback.print_exc()
        progress.emit("run_error", message=str(e))
    finally:
        with _run_lock:
            _run_in_progress = False


@app.get("/")
async def index():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))


@app.get("/api/status")
async def status():
    with _run_lock:
        return {"running": _run_in_progress}


@app.post("/api/run")
async def start_run(request: Request):
    global _run_in_progress
    data = await request.json()

    query = (data.get("query") or "").strip()
    location = (data.get("location") or "").strip()
    try:
        limit = int(data.get("limit") or 5)
        max_revisions = int(data.get("max_revisions") or 2)
    except (TypeError, ValueError):
        return JSONResponse({"error": "limit and max_revisions must be numbers"}, status_code=400)

    if not query or not location:
        return JSONResponse({"error": "query and location are required"}, status_code=400)

    with _run_lock:
        if _run_in_progress:
            return JSONResponse({"error": "A run is already in progress"}, status_code=409)
        _run_in_progress = True

    thread = threading.Thread(
        target=_run_pipeline, args=(query, location, limit, max_revisions), daemon=True
    )
    thread.start()

    return {"status": "started"}


@app.get("/api/stream")
async def stream():
    q = progress.subscribe()

    def event_gen():
        try:
            while True:
                try:
                    event = q.get(timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            progress.unsubscribe(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
