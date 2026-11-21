"""The scripted Veteran (FAKE_LLM=1 and tests): deterministic replies built only from the memory
blocks, so every figure and quote is already in the allowlist. Every reply ends with a question."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from financequest.agents.veteran.context import VeteranContext
from financequest.agents.veteran.schemas import VeteranOut
from financequest.llm import LLMResult

_ADVICE = re.compile(
    r"\b(should i|shall i|what (should|do) i (buy|sell)|which (stock|company|share)|tell me what to|"
    r"buy or sell|is it a good (buy|investment)|invest in)\b",
    re.I,
)
_RUNNING = re.compile(
    r"\b(current|this) (quest|campaign|company)|right now|my quest now|the quest i'?m on|"
    r"what happens next|how does it end|will (it|the price)\b",
    re.I,
)
_STORY = re.compile(
    r"\b(your (own )?(story|stories|adventures?|quests?)|tell me a story|about you)\b", re.I
)


def aside(text: str) -> str | None:
    """A turn that steps off the walkthrough: advice, the running quest, or one of his stories."""
    if _ADVICE.search(text):
        return "advice"
    if _RUNNING.search(text):
        return "running"
    if _STORY.search(text):
        return "story"
    return None


STORIES = (
    (
        "Years back, in the salt marshes, a crier shouted that the barges were sinking. I sold my share "
        "of the salt works at dawn for half its worth. By noon the barges floated fine: the crier had "
        "seen one leaky boat. Since then I read the harbour log before I listen to the square. What do "
        "you read first when bad news breaks?"
    ),
    (
        "I once swore on my beard that the copper mine at Grey Ford could not fail. I had read one good "
        "report and stopped looking. The report I skipped spoke of flooded tunnels. I kept the beard and "
        "lost the coin. How sure were you last time, and on what?"
    ),
    (
        "My old captain used to say: count the doors before you pick one. I lost a winter's pay at "
        "Eastmere because I decided in the first tavern I walked into. The answer sat in the library "
        "across the square. Which room do you tend to skip?"
    ),
    (
        "Best call I ever made lost money. Sound reasoning, the ledgers backed me, then a storm took the "
        "fleet. Worst call I ever made doubled my purse. Had I learned from results instead of reasons, "
        "I would be a beggar now. Which of your results fooled you most?"
    ),
)
STORY_FOR = {
    "panic_sell": 0,
    "sold_on_news": 0,
    "overconfident": 1,
    "missed_clues": 2,
    "thin_reasons": 3,
}

JUDGEMENT = {
    "sound": "That is sound thinking: you named a reason, and it came from what you had seen.",
    "hasty": "That one was written in a hurry. Fear held the quill, not the ledgers.",
    "thin": "You did not write down why. Without a reason you cannot learn from it, win or lose.",
}
LUCK = {
    ("sound", "kind"): "The price went your way afterwards. Earned, but note why it worked.",
    (
        "sound",
        "cruel",
    ): "The price went against you afterwards. That was the die, not your thinking.",
    (
        "hasty",
        "kind",
    ): "The price happened to favour you. A lucky escape; it will not come every time.",
    ("hasty", "cruel"): "And the price went against you after. A lesson paid in full.",
    (
        "thin",
        "kind",
    ): "The price went your way after, but that tells us nothing about the reasoning.",
    (
        "thin",
        "cruel",
    ): "The price went against you after, but that alone tells us nothing about the reasoning.",
}
QUESTION = {
    "sound": "What made you trust that reason?",
    "hasty": "What were you afraid of in that moment?",
    "thin": "If you made that call again, what reason would you write?",
}
MOOD = {"sound": "approving", "hasty": "stern", "thin": "pondering"}
BAND = {
    "well_matched": "Your confidence matched what you knew. That is rarer than a good result.",
    "overconfident": "You were surer than the evidence allowed.",
    "missed": "You read it one way and the market went the other. It happens to the best of us.",
    "underconfident": "You read it right but trusted yourself little.",
    "hedged": "You kept it near even odds. Honest, when the signs are mixed.",
}
ACTION = {"buy": "you bought", "sell": "you sold", "hold": "you held"}


def _cut(text: str, words: int = 28) -> str:
    w = text.split()
    return " ".join(w[:words]) + ("…" if len(w) > words else "")


def _quote(text: str, words: int = 28) -> str:
    """The hero's own words in quotes, closing the sentence once (no "….”." doubling)."""
    q = _cut(text, words)
    return f"“{q}”" + ("" if q[-1:] in ".!?…" else ".")


def _named(f: dict[str, Any]) -> str:
    return f"{f['title']}, the road of {f['company']}" + (
        f" that we now know was {f['real_name']}" if f.get("real_name") else ""
    )


