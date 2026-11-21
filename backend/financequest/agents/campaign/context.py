"""Everything an agent call sees, built from the GatedView and the event log.

``build_agent_context`` is the only place that touches the database; the result is plain data so
graphs run in worker threads without a session. Nothing here reads ``scenario_secret`` except the
pack's leak terms, which are used by the leak guard and never sent to a model.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from financequest.agents.campaign.guards import build_allowlist
from financequest.campaign import clock, rules
from financequest.campaign.events import campaign_events
from financequest.campaign.pack import Pack
from financequest.campaign.view import gated_content, gated_view
from financequest.db.models_campaign import CampaignRun, ClueState, Hero, Location
from financequest.engine.gate import GatedView

CHRONICLER = "chronicler"
DM_NAME = "Campaign Master"
BUDDY_NAME = "CommerzBuddy"
MAX_GENERATED = 3  # places the Campaign Master may add to one campaign
DM_TURNS = 8
BUDDY_TURNS = 6


@dataclass
class AgentContext:
    pack: Pack
    gv: GatedView
    phase: str
    turn_count: int
    focus_left: int
    rerolls_left: int
    keen_eye_left: int
    hp_start: int
    hp_lost: int
    news_shown: bool
    opening_done: bool
    can_decide: bool
    hero_name: str
    hero_class: str
    content: dict[str, Any]
    current: dict[str, Any] | None = None
    locations: list[dict[str, Any]] = field(default_factory=list)
    found: list[str] = field(default_factory=list)
    challenges: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    summary_at_turn: int = 0
    exchanges: list[tuple[str, str]] = field(default_factory=list)
    buddy_exchanges: list[tuple[str, str]] = field(default_factory=list)
    plan: str = ""
    screen: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    whatif: list[dict[str, Any]] | None = None
    forecast_pct: int | None = None
    player_texts: list[str] = field(default_factory=list)
    overlooked: list[str] = field(default_factory=list)
    question: str | None = None
    company_revealed: bool = False
    deadline: float | None = None
    campaign_id: str = ""
    # decisions throughout the campaign (euro figures only; engine computed)
    purse: dict[str, Any] | None = None  # cash_eur, position_eur, total_eur
    decisions: list[dict[str, Any]] = field(default_factory=list)
    scene: dict[str, Any] | None = None  # the open decision scene

    @property
    def holds_shares(self) -> bool:
        return bool(self.purse and self.purse.get("position_eur", 0) > 0)

    @property
    def budget(self) -> int:
        """The investable budget now: the starting purse minus the damage taken."""
        return (self.hp_start - self.hp_lost) * 10

    @property
    def npc_here(self) -> dict[str, Any] | None:
        """The NPC of the Master-created place the hero is in, else None."""
        here = self.current["key"] if self.current else None
        loc = next((x for x in self.locations if x["key"] == here), None)
        return loc["npc"] if loc and loc.get("generated") and loc.get("npc") else None

    @property
    def generated_count(self) -> int:
        return sum(1 for x in self.locations if x.get("generated"))

    @property
    def locked(self) -> bool:
        return self.outcome is not None

    def seconds_left(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - time.monotonic()

    def with_deadline(self, seconds: float) -> AgentContext:
        self.deadline = time.monotonic() + seconds
        return self

    def evidence_by_id(self, eid: str) -> dict[str, Any] | None:
        return next((e for e in self.content["evidence"] if e["id"] == eid), None)

    def location_name(self, key: str) -> str:
        return next((x["name"] for x in self.locations if x["key"] == key), key)

    def unfound(self) -> list[dict[str, Any]]:
        got = set(self.found)
        return [e for e in self.content["evidence"] if e["id"] not in got]

    def character(self, cid: str | None) -> dict[str, Any] | None:
        return next((c for c in self.content["characters"] if c["id"] == cid), None)


# ---- building -------------------------------------------------------------------------------------
def _exchanges(events: list[Any], limit: int) -> list[tuple[str, str]]:
    """(player input, reply) pairs for the Campaign Master from the event log."""
    out: list[tuple[str, str]] = []
    pending = ""
    for e in events:
        p = e.payload or {}
        if e.type == "action":
            pending = f"Player: {p.get('text', '')}"
        elif e.type == "move":
            pending = f"Player moved to the {p.get('name', '?')}."
        elif e.type == "dice_roll" and p.get("final"):
            pending = f"Dice check '{p.get('title', '')}': {p.get('result', '')}."
        elif e.type == "dm_reply" and p.get("text"):
            who = p.get("speaker") or DM_NAME
            out.append((pending, f"{who}: {p['text']}"))
            pending = ""
    return out[-limit:]


def _buddy_exchanges(events: list[Any], limit: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    q = ""
    for e in events:
        p = e.payload or {}
        if e.type == "buddy_q":
            q = str(p.get("text", ""))
        elif e.type == "buddy_a":
            out.append((q, str(p.get("text", ""))))
            q = ""
    return out[-limit:]


def screen_data(content: dict[str, Any], screen: str | None) -> dict[str, Any] | None:
    """What the player has open, as gated data (never client-supplied figures)."""
    if not screen:
        return None
    if screen in ("market_square", "price_board"):
        rows = content["chart"][-12:]
        return {"view": "Market Square price board", "rows": rows, "summary": chart_summary(content)}
    if screen == "library":
        return {
            "view": "Library",
            "documents": [{"id": d["id"], "title": d["title"]} for d in content["documents"]],
            "company_card": content["company_card"],
        }
    if screen.startswith("document:"):
        doc_id = screen.split(":", 1)[1]
        doc = next((d for d in content["documents"] if d["id"] == doc_id), None)
        if doc is None:
            return None
        by_id = {e["id"]: e for e in content["evidence"]}
        return {
            "view": f"Library document: {doc['title']}",
            "entries": [by_id[i] for i in doc["evidence_ids"] if i in by_id],
        }
    if screen == "commit":
        return {"view": "the commit screen", "company_card": content["company_card"]}
    return None


def chart_summary(content: dict[str, Any]) -> dict[str, Any] | None:
    """Engine-computed facts about the visible price board, so agents never calculate."""
    rows = content["chart"]
    if len(rows) < 2:
        return None
    closes = [Decimal(r["close"]) for r in rows]
    first, last = closes[0], closes[-1]
    change = ((last / first - 1) * 100).quantize(Decimal("0.1")) if first else Decimal(0)
    return {
        "first_day": rows[0]["day"], "last_day": rows[-1]["day"], "first_close": str(first),
        "last_close": str(last), "highest_close": str(max(closes)), "lowest_close": str(min(closes)),
        "change_pct": str(change),
    }  # fmt: skip


def outcome_facts(db: Session, run: CampaignRun) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, int | None, list[str]]:
    """Result facts for agents, only once a decision is locked (the lock response already shows
    them to the player): outcome numbers, what-if rows, the forecast and the player's own words."""
    from financequest.campaign import service
    from financequest.db.models_campaign import Debrief

    dec = service.decision_of(db, run.id)
    oc = service.db_outcome(db, run.id)
    if dec is None or oc is None:
        return None, None, None, []
    outcome = {
        "action": dec.action, "amount_eur": (dec.amount_cents or 0) // 100, "budget": (run.hp_start - run.hp_lost) * 10,
        "cash": oc.cash, "invested": oc.invested, "value_now": oc.value_now, "final": oc.final,
        "pnl": oc.pnl, "pnl_pct": oc.pnl_pct, "hp_before": oc.hp_before, "hp_after": oc.hp_after,
    }  # fmt: skip
    deb = db.get(Debrief, run.id)
    texts = [str(dec.evidence or "")] + ([deb.reflection_text] if deb and deb.reflection_text else [])
    return outcome, (deb.whatif if deb else None), int(dec.forecast_pct or 0), texts


