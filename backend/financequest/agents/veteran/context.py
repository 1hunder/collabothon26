"""What the Veteran knows in one conversation turn, and how it is written into the prompt.

Only finished campaigns are in here. The running campaign (if any) is never loaded: its leak terms
come along only so the guard can block them.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from financequest.agents.campaign.guards import build_allowlist, whole

VETERAN_NAME = "Brannoc"
VETERAN_ID = "veteran"
HISTORY_TURNS = 8


@dataclass
class VeteranContext:
    hero_name: str
    hero_class: str
    topic: str | None  # a campaign id, "habits", or None
    profile: dict[str, Any] | None
    recent: list[dict[str, Any]]  # short memories, newest last
    focus: dict[str, Any] | None  # full detail of the campaign under discussion
    history: list[tuple[str, str]] = field(default_factory=list)  # (role, text) in this topic
    step: int = 0  # walkthrough replies already given in this topic
    running: bool = False  # a campaign is in progress (never discussed)
    leak_terms: tuple[str, ...] = ()
    deadline: float | None = None

    def seconds_left(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - time.monotonic()

    def with_deadline(self, seconds: float) -> VeteranContext:
        self.deadline = time.monotonic() + seconds
        return self

    @property
    def has_memory(self) -> bool:
        return bool(self.recent)


def _figure_texts(ctx: VeteranContext) -> list[str]:
    """Every figure the Veteran may quote: from the memories and the player's own words."""
    out: list[str] = [json.dumps(ctx.profile or {}), json.dumps(ctx.recent)]
    if ctx.focus:
        out.append(json.dumps(ctx.focus))
    return out


def allowlist(ctx: VeteranContext, typed: str = "") -> set[str]:
    return build_allowlist([*_figure_texts(ctx), typed], [len(ctx.recent)])


def _fmt_short(m: dict[str, Any]) -> str:
    real = f" (revealed: {m['real_name']})" if m.get("real_name") else ""
    pct = f", {whole(m['pnl_pct'])}%" if m.get("pnl_pct") is not None else ""
    return (
        f"Quest {m['number']}: {m['title']}, company {m['company']}{real}. Result {m['result']}"
        f"{pct}. Forecast {m['forecast']}. Tags: {', '.join(m['tags']) or 'none'}. XP {m['xp']}."
    )


def facts_block(ctx: VeteranContext) -> str:
    lines = [f"# The hero you are talking to\nClass: {ctx.hero_class}."]
    if ctx.running:
        lines.append(
            "They are in the middle of a quest right now. You know nothing about it and "
            "never discuss it."
        )
    if not ctx.recent:
        lines.append("\n# Your ledger of their quests\nEmpty: they have not finished a quest yet.")
        return "\n".join(lines)
    p = ctx.profile or {}
    lines.append("\n# Player profile (recurring = seen in two or more quests)")
    for key in ("strengths", "weaknesses", "habits"):
        rows = p.get(key) or []
        lines.append(
            f"{key.title()}: "
            + ("; ".join(f"{r['label']} ({r['count']} quests)" for r in rows) or "none yet")
        )
    lines.append(
        "Emerging (latest quest only): "
        + ("; ".join(r["label"] for r in p.get("emerging") or []) or "none")
    )
    lines.append(
        "Milestones: "
        + (
            "; ".join(f"{m['label']} (quest {m['quest']})" for m in p.get("milestones") or [])
            or "none"
        )
    )
    lines.append(
        f"Quests finished: {p.get('quests', 0)}, gains {p.get('gains', 0)}, losses {p.get('losses', 0)}, XP {p.get('xp', 0)}."
    )
    lines.append("\n# Recent quests (oldest first)")
    lines += [_fmt_short(m) for m in ctx.recent]
    f = ctx.focus
    if f:
        lines.append(f"\n# The quest you are discussing: quest {f['number']}, {f['title']}")
        real = f["real_name"] or "not revealed"
        lines.append(f"In-story company: {f['company']}. Revealed real company: {real}.")
        lines.append(
            "Decisions in order (when | action | coins | the player's own words | judgement | luck):"
        )
        for d in f["decisions"]:
            lines.append(
                f"{d['seq']}. {d['when']} ({d['day']}) | {d['action']} | {whole(d['amount_eur'])} | "
                f'"{d["text"]}" | {d["judgement"]} | {d["luck"]}'
                + (f' | their reasons, in their words: "{d["reasoning"]}"' if d.get("reasoning") else " | no reasons given")
            )
        if f.get("closing_note"):
            lines.append(f'Closing note at the seal: "{f["closing_note"]}"')
        fc = f["forecast"]
        lines.append(
            f"Forecast: {whole(fc['pct'])}% likely higher, confidence {fc['confidence']}. The price "
            f"ended {'higher' if fc['market'] == 'up' else 'lower'}. Band: {fc['band']}."
        )
        r = f["result"]
        lines.append(
            f"Result: {r['kind']}, {whole(r['pnl_pct'])}% ({whole(r['pnl_eur'])} coins of {whole(r['budget_eur'])}). XP {f['xp']}."
        )
        lines.append("Key clues they never found: " + (", ".join(f["missed"]) or "none"))
        d = f["debrief"]
        lines.append(f"Debrief: sound reasoning: {d.get('sound')} | luck: {d.get('luck')}")
        if f.get("reflection"):
            lines.append(f'Their reflection: "{f["reflection"]}"')
    return "\n".join(lines)


def history_block(ctx: VeteranContext) -> str:
    if not ctx.history:
        return ""
    who = {"player": "Hero", "veteran": "You"}
    return "\n\n# Conversation so far\n" + "\n".join(
        f"{who.get(r, r)}: {t}" for r, t in ctx.history[-HISTORY_TURNS:]
    )
