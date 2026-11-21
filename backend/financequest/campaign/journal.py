"""Projections over the event log: journal and backlog."""

from __future__ import annotations

from typing import Any

from financequest.db.models import Event

JOURNAL_TYPES = {
    "move", "action", "dice_roll", "reroll", "keen_eye", "clue_found", "buddy_q", "buddy_a",
    "news", "focus_spend", "lock", "debrief_complete",
}  # fmt: skip


def journal(events: list[Event]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        if e.type not in JOURNAL_TYPES:
            continue
        p = e.payload or {}
        if e.type == "dice_roll" and not p.get("final"):
            continue
        out.append({"seq": e.seq, "type": e.type, "ts": e.ts.isoformat(), **p})
    return out


def backlog(events: list[Event]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        p = e.payload or {}
        if e.type == "action":
            out.append({"seq": e.seq, "speaker": "You", "text": p.get("text", "")})
        elif e.type in ("dm_reply", "buddy_a"):
            who = "CommerzBuddy" if e.type == "buddy_a" else p.get("speaker", "Campaign Master")
<<<<<<< HEAD
            # the event id is the reply's audio id (GET /tts/{id}): a resumed screen can still
            # play the server voice instead of the browser's
            out.append({"seq": e.seq, "speaker": who, "text": p.get("text", ""), "audio_text_id": e.id})
=======
            entry = {"seq": e.seq, "speaker": who, "text": p.get("text", "")}
            if p.get("speaker_kind") == "npc":
                entry["speaker_kind"] = "npc"
            out.append(entry)
>>>>>>> origin/main
        elif e.type == "buddy_q":
            out.append({"seq": e.seq, "speaker": "You (to Buddy)", "text": p.get("text", "")})
    return out