def build_agent_context(
    db: Session,
    run: CampaignRun,
    pack: Pack,
    hero: Hero,
    *,
    screen: str | None = None,
    whatif: list[dict[str, Any]] | None = None,
    overlooked: list[str] | None = None,
    question: str | None = None,
) -> AgentContext:
    from financequest.campaign import service  # local: service imports narration

    outcome, stored_whatif, forecast_pct, player_texts = outcome_facts(db, run)
    can_decide = service.decide_ready(db, run, pack) if run.phase in ("play", "commit") else False
    gv = gated_view(run)
    content = gated_content(pack, gv)
    events = campaign_events(db, run.id)
    locs = list(db.exec(select(Location).where(Location.campaign_id == run.id)))
    cur = next((x for x in locs if x.id == run.current_location_id), None)
    chs = []
    for c in service.challenges(db, run.id):
        if not gv.at_checkpoint(c.checkpoint):
            continue
        chs.append({
            "id": str(c.id), "key": c.key, "title": c.title, "state": c.state, "result": c.result,
            "location": c.location_key, "optional": c.optional, "dc": c.dc,
            "alt_source": c.alt_source if c.result == "setback" else None,
        })  # fmt: skip
    found = [
        c.clue_id
        for c in db.exec(
            select(ClueState).where(ClueState.campaign_id == run.id).order_by(ClueState.found_at_seq)  # type: ignore[arg-type]
        )
    ]
    summary_ev = next((e for e in reversed(events) if e.type == "summary"), None)
    opening = next(
        (e for e in events if e.type == "dm_reply" and (e.payload or {}).get("opening")), None
    )
    return AgentContext(
        pack=pack, gv=gv, phase=run.phase, turn_count=run.turn_count, focus_left=run.focus_left,
        rerolls_left=run.rerolls_left, keen_eye_left=run.keen_eye_left, hp_start=run.hp_start,
        hp_lost=run.hp_lost, news_shown=run.news_shown, opening_done=run.opening_done, can_decide=can_decide,
        hero_name=hero.name, hero_class=hero.hero_class, content=content,
        current={"key": cur.key, "name": cur.name, "visited": cur.visited} if cur else None,
        locations=[
            {"id": str(x.id), "key": x.key, "name": x.name, "description": x.description,
             "visited": x.visited, "fixed": x.fixed, "generated": x.generated, "npc": x.npc}
            for x in locs
        ],
        found=found, challenges=chs,
        summary=(summary_ev.payload or {}).get("summary") if summary_ev else None,
        summary_at_turn=int((summary_ev.payload or {}).get("turn_count", 0)) if summary_ev else 0,
        exchanges=_exchanges(events, DM_TURNS),
        buddy_exchanges=_buddy_exchanges(events, BUDDY_TURNS),
        plan=str((opening.payload or {}).get("text", "")) if opening else "",
        screen=screen_data(content, screen), outcome=outcome, whatif=whatif or stored_whatif,
        forecast_pct=forecast_pct, player_texts=player_texts, overlooked=overlooked or [],
        question=question,
        company_revealed=any(e.type == "debrief_complete" for e in events),
        campaign_id=str(run.id),
        purse=service.purse(db, run, pack), decisions=service.decisions_out(db, run, pack),
        scene=run.market_scene if isinstance(run.market_scene, dict) else None,
    )  # fmt: skip