class VeteranFakeLLM:
    """Implements ``NodeLLM.run`` for the ``veteran_*`` nodes."""

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
        c = context or {}
        parsed = talk(c["ctx"], str(c.get("input", "")))
        return LLMResult(
            parsed=parsed,
            content=[{"type": "text", "text": parsed.model_dump_json()}],
            usage={"input_tokens": 1, "output_tokens": 1},
        )


def talk(ctx: VeteranContext, text: str) -> VeteranOut:
    kind = aside(text)
    if kind == "advice":
        return VeteranOut(
            text="I do not hand out orders. I have watched too many roads end badly that way. What I "
            "can do is help you see your own reasoning. Which of your decisions do you want to look "
            "at again?",
            mood="stern",
            suggestions=[
                "Walk me through my last quest",
                "What habits do you see?",
                "Tell me a story",
            ],
        )
    if kind == "running":
        return VeteranOut(
            text="Not a word about the road you are on. That one is yours to walk. Finish it and I "
            "will hear every step. Shall we look back at an old road instead?",
            mood="stern",
            suggestions=_menu(ctx),
        )
    if not ctx.has_memory:
        return _intro(ctx)
    if kind == "story":
        return VeteranOut(text=STORIES[_story_index(ctx)], mood="pondering", suggestions=_menu(ctx))
    if ctx.topic == "habits":
        return _habits(ctx)
    if ctx.focus:
        return _walk(ctx)
    return _greet(ctx)


def _menu(ctx: VeteranContext) -> list[str]:
    if not ctx.recent:
        return ["What kind of quests are there?", "Tell me another story", "I'll be back"]
    last = ctx.recent[-1]
    return [
        f"Walk me through {last['title']}",
        "What habits do you see in me?",
        "Tell me one of your stories",
    ]


def _story_index(ctx: VeteranContext) -> int:
    for r in (ctx.profile or {}).get("weaknesses") or []:
        if r["tag"] in STORY_FOR:
            return (STORY_FOR[r["tag"]] + ctx.step) % len(STORIES)
    tags = ctx.recent[-1]["tags"] if ctx.recent else []
    base = next((STORY_FOR[t] for t in tags if t in STORY_FOR), 3)
    return (base + ctx.step) % len(STORIES)


