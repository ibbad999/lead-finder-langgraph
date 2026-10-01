"""
Shared helper for calling Gemini with automatic retries and safely
extracting text from its response.
"""

import time
from langchain_core.messages import BaseMessage


def invoke_with_retry(llm, messages, max_attempts=4, base_delay=5.0):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return llm.invoke(messages)
        except Exception as e:
            last_error = e
            error_text = str(e)
            transient_markers = ["503", "UNAVAILABLE", "high demand", "overloaded"]
            if not any(marker.lower() in error_text.lower() for marker in transient_markers):
                raise
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            print(f"  Gemini is busy (attempt {attempt}/{max_attempts}), retrying in {delay:.0f}s...")
            time.sleep(delay)
    raise last_error


def get_text(response) -> str:
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if "text" in part:
                    parts.append(part["text"])
        return "".join(parts)
    return str(content)