# ---- engine reachability -----------------------------------------------------------------------
def free_clues_at(ctx: AgentContext, loc_key: str) -> list[str]:
    """Unfound, ungated clues of this place at the current checkpoint (granted on arrival)."""
    gated = rules.gated_clue_ids(ctx.pack)
    got = set(ctx.found)
    return [
        e["id"]
        for e in ctx.content["evidence"]
        if e["location"] == loc_key and e["id"] not in gated and e["id"] not in got
    ]


def people_at(ctx: AgentContext, loc_key: str) -> list[dict[str, Any]]:
    """Who can be questioned at a place: the pack's characters and the NPC of a created place."""
    out = [c for c in ctx.content["characters"] if c["location"] == loc_key]
    loc = next((x for x in ctx.locations if x["key"] == loc_key), None)
    if loc and loc.get("generated") and loc.get("npc"):
        out.append({"id": loc["npc"]["id"], "name": loc["npc"]["name"], "role": loc["npc"]["role"]})
    return out


def characters_here(ctx: AgentContext) -> list[dict[str, Any]]:
    here = ctx.current["key"] if ctx.current else None
    return [c for c in ctx.content["characters"] if c["location"] == here]


def reachable_clue_ids(ctx: AgentContext, speaker: str | None) -> set[str]:
    """The only clue ids the engine will accept from the Campaign Master this turn: what a
    character who is here may reveal at this checkpoint, or the free clues of this place."""
    here = ctx.current["key"] if ctx.current else ""
    if speaker and speaker != CHRONICLER:
        ch = ctx.character(speaker)
        if ch is not None and ch["location"] == here:
            return set(ch["may_reveal"])
        return set()
    at_here = {e["id"] for e in ctx.content["evidence"] if e["location"] == here}
    return set(free_clues_at(ctx, here)) | (set(ctx.found) & at_here)


