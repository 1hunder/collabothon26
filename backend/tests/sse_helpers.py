"""Parse Server-Sent Events from a TestClient response."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """[(event name, data dict)] in order; comments (heartbeats) are skipped."""
    out: list[tuple[str, dict[str, Any]]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            out.append((name, json.loads("\n".join(data))))
    return out


def post_sse(
    client: TestClient, url: str, headers: dict[str, str], json_body: Any = None
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    """POST an SSE endpoint; returns (events, the ``done`` payload)."""
    r = client.post(url, json=json_body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    done = next((d for n, d in events if n == "done"), {})
    return events, done


def names(events: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [n for n, _ in events]


def streamed_text(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(d["text"] for n, d in events if n == "token")
