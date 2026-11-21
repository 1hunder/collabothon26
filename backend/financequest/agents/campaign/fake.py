"""FAKE_LLM=1: a scripted Campaign Master and CommerzBuddy.

Deterministic, derived only from the gated ``AgentContext`` (so it never knows more than a real
model would), flavoured for the Golden Guild case, and written to pass the guards. The whole
campaign is playable without keys. Used by the demo and by e2e tests.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from financequest.agents.campaign import context as C
from financequest.agents.campaign import schemas as S
from financequest.agents.campaign.graphs import prepared_setup, the
from financequest.agents.campaign.guards import whole
from financequest.campaign import reasoning as reasoning_mod
from financequest.campaign import rules
from financequest.llm import LLMResult


def first_sentences(text: str, n: int = 1, max_words: int = 32) -> str:
    """The first ``n`` sentences. A sentence that is too long is cut at the last clause boundary
    (comma, semicolon or colon) that fits, never mid-clause, so no figure is left dangling."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = " ".join(parts[:n])
    words = out.split()
    if len(words) <= max_words:
        return out
    head = " ".join(words[:max_words])
    cut = max(head.rfind(","), head.rfind(";"), head.rfind(":"))
    if cut > len(head) // 3:
        head = head[:cut]
    return head.rstrip(",;: ") + "."


def _names(ctx: C.AgentContext, ids: list[str]) -> str:
    return "; ".join((ctx.evidence_by_id(i) or {}).get("title", i) for i in ids)


def _has(text: str, *words: str) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{re.escape(w)}", low) for w in words)


_GENERIC_ROLE = {"guild", "golden", "company"}

# ---- scripted damage (tests): FAKE_LLM defaults to none --------------------------------------
DAMAGE_SCRIPT: list[tuple[int, str]] = []


def script_damage(loss: int, reason: str = "a costly slip") -> None:
    """Queue one HP loss for the next turn or setback narration that may carry damage."""
    DAMAGE_SCRIPT.append((loss, reason))


def clear_damage() -> None:
    DAMAGE_SCRIPT.clear()


def _take_damage() -> tuple[int, str]:
    return DAMAGE_SCRIPT.pop(0) if DAMAGE_SCRIPT else (0, "")


def _with_damage(body: str, loss: int, reason: str) -> str:
    return f"{body} You lose {loss} HP: {reason}." if loss > 0 else body


# ---- scripted offers of the all-in plot: FAKE_LLM defaults to a buyback ---------------------------
OFFER_SCRIPT: list[str] = []
_BROKERS = ("Harrel Voss", "Ysolde Marsh", "Cato Brindle")
_LENDERS = ("Ismene Dray", "Orlan Pike", "Veda Quillon")


def script_offer(kind: str) -> None:
    """Queue the kind (buyback / loan / fast_forward) of the next offer the Master makes."""
    OFFER_SCRIPT.append(kind)


def clear_offers() -> None:
    OFFER_SCRIPT.clear()


# ---- movement phrasing and place synonyms ----------------------------------------------------
_MOVE_PHRASES = (
    "go to", "go back", "visit", "head to", "head for", "head back", "walk to", "travel", "enter",
    "back to", "return to", "let's go", "lets go", "off to", "take me to", "stop by", "drop by",
    "make my way", "go see", "go over to", "run to", "hurry to", "ride to", "sail to", "check out",
)
# ---- ad-hoc skill checks: phrase -> skill (the scripted router; a real model judges by meaning) --
_SKILL_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("insight", (r"\binsights?\b", r"\bis (he|she|they|[a-z]+( [a-z]+)?) (lying|honest|hiding)",
                 r"\b(lying|lies|bluffing)\b", r"\bstudy (his|her|their) (face|eyes)",
                 r"\bread (whether|if|him|her|them|his|her|their)\b", r"\bread (the )?(motive|intent)")),
    ("persuasion", (r"\bpersuade\b", r"\bconvince\b", r"\bpress (him|her|them)\b")),
    ("stealth", (r"\bsneak", r"\beavesdrop", r"\boverhear", r"\bslip past\b")),
    ("investigation", (r"\bsearch", r"\blook(ing)? for (any )?(clues?|signs?|something|hidden)",
                       r"\binspect\b", r"\brummage", r"\bscour\b", r"\blook closely\b")),
    ("knowledge", (r"\brecall\b", r"\bwhat do i (know|remember) about\b")),
)
_SKILL_DIFFICULTY = {"investigation": "easy", "persuasion": "hard"}
_LEAD_IN = {
    "investigation": "You crouch to study the scuffed floorboards and the corners others overlook.",
    "insight": "You hold {t}'s gaze a moment longer than is polite, weighing every pause.",
    "persuasion": "You lean in and press the point, choosing each word with care.",
    "stealth": "You slow your breathing and drift closer, keeping to the shadows.",
    "knowledge": "You turn over in your mind everything you once learned of such matters.",
}
_REPEAT = {
    "investigation": "You have already gone over this place carefully, and there is nothing more to find.",
    "insight": "You have already read {t} as well as you can, and they give nothing more away.",
    "persuasion": "You have already pressed {t} as far as it will go for now.",
    "stealth": "You have already tried that here, and trying again would only draw eyes.",
    "knowledge": "You have already searched your memory on that, and nothing more comes.",
}