def npc_may_reveal(ctx: AgentContext) -> list[str]:
    """What a Master-created NPC may reveal: free evidence already unlocked at the current
    checkpoint (the gated content holds nothing later), minus what a dice check guards."""
    gated = rules.gated_clue_ids(ctx.pack)
    return [e["id"] for e in ctx.content["evidence"] if e["id"] not in gated]


def speaker_name(ctx: AgentContext, speaker: str | None) -> str:
    npc = ctx.npc_here
    if npc and speaker == npc["id"]:
        return str(npc["name"])
    ch = ctx.character(speaker) if speaker and speaker != CHRONICLER else None
    return ch["name"] if ch else DM_NAME


# ---- allowlist -----------------------------------------------------------------------------------
def figure_texts(ctx: AgentContext) -> list[str]:
    """Every string whose numbers the player may legitimately see before the lock."""
    out: list[str] = []
    for e in ctx.content["evidence"]:
        out += [e["title"], e["text"]]
    for f in ctx.content["company_card"]["key_figures"]:
        out += [str(f.get("value", "")), str(f.get("label", "")), str(f.get("explain", ""))]
    out += [ctx.content["company_card"].get("size", "")]
    for r in ctx.content["chart"]:
        out += [str(r["day"]), r["open"], r["high"], r["low"], r["close"]]
    if ctx.content["news"]:
        out += [ctx.content["news"]["headline"], ctx.content["news"]["summary"]]
    summ = chart_summary(ctx.content)
    if summ:
        out += [str(v) for v in summ.values()]
    return out


def free_numbers(ctx: AgentContext, typed: str = "") -> list[Any]:
    p = ctx.pack
    nums: list[Any] = [
        2, 20, ctx.hp_start, ctx.budget, ctx.hp_start * 10, ctx.hp_start - ctx.hp_lost, ctx.turn_count, ctx.turn_count + 1, ctx.focus_left,
        ctx.rerolls_left, ctx.keen_eye_left, ctx.gv.clock_day, p.horizon_days, *rules.DC_TABLE.values(),
        rules.BONUS_DC, rules.NEWS_TURNS, rules.NEWS_MARKET_TURNS, 70, 100, 150,
    ]  # fmt: skip
    nums += [c["dc"] for c in ctx.challenges]
    if ctx.news_shown and p.news:
        nums.append(int(p.news.get("time_skip_days", 0)))
        nums.append(max(1, ctx.gv.clock_day - p.intro.story_day))  # the shown skip, from the clock
    nums += [cp.story_day for cp in p.checkpoints if ctx.gv.at_checkpoint(cp.id)]
    for text in [typed, *ctx.player_texts, *(d["text"] for d in ctx.decisions)]:
        nums += re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if ctx.purse:  # the purse card shows these figures to the player
        nums += [ctx.purse["cash_eur"], ctx.purse["position_eur"], ctx.purse["total_eur"]]
    for d in ctx.decisions:
        nums += [d["amount_eur"], d["cash_after_eur"]]
        if d.get("effect_eur") is not None:  # only after the lock
            nums.append(d["effect_eur"])
    if ctx.outcome:  # after the lock the outcome and what-if figures are public
        o = ctx.outcome
        nums += [v for v in o.values() if isinstance(v, int | float | Decimal | str)]
        for row in ctx.whatif or []:
            nums += [row.get("final"), row.get("pnl_pct"), row.get("hp_after")]
        if ctx.forecast_pct is not None:
            nums += [ctx.forecast_pct, 100 - ctx.forecast_pct]
    return nums


