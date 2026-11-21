"""A prepared demo hero with finished campaigns, so the Veteran has something to talk about.

The campaigns are played through the real API in-process (the scripted Campaign Master, no keys,
no network), and finished the normal way, so the Veteran's memory is built by the same code path a
player triggers. Three different playstyles give the profile something to say:

1. a hasty seller: buys on the opening, then sells in a hurry when the story turns;
2. a careful reader: holds until the ledgers are read and gives reasons every time;
3. a careful reader again, with a confident forecast: strengths and weaknesses both recur.

Pass scenario ids to play different companies (recommended: a past campaign on the same company
as the one being played is sealed while that campaign runs, so the Veteran keeps quiet about it).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlmodel import Session, select

from financequest.db.models import Scenario, ScenarioSecret
from financequest.db.models_personal import GenerationJob
from financequest.db.session import get_engine

log = logging.getLogger("financequest.veteran.demo")

STYLES: tuple[dict[str, Any], ...] = (
    {
        "scenes": {
            "opening": "I buy 300 gp: the guild ledgers look clean and the docks are busy, "
            "so I take a stake.",
            "news": "Get out before it sinks! Sell everything, quick!",
            "decision": "Get out before it sinks! Sell everything, quick!",
        },
        "forecast": 85, "confidence": "high",
        "evidence": "The crowd in the square was selling and I did not want to be the last one "
        "holding the coins when the news broke.",
        "reflection": "I sold because I was scared, not because the ledgers told me anything new. "
        "Next time I will reread my own reasons before I act on loud news in the square.",
    },
    {
        "scenes": {
            "opening": "I keep my coins until I have read the ledgers in the library.",
            "news": "The news is loud, but the cash flow ledger has not changed, so I hold and "
            "read further.",
            "decision": "I stay out because cash flow is negative while earnings look positive, "
            "and the debt is large.",
        },
        "forecast": 30, "confidence": "medium",
        "evidence": "Earnings in the ledger looked strong, but the coin that actually moved went "
        "the other way, and the debt kept growing.",
        "reflection": "Reading the cash flow next to the earnings told me more than the price "
        "board. I want to keep doing that, and to visit every place before I decide anything.",
    },
    {
        "scenes": {
            "opening": "I hold for now, because I have not seen the guild's records yet.",
            "news": "I hold through the news since the records I read do not match the rumour.",
            "decision": "I invest 200 gp because the cash flow ledger looks healthier than the "
            "crowd thinks, but I keep most of my purse.",
        },
        "forecast": 80, "confidence": "high",
        "evidence": "I compared the records with the rumours and trusted the records, but I was "
        "very sure of myself for one ledger.",
        "reflection": "I gave reasons this time, which felt good, but I was far too confident for "
        "what one ledger could tell me. Next time I will look for the clue I have not found yet.",
    },
)
ROUTE = ("library", "tavern", "market_square", "library", "market_square", "tavern")


def pick_scenarios(db: Session, wanted: list[uuid.UUID] | None, n: int) -> list[uuid.UUID]:
    """The requested scenarios, else up to ``n`` playable ones on different companies (repeating
    the first when there are fewer companies than campaigns)."""
    if wanted:
        return [wanted[i % len(wanted)] for i in range(n)]
    seen: dict[str, uuid.UUID] = {}
    for sc in db.exec(select(Scenario).where(Scenario.status == "playable")):
        sec = db.get(ScenarioSecret, sc.id)
        if sec is not None and sec.real_name not in seen:
            seen[sec.real_name] = sc.id
    ids = list(seen.values())
    if not ids:
        raise RuntimeError("no playable scenario: import a reference pack first")
    return [ids[i % len(ids)] for i in range(n)]


def _own(db: Session, sid: uuid.UUID, scenario_id: uuid.UUID) -> None:
    """Generated quests are personal: give the demo session its own job row for the scenario."""
    jobs = list(db.exec(select(GenerationJob).where(GenerationJob.scenario_id == scenario_id)))
    if not jobs or any(j.session_id == sid for j in jobs):
        return
    src = jobs[0]
    db.add(GenerationJob(
        session_id=sid, kind="extra", quest_date=date.today(), category=src.category,
        category_label=src.category_label, company=src.company, ticker=src.ticker,
        status="ready", step="Ready", scenario_id=scenario_id, detail={"demo": True},
    ))  # fmt: skip
    db.commit()


def _play(client: Any, h: dict[str, str], cid: str, scenes: dict[str, str]) -> None:
    for i in range(40):
        state = client.get(f"/campaigns/{cid}", headers=h).json()
        if state["can_decide"]:
            return
        scene = state.get("market_scene")
        if scene:
            text = scenes.get(scene["beat"], scenes["decision"])
            client.post(f"/campaigns/{cid}/actions", json={"text": text}, headers=h).read()
            continue
        loc = next(x["id"] for x in state["locations"] if x["key"] == ROUTE[i % len(ROUTE)])
        r = client.post(f"/campaigns/{cid}/move", json={"location_id": loc}, headers=h)
        r.raise_for_status()
    raise RuntimeError("the demo campaign never reached the seal")


def _ok(r: Any) -> Any:
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}")
    return r


def seed_demo_hero(
    name: str = "Tarn", hero_class: str = "investigator",
    scenario_ids: list[uuid.UUID] | None = None, campaigns: int = 3,
) -> dict[str, Any]:  # fmt: skip
    """Create a session with a hero who has finished ``campaigns`` quests. Returns the session id
    and the finished campaign ids. Runs on the scripted agents (no keys, no network)."""
    from fastapi.testclient import TestClient

    from financequest.agents.campaign.narration import AgentNarration
    from financequest.api import sse
    from financequest.api.main import create_app
    from financequest.campaign.narration import get_narration, set_narration
    from financequest.llm import DefaultFakeNodeLLM

    previous, delay = get_narration(), sse.TOKEN_DELAY_S
    set_narration(AgentNarration(DefaultFakeNodeLLM()))
    sse.TOKEN_DELAY_S = 0
    try:
        client = TestClient(create_app())  # no lifespan: no art rescan, no job recovery
        sid = _ok(client.post("/session")).json()["session_id"]
        h = {"X-Session-Id": sid}
        _ok(client.post("/hero", json={"name": name, "class": hero_class}, headers=h))
        with Session(get_engine()) as db:
            picks = pick_scenarios(db, scenario_ids, campaigns)
            for sc in dict.fromkeys(picks):
                _own(db, uuid.UUID(sid), sc)
        done: list[str] = []
        for i, sc in enumerate(picks):
            style = STYLES[i % len(STYLES)]
            body = {"interests": ["Trade"], "scenario_id": str(sc)}
            cid = _ok(client.post("/campaigns", json=body, headers=h)).json()["id"]
            _ok(client.post(f"/campaigns/{cid}/opening", headers=h)).read()
            _play(client, h, cid, style["scenes"])
            commit = {
                "action": "invest",
                "amount_eur": 0,
                "evidence": style["evidence"],
                "forecast_pct": style["forecast"],
                "confidence": style["confidence"],
            }
            _ok(client.put(f"/campaigns/{cid}/commit-draft", json=commit, headers=h))
            _ok(client.post(f"/campaigns/{cid}/lock", json=commit, headers=h))
            _ok(client.get(f"/campaigns/{cid}/reveal", headers=h))
            _ok(client.post(f"/campaigns/{cid}/debrief", headers=h)).read()
            reflection = {"text": style["reflection"]}
            _ok(client.post(f"/campaigns/{cid}/reflection", json=reflection, headers=h))
            _ok(client.post(f"/campaigns/{cid}/xp", headers=h))
            _ok(client.post(f"/campaigns/{cid}/finish", headers=h))
            done.append(cid)
            log.info("demo campaign %d/%d finished", i + 1, len(picks))
        companies = len(set(picks))
        return {"session_id": sid, "campaigns": done, "distinct_companies": companies}
    finally:
        set_narration(previous)
        sse.TOKEN_DELAY_S = delay
