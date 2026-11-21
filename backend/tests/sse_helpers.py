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


# ---- decisions throughout the campaign ----
HOLD_TEXT = "I keep my coins for now and watch how this unfolds."
DECISION_TEXT = "I invest 400 coins: the cash flow worries me, so I take a measured stake."
_ROUTE = ("library", "tavern", "market_square", "library", "market_square", "tavern")


def campaign_state(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    r = client.get(f"/campaigns/{cid}", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


def answer_scene(
    client: TestClient, h: dict[str, str], cid: str, text: str | None = None
) -> dict[str, Any] | None:
    """Answers the open decision scene, if any (a hold, unless told otherwise)."""
    scene = campaign_state(client, h, cid).get("market_scene")
    if not scene:
        return None
    return post_sse(client, f"/campaigns/{cid}/actions", h, {"text": text or HOLD_TEXT})[1]


def play_to_decide(
    client: TestClient, h: dict[str, str], cid: str, decision_text: str = DECISION_TEXT
) -> dict[str, Any]:
    """Investigates until the seal is open: moves around, holds at the story's earlier decision
    scenes and answers the day-of-decision scene with ``decision_text``."""
    for i in range(30):
        state = campaign_state(client, h, cid)
        if state["can_decide"]:
            return state
        scene = state.get("market_scene")
        if scene:
            text = decision_text if scene["beat"] == "decision" else HOLD_TEXT
            post_sse(client, f"/campaigns/{cid}/actions", h, {"text": text})
            continue
        key = _ROUTE[i % len(_ROUTE)]
        loc = next(x["id"] for x in state["locations"] if x["key"] == key)
        r = client.post(f"/campaigns/{cid}/move", json={"location_id": loc}, headers=h)
        assert r.status_code == 200, r.text
    raise AssertionError("never reached the seal")