def allowlist(ctx: AgentContext, typed: str = "") -> set[str]:
    figs = figure_texts(ctx)
    if ctx.outcome:  # numeric-looking strings in the outcome payload
        figs += [str(v) for v in ctx.outcome.values()]
    return build_allowlist(figs, free_numbers(ctx, typed))


# ---- prompt blocks -------------------------------------------------------------------------------
def stable_prefix(ctx: AgentContext) -> str:
    """World, gated reference data and the campaign plan. Cache breakpoint 1: it only changes when
    the checkpoint changes (the news) or the plan is written."""
    p, c = ctx.pack, ctx.content
    lines = [
        "# Reference data for this campaign (the only facts you may state)",
        f"Campaign: {p.title}. Setting: {p.setting}. Company: {p.company_name} ({p.trade}).",
        f"Market: {p.market_name}. Budget: {ctx.budget} euros. Horizon: {clock.horizon_sentence(p)}.",
        f"Checkpoint {c['checkpoint']}, story day {c['story_day']}.",
        "", "## Evidence visible now (id | location | title | text)",
    ]
    for e in c["evidence"]:
        lines.append(f"{e['id']} | {e['location']} | {e['title']} | {e['text']}")
    lines += ["", "## Library documents"]
    lines += [f"{d['id']}: {d['title']} ({', '.join(d['evidence_ids'])})" for d in c["documents"]]
    lines += ["", "## Company card"]
    card = c["company_card"]
    lines.append(f"{card['name']}: {card['trade']}. {card.get('size', '')}")
    lines += [f"- {f['label']}: {f['value']} ({f.get('period', '')})" for f in card["key_figures"]]
    lines += ["", "## Characters (id | name | role | location | may reveal now)"]
    for ch in c["characters"]:
        lines.append(
            f"{ch['id']} | {ch['name']} | {ch['role']} | {ch['location']} | "
            f"{', '.join(ch['may_reveal'])} | never: {'; '.join(ch['never'])}"
        )
    lines += ["", "## Price board (story day: open/high/low/close)"]
    lines += [f"{r['day']}: {r['open']}/{r['high']}/{r['low']}/{r['close']}" for r in c["chart"]]
    summ = chart_summary(c)
    if summ:
        lines.append(f"Board summary (engine computed): {summ}")
    if c["news"]:
        lines += ["", f"## Breaking news (shown): {c['news']['headline']}. {c['news']['summary']}"]
    lines += ["", "## Encounters"]
    lines += [f"{e['id']} | {e['location']} | {e['title']}" for e in c["encounters"]]
    if ctx.plan:
        lines += ["", "## Campaign plan (the Tavern briefing already given)", ctx.plan]
    return "\n".join(lines)