def _intro(ctx: VeteranContext) -> VeteranOut:
    if ctx.step == 0:
        return VeteranOut(
            text="Pull up a stool. Name's Brannoc. Forty winters on the trade roads, and I once lost "
            "a mule and half my coin to a rumour I never checked. That taught me more than any win. "
            "I keep a ledger of every quest the young ones bring back here. Yours is empty for now. "
            "Finish your first quest and come find me by the fire; we will walk that road back "
            "together. What sort of quest are you after?",
            mood="listening",
            suggestions=["Tell me another story", "What will we talk about?", "I'll be back"],
        )
    if ctx.step % 2 == 1:
        return VeteranOut(
            text=STORIES[ctx.step // 2 % len(STORIES)],
            mood="pondering",
            suggestions=["Tell me another story", "Why do you keep a ledger?", "I'll be back"],
        )
    return VeteranOut(
        text="When you come back from your first quest, we look at every decision you made: what "
        "you knew, what you wrote, and what was only luck. No orders, just honest questions. Ready "
        "to go find one?",
        mood="listening",
        suggestions=["Tell me another story", "Why separate luck?", "I'll be back"],
    )


def _greet(ctx: VeteranContext) -> VeteranOut:
    last = ctx.recent[-1]
    n = len(ctx.recent)
    ended = {"gain": "in gain", "loss": "in loss", "flat": "about even"}.get(last["result"], "")
    quests = "one of your quests" if n == 1 else f"{n} of your quests"
    return VeteranOut(
        text=f"Back by the fire. I remember {quests}. The last was {last['title']}, and it ended "
        f"{ended}. We can walk one road back step by step, or look at the habits that follow you "
        "from quest to quest. Where shall we start?",
        mood="listening",
        suggestions=_menu(ctx),
    )


def _walk(ctx: VeteranContext) -> VeteranOut:
    f = ctx.focus or {}
    decisions = f.get("decisions") or []
    n = len(decisions)
    step = ctx.step
    if step < n:
        d = decisions[step]
        verb = ACTION.get(d["action"], "you chose")
        amount = (
            f" {d['amount_eur']} gp"
            if d["action"] in ("buy", "sell") and d["amount_eur"]
            else ""
        )
        luck = LUCK.get((d["judgement"], d["luck"]), "")
        said = f" You said: {_quote(d['reasoning'], 14)}" if d.get("reasoning") else ""
        head = (
            f"{_named(f)}. You made {_count(n)} there. The first, {d['when'].lower()}:"
            if step == 0
            else f"Next, {d['when'].lower()}:"
        )
        return VeteranOut(
            text=f"{head} {verb}{amount} and wrote {_quote(d['text'])}{said} {JUDGEMENT[d['judgement']]} "
            f"{luck} {QUESTION[d['judgement']]}".replace("  ", " "),
            mood=MOOD[d["judgement"]],
            show_timeline=step == 0,
            suggestions=[
                "Go on to the next one",
                "Why was that luck?",
                "Show me the whole timeline",
            ],
        )
    fc = f.get("forecast") or {}
    if step == n:
        said = (
            f"You said {fc['pct']}% likely higher, with {fc['confidence']} confidence."
            if fc.get("pct") is not None
            else "You left the forecast open."
        )
        ended = "higher" if fc.get("market") == "up" else "lower"
        return VeteranOut(
            text=f"Then the forecast. {said} The price ended {ended}. {BAND.get(fc.get('band', 'hedged'), '')} "
            "What would have changed your confidence?",
            mood="pondering",
            suggestions=["I trusted one clue too much", "I wasn't sure at all", "Go on"],
        )
    if step == n + 1:
        missed = f.get("missed") or []
        if missed:
            names = ", ".join(missed[:3])
            return VeteranOut(
                text=f"Some doors you never opened on that road: {names}. A clue unread is a question "
                "unasked. Which of those would you look for first next time?",
                mood="stern",
                suggestions=["The first one", "I ran out of time", "Go on"],
            )
        return VeteranOut(
            text="You found every key clue on that road. Good scouting; most rush past half of them. "
            "What helped you find them?",
            mood="approving",
            suggestions=["I visited every place", "I asked the locals", "Go on"],
        )
    if step == n + 2:
        r = f.get("result") or {}
        kind = {"gain": "a gain", "loss": "a loss", "flat": "about even"}.get(
            r.get("kind") or "", "its end"
        )
        pct = (
            f" of {r['pnl_pct']}%"
            if r.get("pnl_pct") is not None and r.get("kind") != "flat"
            else ""
        )
        moral = ""
        if r.get("kind") == "loss" and f.get("sound_overall"):
            moral = " Sound thinking, cruel luck. Keep the thinking."
        elif r.get("kind") == "gain" and not f.get("sound_overall"):
            moral = " The purse grew, but the reasons were thin. Do not let the result teach you."
        refl = (
            f" Afterwards you wrote: “{_cut(f['reflection'], 24)}”." if f.get("reflection") else ""
        )
        return VeteranOut(
            text=f"It ended in {kind}{pct}.{moral}{refl} What lesson from this road would you keep in "
            "your journal?",
            mood="approving" if f.get("sound_overall") else "pondering",
            suggestions=["Keep a lesson in my journal", "What habits do you see?", "Another quest"],
        )
    return VeteranOut(
        text="That is the whole road, start to end. Pick another quest, or we can look at the habits "
        "that follow you. Which shall it be?",
        mood="listening",
        suggestions=_menu(ctx),
    )


def _count(n: int) -> str:
    return "one decision" if n == 1 else f"{n} decisions"


def _habits(ctx: VeteranContext) -> VeteranOut:
    p = ctx.profile or {}
    strengths, weaknesses = p.get("strengths") or [], p.get("weaknesses") or []
    step = ctx.step % 3
    if step == 0:
        if not strengths and not weaknesses:
            emerging = [r["label"] for r in p.get("emerging") or []][:3]
            seen = "; ".join(emerging) if emerging else "a quiet hand"
            return VeteranOut(
                text=f"One road is not a pattern yet. From your last quest I saw this: {seen}. Come "
                "back after another and we will see what sticks. Which of those surprises you?",
                mood="pondering",
                suggestions=[
                    "Tell me more about that",
                    "Tell me one of your stories",
                    "Walk me through it",
                ],
            )
        good = " and ".join(r["label"] for r in strengths[:2])
        bad = " and ".join(r["label"] for r in weaknesses[:2])
        parts = []
        if good:
            parts.append(f"Quest after quest, you {good}. Keep that.")
        if bad:
            parts.append(f"But one habit follows you: you {bad}.")
        return VeteranOut(
            text=f"I have {p.get('quests', 0)} of your quests in my ledger, and a pattern or two. "
            f"{' '.join(parts)} Where do you think that habit comes from?",
            mood="stern" if bad else "approving",
            suggestions=[
                "I get nervous on bad news",
                "Show me my milestones",
                "Tell me one of your stories",
            ],
        )
    if step == 1:
        ms = [m["label"] for m in p.get("milestones") or []]
        listed = "; ".join(ms[-3:]) if ms else "none yet, but the road is long"
        return VeteranOut(
            text=f"Milestones in my ledger for you: {listed}. A sound loss counts as much as a win, "
            "in my book. Which one are you proudest of?",
            mood="approving",
            suggestions=[
                "The sound loss, honestly",
                "My first gain",
                "Tell me one of your stories",
            ],
        )
    return VeteranOut(text=STORIES[_story_index(ctx)], mood="pondering", suggestions=_menu(ctx))
