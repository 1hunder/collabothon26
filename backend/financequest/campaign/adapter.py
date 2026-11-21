"""Gate scenario (no manifest) -> minimal manifest dict, per shared contract section 4.

Reads only player-facing, already disguised scenario fields: beats ``{day|story_day, title|
headline, text|facts}``, ``chart_series`` ``{day, open?, high?, low?, close|price}``.
"""

from __future__ import annotations

from typing import Any

from financequest.db.models import Scenario


class NotPlayable(Exception):
    pass


def _day(x: dict[str, Any]) -> int:
    return int(x.get("day", x.get("story_day", 0)))


def _text(b: dict[str, Any]) -> str:
    if b.get("text"):
        return str(b["text"])
    facts = b.get("facts") or []
    return " ".join(str(f) for f in facts) or str(b.get("headline") or b.get("title") or "")


def adapt_gate_scenario(sc: Scenario) -> dict[str, Any]:
    beats = sorted(sc.beats or [], key=_day)
    chart = sorted(sc.chart_series or [], key=_day)
    if not beats or not chart:
        raise NotPlayable("needs beats and a chart")
    sdays = sc.story_days if isinstance(sc.story_days, dict) else {}
    today = int(sdays.get("today", _day(beats[-1])))
    horizon = int(sdays.get("horizon_end", _day(chart[-1])))
    if horizon <= today:
        raise NotPlayable("chart ends at story today")
    series = []
    for p in chart:
        c = p.get("close", p.get("price"))
        series.append({"day": _day(p), "open": p.get("open", c), "high": p.get("high", c),
                       "low": p.get("low", c), "close": c})  # fmt: skip
    news_beat = beats[-1]
    earlier = beats[:-1] or beats[:1]
    intro_day = _day(earlier[0])
    evidence: list[dict[str, Any]] = []
    for i, b in enumerate(earlier):
        evidence.append({
            "id": f"B{i}", "checkpoint": "G0",
            "location": "library" if i % 2 == 0 else "market_square",
            "kind": "announcement", "title": str(b.get("headline") or b.get("title") or f"Notice {i + 1}"),
            "player_text": _text(b), "key": i == 0,
        })  # fmt: skip
    gated = []
    for i, ev in enumerate(evidence[:2]):
        gated.append({
            "id": f"X{i}", "checkpoint": "G0", "location": ev["location"], "kind": "opinion",
            "title": f"A closer look: {ev['title']}",
            "player_text": f"On a closer read: {ev['player_text']}", "key": False,
        })  # fmt: skip
    evidence += gated
    news_ev = {
        "id": "NEWS", "checkpoint": "G1", "location": "market_square", "kind": "announcement",
        "title": str(news_beat.get("headline") or news_beat.get("title") or "News"),
        "player_text": _text(news_beat), "key": True,
    }  # fmt: skip
    evidence.append(news_ev)
    g0 = [e["id"] for e in evidence if e["checkpoint"] == "G0"]
    return {
        "meta": {"campaign_title": sc.invented_name, "currency": "GP", "case_id": str(sc.id)},
        "world": {
            "setting_name": "the realm",
            "company_name": sc.invented_name,
            "market_name": "Market Square",
        },  # fmt: skip
        "checkpoints": [
            {"id": "G0", "role": "intro", "story_day": intro_day, "label": "The opening scene"},
            {"id": "G1", "role": "disclosure", "story_day": _day(news_beat), "label": "News"},
            {"id": "G2", "role": "decision", "story_day": today, "label": "Decision day"},
        ],
        "company_card": {
            "name": sc.invented_name,
            "trade": sc.industry_shown,
            "size": "",
            "key_figures": [],
        },  # fmt: skip
        "evidence": evidence,
        "documents": [
            {"id": "DOC-0", "checkpoint": "G0", "title": "Archive notes", "evidence_ids": g0}
        ],  # fmt: skip
        "characters": [
            {
                "id": "broker",
                "name": "The Broker",
                "role": "Exchange broker",
                "location": "market_square",
                "may_reveal": {"G0": g0[:1]},
                "never": [],
            },
            {
                "id": "scholar",
                "name": "The Scholar",
                "role": "Independent scholar",
                "location": "library",
                "may_reveal": {"G0": g0[:1]},
                "never": [],
            },
            {
                "id": "treasurer",
                "name": "The Treasurer",
                "role": "Speaks for management",
                "location": "tavern",
                "may_reveal": {"G0": g0[:1]},
                "never": [],
            },
        ],  # fmt: skip
        "encounters": [
            {
                "id": "ENC-A",
                "title": "Find the public report",
                "checkpoint": "G0",
                "location": "library",
                "kind": "public_report",
                "dc": None,
                "skill_flavor": "",
                "evidence_ids": g0[:1],
                "success_clue_id": "X0",
                "failure_forward": "Ask the scholar; the same facts are available elsewhere.",
            },
            {
                "id": "ENC-B",
                "title": "Spot the unusual figure",
                "checkpoint": "G0",
                "location": "market_square",
                "kind": "unusual_figure",
                "dc": None,
                "skill_flavor": "",
                "evidence_ids": g0[:1],
                "success_clue_id": "X1",
                "failure_forward": "Ask the broker; the same facts are available elsewhere.",
            },
        ],  # fmt: skip
        "news": {
            "checkpoint": "G1",
            "time_skip_days": max(1, _day(news_beat) - intro_day),
            "headline": news_ev["title"],
            "summary": news_ev["player_text"],
            "evidence_ids": ["NEWS"],
        },  # fmt: skip
        "prices": {"decision_story_day": today, "horizon_story_day": horizon},
        "rubric": None,
        "campaign_location_seeds": [],
        "debrief": {"questions": ["What would you check first next time?"]},
        "_series": series,
    }