def facts_block(ctx: AgentContext) -> str:
    """Facts injected from the event log on every call."""
    cur = ctx.current["name"] if ctx.current else "nowhere"
    found = [f"{i} ({(ctx.evidence_by_id(i) or {}).get('title', 'bonus lead')})" for i in ctx.found]
    visited = [x["name"] for x in ctx.locations if x["visited"]]
    unvisited = [f"{x['key']} ({x['name']})" for x in ctx.locations if not x["visited"]]
    gated = rules.gated_clue_ids(ctx.pack)
    unfound = [
        f"{e['id']}@{e['location']}{' (dice-gated)' if e['id'] in gated else ''}"
        for e in ctx.unfound()
    ]
    chs = [
        f"{c['key']}: {c['title']} at {c['location']} [{c['state']}"
        f"{', ' + c['result'] if c['result'] else ''}]"
        for c in ctx.challenges
    ]
    return "\n".join([
        "# Facts from the event log",
        f"Hero: a {ctx.hero_class}, always addressed as 'you' (never by name). Phase: {ctx.phase}. Story day {ctx.gv.clock_day}.",
        f"Turns taken: {ctx.turn_count}. Focus left: {ctx.focus_left}. News shown: {ctx.news_shown}.",
        f"Current location: {cur}. Visited: {', '.join(visited) or 'none'}.",
        f"Not yet visited: {', '.join(unvisited) or 'none'}.",
        f"Clues found: {'; '.join(found) or 'none'}.",
        f"Clues not found yet (never quote their text): {'; '.join(unfound) or 'none'}.",
        f"Challenges: {'; '.join(chs) or 'none'}.",
        f"Player may decide now: {ctx.can_decide}.",
        f"HP (the budget bar, 1 HP is 10 euros): {ctx.hp_start - ctx.hp_lost} of {ctx.hp_start}; "
        f"lost so far: {ctx.hp_lost}.",
        f"Places the Master created so far: {ctx.generated_count} of {MAX_GENERATED}.",
        *purse_lines(ctx),
    ])  # fmt: skip


def purse_lines(ctx: AgentContext) -> list[str]:
    """The hero's coins and the decisions so far, so the world can react to their position."""
    if ctx.purse is None:
        return []
    p = ctx.purse
    lines = [
        f"Purse (engine computed, euros): cash {p['cash_eur']}, coins in the company worth "
        f"{p['position_eur']}, total {p['total_eur']}."
    ]
    for d in ctx.decisions:
        lines.append(
            f"Decision on {d['day_label']} ({d['beat']}): {d['action']} {d['amount_eur']} euros. "
            f"In their words: \"{d['text']}\""
        )
    if not ctx.decisions:
        lines.append("Investment decisions so far: none.")
    if ctx.scene:
        lines.append(f"A decision scene is open ({ctx.scene.get('beat')}): the hero owes an answer.")
    return lines


def history_block(ctx: AgentContext, buddy: bool = False) -> str:
    parts: list[str] = []
    if ctx.summary and not buddy:
        parts.append(f"# Summary of earlier turns\n{ctx.summary}")
    pairs = ctx.buddy_exchanges if buddy else ctx.exchanges
    if pairs:
        parts.append("# Recent exchanges")
        for q, a in pairs:
            parts.append(f"{q}\n{a}".strip())
    return "\n".join(parts)


def build_messages(
    ctx: AgentContext,
    role_prompt: str,
    user_text: str,
    *,
    buddy: bool = False,
    corrective: list[str] | None = None,
    extra: str = "",
) -> list[Any]:
    """System: [stable prefix (cache breakpoint 1), role prompt (cache breakpoint 2)]. Human:
    facts + history + input. Plain dict blocks so the SDK forwards ``cache_control``."""
    from langchain_core.messages import HumanMessage, SystemMessage

    system = SystemMessage(content=[
        {"type": "text", "text": stable_prefix(ctx), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": role_prompt, "cache_control": {"type": "ephemeral"}},
    ])  # fmt: skip
    body = [facts_block(ctx)]
    if ctx.screen:
        body.append(f"# What the player has open right now (gated data)\n{ctx.screen}")
    if ctx.outcome:
        body.append(f"# Result (after the lock; engine computed)\n{ctx.outcome}")
    if hist := history_block(ctx, buddy):
        body.append(hist)
    if extra:
        body.append(extra)
    body.append(f"# Player input\n{user_text}")
    if corrective:
        body.append(
            "# Your previous answer was rejected. Fix these problems and answer again\n"
            + "\n".join(f"- {v}" for v in corrective)
        )
    return [system, HumanMessage(content="\n\n".join(body))]


def new_client_id() -> str:
    return uuid.uuid4().hex


__all__ = ["AgentContext", "build_agent_context", "allowlist", "build_messages", "GatedView"]