def skill_of(low: str) -> str | None:
    return next((sk for sk, pats in _SKILL_PHRASES if any(re.search(p, low) for p in pats)), None)


def _check_target(ctx: C.AgentContext, low: str, skill: str) -> str:
    for ch in ctx.content["characters"]:
        parts = [ch["name"].lower(), *(w for w in ch["name"].lower().split() if len(w) > 3)]
        if any(p in low for p in parts):
            return str(ch["name"])
    if skill in ("insight", "persuasion"):
        return "the person before you"
    return {"stealth": "the talk nearby", "knowledge": "the matter at hand"}.get(
        skill, f"the {ctx.current['name'].lower()}" if ctx.current else "the room")


_EXAMINE = ("examine", "read", "investigate", "inspect", "study", "cross-check", "scrutinize")
_SYNONYMS = {
    "market_square": ("market", "square", "price board", "trading floor", "exchange"),
    "library": ("library", "archive", "archives", "records", "ledger room"),
    "tavern": ("tavern", "inn", "pub", "common room", "where we started"),
    "golden_guild_hall": ("guild hall", "council chamber", "hall"),
}
_PLACE_ROLE = {
    "warehouse": "Warehouse keeper", "docks": "Dockmaster", "dock": "Dockmaster",
    "harbour": "Harbourmaster", "harbor": "Harbourmaster", "port": "Port clerk",
    "ship": "Ship's purser", "vessel": "Ship's purser", "office": "Chief clerk",
    "chamber": "Chamber usher", "bank": "Banker", "factory": "Foreman", "mill": "Miller",
    "workshop": "Master craftsman", "shipyard": "Shipwright", "depot": "Depot clerk",
    "regulator": "Regulator's clerk", "auditor": "Auditor", "counterparty": "Counterparty's agent",
    "counting": "Counting-house clerk", "vault": "Vault keeper", "customs": "Customs officer",
    "court": "Court clerk", "shop": "Shopkeeper", "tower": "Tower warden", "market": "Stall keeper",
}
_NPC_NAMES = ("Brann Ostrel", "Mirela Vance", "Tolek Harrowind", "Sivra Dunmere", "Edda Fenwick")
_STOP = {"the", "a", "an", "to", "at", "of", "my", "our", "their", "that", "this", "old", "big"}


def listed_place(ctx: C.AgentContext, low: str) -> str | None:
    """The key of a listed place the (lowercased) text names: by name word, key or synonym."""
    words = set(re.findall(r"[a-z']+", low))
    for loc in ctx.locations:
        name_words = {w for w in re.findall(r"[a-z]+", loc["name"].lower()) if len(w) > 3}
        if name_words & words or loc["key"].replace("_", " ") in low:
            return str(loc["key"])
    have = {x["key"] for x in ctx.locations}
    for key, syns in _SYNONYMS.items():
        if key in have and any(re.search(rf"\b{re.escape(w)}\b", low) for w in syns):
            return key
    return None


def names_travel(ctx: C.AgentContext, text: str) -> bool:
    """Deterministic: the text uses a travel phrase and names a place the hero can go to."""
    low = text.lower()
    return _has(low, *_MOVE_PHRASES) and listed_place(ctx, low) is not None


def _place_spec(text: str) -> dict[str, Any] | None:
    words = re.findall(r"[A-Za-z']+", text)
    for i, w in enumerate(words):
        noun = w.lower()
        if noun not in _PLACE_ROLE:
            continue
        pre = words[i - 1] if i and words[i - 1].lower() not in _STOP and not words[i - 1].endswith("'s") else ""
        name = " ".join(x.capitalize() for x in (pre, w) if x)
        name = name if name.lower().endswith("s") or True else name
        idx = sum(ord(c) for c in name) % len(_NPC_NAMES)
        return {
            "name": name,
            "description": f"A busy {noun} in the trade quarter, damp with river air and full of the guild's cargo.",
            "art_subject": f"The interior of a weathered {noun}, stacked crates, rope and barrels in warm lantern light, empty of people",
            "npc": {"name": _NPC_NAMES[idx], "role": _PLACE_ROLE[noun],
                    "persona": "Curt and practical, speaks plainly and distrusts idle questions."},
        }
    return None


