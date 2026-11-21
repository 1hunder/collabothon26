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
        for ch in ctx.challenges:
            title_words = {w for w in re.findall(r"[a-z]+", ch["title"].lower()) if len(w) > 3}
            if title_words & words or ch["key"].lower() in low:
                return S.RouteOut(intent="challenge", challenge_key=ch["key"])
        here = ctx.current["key"] if ctx.current else ""
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
        if _has(low, "go to", "visit", "head to", "walk to", "travel", "enter", "back to", "return to"):
            for loc in ctx.locations:
                name_words = {w for w in re.findall(r"[a-z]+", loc["name"].lower()) if len(w) > 3}
                if name_words & words or loc["key"].replace("_", " ") in low:
                    return S.RouteOut(intent="move", location_key=loc["key"])
        if _has(low, "joke", "weather", "pizza", "football", "recipe", "movie", "song", "poem", "cats"):
            return S.RouteOut(intent="off_topic")
        return S.RouteOut(intent="free")

    # ---- Campaign Master turn -----------------------------------------------------------------------
    def turn(self, c: dict[str, Any]) -> S.TurnOut:
        ctx: C.AgentContext = c["ctx"]
        r: S.RouteOut = c["route"]
        text: str = c["input"]
        _, allowed = _turn_allowed(ctx, r)
        given: list[str] = []
        speaker = C.CHRONICLER
        body: str
        if r.intent == "move" and r.location_key:
            body, given = self._arrival(ctx, r.location_key, sorted(allowed))
        elif r.intent == "talk":
            body, given, speaker = self._talk(ctx, r, allowed)
        elif r.intent == "challenge":
            body = self._challenge(ctx, r)
        elif r.intent == "off_topic":
            body = (
                "A fine jest, traveller, and the rain applauds. But the mystery will not solve "
                "itself, and the ledgers are waiting."
            )
        else:
            body = self._free(ctx, text)
        remaining = _remaining_need(ctx, set(given))
        nothing_more = ctx.news_shown and not remaining
        if nothing_more:
            body += " There is nothing more to uncover for now. Ready to make your decision?"
            sugg = ["Review what you found", "Ask CommerzBuddy for a recap", "Look around once more"]
        else:
            body += " What would you do?"
            sugg = _suggestions(ctx, given, r.location_key if r.intent == "move" else None)
        return S.TurnOut(text=body, speaker=speaker, suggestions=sugg, clue_ids_given=given,
                         nothing_more_to_uncover=nothing_more)  # fmt: skip

    def _arrival(self, ctx: C.AgentContext, key: str, free: list[str]) -> tuple[str, list[str]]:
        loc = next(x for x in ctx.locations if x["key"] == key)
        here = [ch["name"] for ch in ctx.content["characters"] if ch["location"] == key]
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

    # ---- dice, news, hint, summary ---------------------------------------------------------------------
    def dice(self, c: dict[str, Any]) -> S.TextOut:
        roll = c["roll"]
        clue = roll.get("clue")
        if roll["result"] == "success":
            body = "The dice favour you, and the page gives up its secret."
            if clue:
                body += f" You find: {clue['title']}. {first_sentences(clue['text'], 2, 40)}"
        else:
            body = (
                "The lines swim and a page sticks to the next. A setback, but no dead end. "
                f"{roll.get('alt_source') or 'Ask around and read the documents.'}"
            )
        return S.TextOut(text=body + " What would you do next?")

    def news(self, c: dict[str, Any]) -> S.TextOut:
        ctx: C.AgentContext = c["ctx"]
        return S.TextOut(
            text=f"A hush falls over the {ctx.pack.market_name} as the proclamation is read aloud. "
            "How does this news change your view of the company?"
        )

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
        return S.DebriefOut(
            sound_reasoning=sound,
            overlooked=", ".join(ctx.overlooked) if ctx.overlooked else "Nothing important",
            luck=f"Much of this result turned on events no one could know at story day "
            f"{ctx.gv.clock_day}. Judge your process, not the outcome alone.",
            reflection_question=c.get("question") or "What would you check first next time?",
        )

    def xp(self, c: dict[str, Any]) -> S.XpOut:
        from financequest.agents.campaign.narration import heuristic_xp

        return S.XpOut(scores=[
            S.XpScore(category=r.category, score=r.score, rationale=r.rationale, quote=r.quote)
            for r in heuristic_xp(c["rubric"], c["texts"])
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
        if any(i not in got for i in ch["may_reveal"]) and ch["location"] == cur:
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