class CampaignFakeLLM:
    """Implements ``NodeLLM.run`` for the ``campaign_*`` nodes."""

    def run(
        self,
        node: str,
        messages: Sequence[Any],
        *,
        schema: type[BaseModel],
        effort: str,
        persona: str | None = None,
        web_search_max_uses: int | None = None,
        context: dict[str, Any] | None = None,
        fallback: bool = False,
    ) -> LLMResult:
        handler = getattr(self, node.removeprefix("campaign_"), None)
        if handler is None:
            raise KeyError(f"no scripted behaviour for node {node!r}")
        parsed = handler(context or {})
        return LLMResult(
            parsed=parsed, content=[{"type": "text", "text": parsed.model_dump_json()}],
            usage={"input_tokens": 1, "output_tokens": 1},
        )  # fmt: skip

    # ---- router ---------------------------------------------------------------------------------
    def route(self, c: dict[str, Any]) -> S.RouteOut:
        ctx: C.AgentContext = c["ctx"]
        text: str = c["input"]
        low = text.lower()
        words = set(re.findall(r"[a-z']+", low))
        if _has(low, *_MOVE_PHRASES) and not _has(low, *_EXAMINE) and not _has(low, "ask ", "talk to"):
            mv = self._move_target(ctx, low, words)
            if mv is not None:
                return mv
        for ch in ctx.challenges:
            if ch["skill"]:  # an earlier ad-hoc check is never a predefined encounter
                continue
            title_words = {w for w in re.findall(r"[a-z]+", ch["title"].lower()) if len(w) > 3}
            if title_words & words or ch["key"].lower() in low:
                return S.RouteOut(intent="challenge", challenge_key=ch["key"])
        here = ctx.current["key"] if ctx.current else ""
        sk = skill_of(low)
        if sk is not None:
            return S.RouteOut(intent="challenge", check=S.CheckSpec(
                skill=sk, target=_check_target(ctx, low, sk),  # type: ignore[arg-type]
                difficulty=_SKILL_DIFFICULTY.get(sk, "medium"),  # type: ignore[arg-type]
                stakes="something the place or person keeps back",
            ))  # fmt: skip
        named = [
            (len(names & words), char["location"] == here, char)
            for char in ctx.content["characters"]
            if (names := {w for w in re.findall(r"[a-z']+", char["name"].lower()) if len(w) > 2}) & words
        ]
        if named:  # a name beats any role word: "Ask Ren Tal about the guild" is Ren Tal
            named.sort(key=lambda t: (t[0], t[1]), reverse=True)
            return S.RouteOut(intent="talk", character_id=named[0][2]["id"])
        if _has(low, "ask", "talk", "speak", "question"):
            for char in ctx.content["characters"]:
                role = {w for w in re.findall(r"[a-z]+", char["role"].lower().split(";")[0]) if len(w) > 4}
                if role & words and not _GENERIC_ROLE & role & words:
                    return S.RouteOut(intent="talk", character_id=char["id"])
        if _has(low, *_MOVE_PHRASES):
            mv = self._move_target(ctx, low, words)
            if mv is not None:
                return mv
        if _has(low, "joke", "weather", "pizza", "football", "recipe", "movie", "song", "poem", "cats"):
            return S.RouteOut(intent="off_topic")
        return S.RouteOut(intent="free")

    def _move_target(self, ctx: C.AgentContext, low: str, words: set[str]) -> S.RouteOut | None:
        """A listed place by its name, its key or a synonym; else a new place the story needs."""
        key = listed_place(ctx, low)
        if key is not None:
            return S.RouteOut(intent="move", location_key=key)
        spec = _place_spec(low)
        if spec is not None:
            return S.RouteOut(intent="new_location", new_location=S.NewLocationSpec(**spec))
        return None

    # ---- Campaign Master turn -----------------------------------------------------------------------
    def turn(self, c: dict[str, Any]) -> S.TurnOut:
        ctx: C.AgentContext = c["ctx"]
        r: S.RouteOut = c["route"]
        text: str = c["input"]
        _, allowed = _turn_allowed(ctx, r)
        given: list[str] = []
        speaker = C.CHRONICLER
        body: str
        loss, why = 0, ""
        if r.intent == "new_location" and r.new_location is not None:
            n = r.new_location
            body = (f"You step into {n.name}. {n.description} {n.npc.name}, {n.npc.role}, "
                    "looks up from their work.")
        elif r.intent == "move" and r.location_key:
            body, given = self._arrival(ctx, r.location_key, sorted(allowed))
        elif r.intent == "talk":
            body, given, speaker = self._talk(ctx, r, allowed)
        elif r.check is not None and r.intent in ("challenge", "free"):
            tpl = (_LEAD_IN if r.intent == "challenge" else _REPEAT)[r.check.skill]
            body = tpl.format(t=r.check.target)
        elif r.intent == "challenge":
            body = self._challenge(ctx, r)
        elif r.intent == "off_topic":
            body = (
                "A fine jest, traveller, and the rain applauds. But the mystery will not solve "
                "itself, and the ledgers are waiting."
            )
        else:
            body = self._free(ctx, text)
        if r.intent not in ("off_topic", "decision_intent"):
            loss, why = _take_damage()
            body = _with_damage(body, loss, why)
        remaining = _remaining_need(ctx, set(given))
        nothing_more = ctx.news_shown and not remaining and r.intent != "new_location"
        if nothing_more:
            body += " There is nothing more to uncover for now. Ready to make your decision?"
            sugg = ["Review what you found", "Ask CommerzBuddy for a recap", "Look around once more"]
        else:
            body += " What would you do?"
            sugg = _suggestions(ctx, given, r.location_key if r.intent == "move" else None)
        if r.intent == "new_location" and r.new_location is not None:
            sugg = [f"Ask {r.new_location.npc.name} what they know", *sugg][:3]
        return S.TurnOut(text=body, speaker=speaker, suggestions=sugg, clue_ids_given=given,
                         nothing_more_to_uncover=nothing_more and r.intent != "new_location",
                         hp_loss=loss, hp_reason=why if loss else "")  # fmt: skip

    def _arrival(self, ctx: C.AgentContext, key: str, free: list[str]) -> tuple[str, list[str]]:
        loc = next(x for x in ctx.locations if x["key"] == key)
        here = [ch["name"] for ch in C.people_at(ctx, key)]
        parts = [
            f"You are back at {the(loc['name'])}."
            if loc["visited"]
            else f"You step into {the(loc['name'])}. {loc['description']}"
        ]
        if free:
            parts.append(f"Here you learn of: {_names(ctx, free)}.")
            for i in free[:2]:
                ev = ctx.evidence_by_id(i)
                if ev:
                    parts.append(first_sentences(ev["text"], 1, 60))
        elif loc["visited"]:
            parts.append("Nothing new catches your eye.")
        if here:
            parts.append(f"{' and '.join(here)} can be questioned here.")
        return " ".join(parts), free

    def _talk(
        self, ctx: C.AgentContext, r: S.RouteOut, allowed: set[str]
    ) -> tuple[str, list[str], str]:
        ch = ctx.character(r.character_id)
        assert ch is not None
        here = ctx.current["key"] if ctx.current else ""
        if ch["location"] != here:
            return (
                f"{ch['name']} is not here. You would find them at "
                f"{the(ctx.location_name(ch['location']))}.",
                [],
                C.CHRONICLER,
            )
        fresh = [i for i in ch["may_reveal"] if i not in ctx.found and i in allowed][:2]
        if not fresh:
            return (f"{ch['name']} spreads their hands. “I have told you all I may.”", [], ch["id"])
        lines = [f"{ch['name']} leans closer."]
        for i in fresh:
            ev = ctx.evidence_by_id(i)
            if ev:
                lines.append(f"“{first_sentences(ev['text'], 1, 30)}”")
        return " ".join(lines), fresh, ch["id"]

    def _challenge(self, ctx: C.AgentContext, r: S.RouteOut) -> str:
        ch = next(x for x in ctx.challenges if x["key"] == r.challenge_key)
        if ch["state"] != "open":
            return (
                f"You have already tried “{ch['title']}”. "
                f"{ch['alt_source'] or 'The answer must come from another source.'}"
            )
        return (
            f"You settle in to examine “{ch['title']}”. The lines blur, then sharpen; a steady eye "
            "and a little luck will decide how deep you see. Steady yourself."
        )

    def _free(self, ctx: C.AgentContext, text: str) -> str:
        if _has(text, "learn", "found", "clue", "remember", "so far"):
            if ctx.found:
                return f"So far you have gathered: {_names(ctx, ctx.found)}."
            return "You have gathered nothing yet, but every ledger holds a thread."
        if _has(text, "price", "chart", "board", "graph"):
            return (
                f"The price board hangs in the {ctx.pack.market_name}. Open it to see how the "
                f"price moved up to day {ctx.gv.clock_day}."
            )
        if _has(text, "mean", "what is", "define", "explain"):
            return "A fair question. CommerzBuddy explains such words better than any proclamation."
        loc = ctx.current
        if loc:
            desc = next((x["description"] for x in ctx.locations if x["key"] == loc["key"]), "")
            return f"You take in the {loc['name']} once more. {desc}"
        return "You look around. The rain keeps its own counsel."

    # ---- the NPC of a Master-created place ---------------------------------------------------------
    def npc(self, c: dict[str, Any]) -> S.NpcOut:
        ctx: C.AgentContext = c["ctx"]
        text: str = c["input"]
        npc = c["npc"]
        low = text.lower()
        here = ctx.current["key"] if ctx.current else ""
        other_names = {
            w for x in ctx.locations if x["key"] != here
            for w in re.findall(r"[a-z]+", x["name"].lower()) if len(w) > 3
        } - {"the", "steps", "guild", "golden", "grand"}
        chal = {w for ch in ctx.challenges if not ch["skill"]
                for w in re.findall(r"[a-z]+", ch["title"].lower()) if len(w) > 4}
        cast = {w for ch in ctx.content["characters"] for w in re.findall(r"[a-z']+", ch["name"].lower()) if len(w) > 2}
        words = set(re.findall(r"[a-z']+", low))
        reason = None
        if _has(low, *_MOVE_PHRASES) or _has(low, "leave", "go home"):
            reason = "the hero wants to travel"
        elif _has(low, "decide", "invest", "commit", "my coins", "ready to", "buy", "sell"):
            reason = "the hero wants to decide"
        elif skill_of(low) is not None:
            reason = "an uncertain skilled attempt that needs the Master"
        elif _has(low, "sneak", "steal", "break in", "pick the lock", "bribe", "threaten", "risk", "dare", "attack"):
            reason = "a risky action that needs the Master"
        elif _has(low, "joke", "weather", "pizza", "football", "recipe", "movie"):
            reason = "off-topic"
        elif (other_names | chal | cast) & words:
            reason = "asks about another place or person"
        if reason:
            return S.NpcOut(text=f"{npc['name']} lifts a hand. “That is beyond me.”",
                            escalate=True, escalate_reason=reason)
        fresh = [i for i in C.npc_may_reveal(ctx) if i not in ctx.found][:1]
        asks = _has(low, "know", "tell", "what", "anything", "rumour", "rumor", "clue", "evidence",
                    "learn", "seen", "heard", "ask")
        line = f"{npc['name']} wipes their hands and studies you. "
        given: list[str] = []
        if fresh and asks:
            ev = ctx.evidence_by_id(fresh[0])
            if ev:
                line += f"“{first_sentences(ev['text'], 1, 30)}”"
                given = fresh
        else:
            line += "“Speak plainly, and I will answer as plainly as I can.”"
        loss, why = _take_damage()
        return S.NpcOut(
            text=_with_damage(line, loss, why) + " What do you ask next?",
            hp_loss=loss, hp_reason=why if loss else "",
            suggestions=["Ask what else they have seen", "Ask about the cargo", "Thank them and think"],
            clue_ids_given=given,
        )

    # ---- dice, news, hint, summary ---------------------------------------------------------------------
    def dice(self, c: dict[str, Any]) -> S.DiceOut:
        roll = c["roll"]
        clue = roll.get("clue")
        if roll.get("skill"):
            if roll["result"] == "success":
                body = "Your patience pays off."
                body += (f" You learn: {clue['title']}. {first_sentences(clue['text'], 2, 40)}" if clue
                         else " You notice a worn path in the dust and a half-hidden mark by the door.")
                if roll.get("used") == 20:
                    body += " A lucky glance shows you one more small thing."
            else:
                body = ("It goes badly: you misjudge it, draw a suspicious look and lose a "
                        "moment you could not spare.")
        elif roll["result"] == "success":
            body = "Fortune favours you, and the page gives up its secret."
            if clue:
                body += f" You find: {clue['title']}. {first_sentences(clue['text'], 2, 40)}"
        else:
            body = (
                "The lines swim and a page sticks to the next. A setback, but no dead end. "
                f"{roll.get('alt_source') or 'Ask around and read the documents.'}"
            )
        loss, why = _take_damage()
        return S.DiceOut(text=_with_damage(body, loss, why) + " What would you do next?",
                         hp_loss=loss, hp_reason=why if loss else "")

    def news(self, c: dict[str, Any]) -> S.TextOut:
        ctx: C.AgentContext = c["ctx"]
        return S.TextOut(
            text=f"A hush falls over the {ctx.pack.market_name} as the proclamation is read aloud. "
            "How does this news change your view of the company?"
        )

    # ---- decisions throughout the campaign ------------------------------------------------------
    _SCENES = {
        "opening": "A guild broker in a gilded coat stops you at the {market}: shares of "
                   "{company} are on offer today, for anyone who trusts what little they know. "
                   "Do you put coins in now, or keep them while you look around?",
        "news": "The {market} is loud with the proclamation, and traders crowd the brokers' "
                "stalls to change their bets. Your purse waits on your word. What do you do "
                "with your coins now?",
        "decision": "The bell for the last trading of the season rings over the {market}. "
                    "Whatever you choose now, you will live with until the horizon. What do you "
                    "do with your coins?",
        "story": "A broker from {company} catches your eye across the {market}, waiting for an "
                 "answer about your coins. What do you do with them now?",
    }  # fmt: skip

    def scene(self, c: dict[str, Any]) -> S.TextOut:
        ctx: C.AgentContext = c["ctx"]
        beat = str(c.get("beat") or "story")
        text = self._SCENES.get(beat, self._SCENES["story"])
        return S.TextOut(text=text.format(market=ctx.pack.market_name, company=ctx.pack.company_name))

    def offer(self, c: dict[str, Any]) -> S.OfferOut:
        ctx: C.AgentContext = c["ctx"]
        allowed: list[str] = c["allowed"]
        want = OFFER_SCRIPT.pop(0) if OFFER_SCRIPT else "buyback"
        kind = want if want in allowed else allowed[0]
        facts = ctx.offer_facts or {}
        pick = int(ctx.campaign_id.replace("-", "")[:8] or "0", 16)
        if kind == "buyback":
            return S.OfferOut(
                kind="buyback", name=_BROKERS[pick % len(_BROKERS)], role="Guild broker",
                text="A broker in a gilded coat draws you aside: for anyone who wants coins back in "
                     "hand, he will buy part of your stake in the company at today's board price, up "
                     f"to {whole(facts['buyback']['max_eur'])} gold pieces worth. How do you answer?",
                suggestions=["Sell half of my coins", "No, I keep them all", "I look around instead"],
            )  # fmt: skip
        if kind == "loan":
            t = facts["loan"]
            return S.OfferOut(
                kind="loan", name=_LENDERS[pick % len(_LENDERS)], role="Moneylender",
                text=f"A moneylender of the guild offers you up to {whole(t['principal_eur'])} gold pieces now, at "
                     f"flat interest of {whole(t['interest_pct'])} percent: {whole(t['repay_eur'])} gold pieces repaid "
                     f"{t['due']}. How do you answer?",
                suggestions=["I take the loan", "No, I decline", "I look around instead"],
            )  # fmt: skip
        return S.OfferOut(
            kind="fast_forward",
            text="With everything committed, the days begin to pass. Are you ready to wait?",
        )  # fmt: skip

    def offer_answer(self, c: dict[str, Any]) -> S.TextOut:
        return S.TextOut(
            text="The lender counts the coins into your purse and the room goes back to its own "
                 "business. What do you do next?"
        )  # fmt: skip

    def forward(self, c: dict[str, Any]) -> S.TextOut:
        why = str(c.get("why") or "")
        lead = {
            "declined": "You turn the offer down, and the offerer shrugs and fades into the crowd. ",
            "ignored": "The offer goes unanswered, and the offerer drifts away to other customers. ",
        }.get(why.split(":")[0], "")
        return S.TextOut(
            text=lead + "With everything committed, nothing is left for you to decide. The days pass "
            "over the guild's halls, the rain comes and goes, and the horizon draws near."
        )  # fmt: skip

    def decide(self, c: dict[str, Any]) -> S.DecideOut:
        ctx: C.AgentContext = c["ctx"]
        text = str(c.get("input") or "")
        action, amount, portion = rules.parse_decision(text)
        from financequest.agents.campaign.narration import decision_suggestions

        low = text.lower()
        if action is None and _has(low, *_MOVE_PHRASES, "explore", "look around", "talk to", "speak to"):
            return S.DecideOut(kind="other")
        if action is None:
            return S.DecideOut(
                kind="question", suggestions=decision_suggestions(ctx),
                text="The broker taps the ledger, patient. Tell me plainly: do you put coins in, "
                     "take coins out, or wait?",
            )  # fmt: skip
        reaction = {
            "buy": "The broker's quill scratches your name into the shareholders' book, and a "
                   "clerk nods at you with new respect. How does it feel to have coins in the game?",
            "sell": "Coins slide back across the counter into your purse. A trader nearby raises "
                    "an eyebrow at your choice. Where do you go from here?",
            "hold": "You keep your purse closed. The broker shrugs and turns to the next customer. "
                    "What will you look into next?",
        }[action]
        loss, why = _take_damage() if action != "hold" else (0, "")  # a hold costs nothing
        if loss > 0:
            reaction = f"You lose {loss} HP: {why}. {reaction}"
        return S.DecideOut(
            kind="decision", action=action, amount_eur=amount, portion=portion,  # type: ignore[arg-type]
            text=reaction, suggestions=decision_suggestions(ctx),
            hp_loss=loss, hp_reason=why if loss else "",
            reasoning=(why_ := reasoning_mod.extract_inline(text)),
            reasoning_sufficient=reasoning_mod.is_sufficient(why_),
        )  # fmt: skip

    def hint(self, c: dict[str, Any]) -> S.TextOut:
        where = c["target"]["location_name"]
        return S.TextOut(
            text=f"A lantern burns late in the window of the {where}. Whatever you have not yet "
            "read is waiting there. Will you go and look?"
        )

    def summary(self, c: dict[str, Any]) -> S.SummaryOut:
        ctx: C.AgentContext = c["ctx"]
        visited = ", ".join(x["name"] for x in ctx.locations if x["visited"]) or "nowhere yet"
        return S.SummaryOut(
            summary=f"After {ctx.turn_count} turns the hero has visited {visited} and found: "
            f"{_names(ctx, ctx.found) or 'nothing yet'}."
        )

    # ---- Buddy ------------------------------------------------------------------------------------------
    def buddy(self, c: dict[str, Any]) -> S.BuddyOut:
        ctx: C.AgentContext = c["ctx"]
        text: str = c["input"]
        if _has(text, "real company", "which company", "what company", "who is", "ticker", "real name",
                "stock symbol", "is this", "is it ", "what year", "which year", "when is this",
                "when was", "when did", "real life", "actual company") or re.search(r"\b(1[89]|20)\d\d\b", text):
            return S.BuddyOut(
                text="I don't know that, and I would not say if I did: the answer is revealed at the "
                "end, after you decide. Until then, the clues are what you have: which one would "
                "you read again?", intent="identity_request", mood="calm")  # fmt: skip
        if _has(text, "price will", "will the price", "what will", "end of the quest", "go up", "go down", "next week", "future"):
            return S.BuddyOut(
                text="Nobody can know that, and neither can I. What I can do is point you to the "
                "evidence: which ledger figures seem to disagree?", intent="future_request",
                mood="thinking")  # fmt: skip
        if _has(text, "should i", "buy", "sell", "invest in", "which stock", "guaranteed", "guarantee", "tell me what to"):
            return S.BuddyOut(
                text="That is your call, and nobody can hand you a sure outcome. What evidence would "
                "make you more or less confident?", intent="advice_request", mood="curious")
        if _has(text, "drawdown"):
            return S.BuddyOut(
                text="A drawdown is how far a price has fallen from its previous high. If something "
                "peaked at 10 and slid to 8, the drawdown is 2, or 20 percent of the peak.",
                intent="concept", mood="cheerful")  # fmt: skip
        concept = _concept(text)
        if concept:
            return S.BuddyOut(text=concept, intent="concept", mood="cheerful")
        if ctx.screen and ctx.screen.get("summary"):
            s = ctx.screen["summary"]
            return S.BuddyOut(
                text=f"On this board the price went from {s['first_close']} to {s['last_close']} "
                f"between day {s['first_day']} and day {s['last_day']}. A board shows what happened, "
                "not why. Which ledger might explain it?", intent="other", mood="thinking")  # fmt: skip
        if ctx.screen and ctx.screen.get("entries"):
            e = ctx.screen["entries"][0]
            return S.BuddyOut(
                text=f"This page says: {first_sentences(e['text'], 1, 30)} Compare it with the "
                "other ledger: do they tell the same story?", intent="other", mood="curious")  # fmt: skip
        unfound = ctx.unfound()
        where = ctx.location_name(unfound[0]["location"]) if unfound else None
        tip = f" You might look again at the {where}." if where else ""
        return S.BuddyOut(
            text="Happy to help. Tell me which word or figure puzzles you, and I will explain it "
            f"plainly.{tip}", intent="other", mood="calm")  # fmt: skip

    # ---- setup, debrief, xp, advice -----------------------------------------------------------------------
    def setup(self, c: dict[str, Any]) -> S.SetupOut:
        ctx: C.AgentContext = c["ctx"]
        out = prepared_setup(ctx)
        have = {x["key"] for x in ctx.locations}
        out.extra_locations = [
            S.ExtraLocation(key=s["key"], description=s.get("description", ""))
            for s in ctx.pack.seeds if s["key"] not in have
        ]  # fmt: skip
        return out

    def debrief(self, c: dict[str, Any]) -> S.DebriefOut:
        ctx: C.AgentContext = c["ctx"]
        from financequest.campaign.xp import excerpt

        mine = excerpt(ctx.player_texts[0] if ctx.player_texts else "", 80)
        sound = (
            f"You wrote “{mine}”, which shows you looked for reasons rather than rumours."
            if mine else "You gave reasons in your own words."
        )
        given = [d for d in ctx.decisions if d.get("reasoning")]
        if given:
            first = excerpt(str(given[0]["reasoning"]), 60)
            how = (
                "You gave reasons for "
                + ("every decision" if len(given) == len(ctx.decisions) else "some of your decisions")
                + f", such as “{first}”. Your stated reasons matched what you did."
            )
        else:
            how = "You gave no reasoning for your decisions along the way, so your thinking is hard to follow."
        return S.DebriefOut(
            sound_reasoning=sound, how_you_reasoned=how,
            overlooked=", ".join(ctx.overlooked) if ctx.overlooked else "Nothing important",
            luck=f"Much of this result turned on events no one could know at story day "
            f"{ctx.gv.clock_day}. Judge your process, not the outcome alone.",
            reflection_question=c.get("question") or "What would you check first next time?",
        )

    def xp(self, c: dict[str, Any]) -> S.XpOut:
        from financequest.agents.campaign.narration import heuristic_xp

        return S.XpOut(scores=[
            S.XpScore(category=r.category, score=r.score, rationale=r.rationale, quote=r.quote)
            for r in heuristic_xp(c["rubric"], c["texts"], c.get("decision"))
        ])  # fmt: skip

    def advice(self, c: dict[str, Any]) -> S.AdviceCheck:
        text: str = c["text"]
        if re.search(r"\b(nobody|no\s+one)\s+can\b|\bcannot\b|can'?t\s+know|no\s+guarantee", text, re.I):
            return S.AdviceCheck()  # a denial, not a promise or a prediction
        return S.AdviceCheck(
            contains_recommendation=bool(
                re.search(r"\b(you\s+(should|must)\s+(buy|sell|invest|hold)|i\s+(recommend|suggest)\s+"
                          r"(buying|selling|that you buy|you buy)|(buy|sell)\s+(it|now|the|this)|"
                          r"good\s+investment)\b", text, re.I)),
            promises_profit=bool(re.search(r"guarantee|risk[- ]free|can'?t\s+lose|sure\s+thing|profit\s+is", text, re.I)),
            predicts_future=bool(re.search(r"\bwill\s+(rise|go\s+up|fall|drop|crash|soar|climb|end)|going\s+to\s+(rise|fall|drop|crash)", text, re.I)),
        )  # fmt: skip


_CONCEPTS = {
    "revenue": "Revenue, or sales, is the money a company bills for what it sold. It is not profit: costs still come out of it.",
    "sales": "Sales are what customers were billed. They are not earnings and not cash: costs and timing come in between.",
    "earnings": "Earnings are what is left of sales after costs are counted in the ledger. They are an accounting figure, not coin in the vault.",
    "cash flow": "Cash flow follows the coin that actually moved in and out. A guild can report earnings while its vault drains, so read both.",
    "debt": "Debt is money owed. It is not bad in itself, but it must be repaid, so large debt next to thin cash deserves a second look.",
    "equity": "Equity, the owners' claim, is what would remain if everything were sold and every debt repaid on paper. It is not spendable coin.",
    "diversif": "Diversifying means not putting everything in one place, so one bad surprise cannot sink the whole purse.",
    "margin": "A margin compares profit with sales: how much of each coin of sales is left after costs. A shrinking margin is a question to ask.",
    "ledger": "A ledger is the company's formal record of what it earned, owed and owned. Reading two ledgers side by side shows what each leaves out.",
}


def _concept(text: str) -> str | None:
    for key, answer in _CONCEPTS.items():
        if key in text.lower():
            return answer
    return None


def _turn_allowed(ctx: C.AgentContext, r: S.RouteOut) -> tuple[str, set[str]]:
    from financequest.agents.campaign.graphs import turn_extra

    return turn_extra(ctx, r)


def _remaining_need(ctx: C.AgentContext, given: set[str]) -> list[str]:
    """Free and key clues at this checkpoint still unfound after this reply."""
    gated = rules.gated_clue_ids(ctx.pack)
    got = set(ctx.found) | given
    return [
        e["id"] for e in ctx.content["evidence"]
        if e["id"] not in got and (e["id"] not in gated or e["key"])
    ]  # fmt: skip


def _suggestions(ctx: C.AgentContext, given: list[str], at: str | None = None) -> list[str]:
    out: list[str] = []
    got = set(ctx.found) | set(given)
    gated = rules.gated_clue_ids(ctx.pack)
    cur = at or (ctx.current["key"] if ctx.current else "")
    for ch in ctx.content["characters"]:
        if ch["location"] == cur:
            out.append(f"Ask {ch['name']} what they know")
    for e in ctx.unfound():
        if e["id"] in got or e["id"] in gated:
            continue
        if e["location"] != cur:
            name = ctx.location_name(e["location"])
            if f"Go to the {name}" not in out:
                out.append(f"Go to the {name}")
    for c in ctx.challenges:
        if c["state"] == "open" and not c["optional"]:
            out.append(f"Examine {c['title']}")
    out.append("Ask CommerzBuddy what to look at")
    return list(dict.fromkeys(out))[:3]
