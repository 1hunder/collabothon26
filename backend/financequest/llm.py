"""Model factory. Real: ChatAnthropic. FAKE_LLM=1: a scripted fake returning given responses."""

from __future__ import annotations

import logging
from typing import Any

from financequest.config import get_settings


class ScriptedLLM:
    """Returns pre-set responses in order (the last one repeats). Mirrors the tiny slice of the
    LangChain chat-model API the importer uses."""

    def __init__(self, responses: list[Any]) -> None:
        if not responses:
            raise ValueError("ScriptedLLM needs at least one response")
        self._responses = list(responses)
        self.calls: list[Any] = []

    def with_structured_output(self, schema: Any, **_: Any) -> ScriptedLLM:
        return self

    def invoke(self, messages: Any, **_: Any) -> Any:
        self.calls.append(messages)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def get_chat_model(fake_responses: list[Any] | None = None) -> Any:
    settings = get_settings()
    if fake_responses is not None or settings.fake_llm:
        if fake_responses is None:
            raise RuntimeError("FAKE_LLM=1 requires scripted responses from the caller")
        return ScriptedLLM(fake_responses)
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=settings.model_id, max_tokens=32000)


# ======================================================================
# Node-level model layer for the LangGraph graphs (spec 002, reid/graph.py)
# ======================================================================
#
# The graphs talk to a ``NodeLLM`` so that real calls (ChatAnthropic), scripted test fakes and the
# FAKE_LLM=1 default all go through one seam. Every call returns an ``LLMResult`` carrying the stop
# reason and usage, so the graph can check ``stop_reason`` (a refusal is a failed call) and write
# telemetry. ChatAnthropic (langchain-anthropic >= 1.7) forwards ``effort`` (output_config.effort),
# ``cache_control`` content blocks and server-tool blocks (server_tool_use /
# web_search_tool_result), so no node needs the raw ``anthropic`` SDK. The one thing LangChain does
# not give us is an API-level refusal ``fallbacks`` list; the graph retries a refusal once through
# ``run(..., fallback=True)``, which uses REFUSAL_FALLBACK_MODEL (default: the same model).

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from typing import Protocol  # noqa: E402

from pydantic import BaseModel  # noqa: E402

WEB_SEARCH_TOOL_TYPE = "web_search_20260209"  # current version for claude-opus-5-5
MAX_PAUSE_TURNS = 4
log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    parsed: BaseModel | None = None
    content: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)
    latency_s: float = 0.0

    @property
    def text(self) -> str:
        return "".join(str(b.get("text", "")) for b in self.content if b.get("type") == "text")

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class NodeLLM(Protocol):
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
    ) -> LLMResult: ...


def extract_json_object(text: str) -> Any:
    """Parse the last top-level JSON object in ``text`` (tolerates prose and code fences)."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    fence = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence[-1])
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def _blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    out: list[dict[str, Any]] = []
    for b in content or []:
        if isinstance(b, str):
            out.append({"type": "text", "text": b})
        elif isinstance(b, dict):
            out.append(b)
        elif hasattr(b, "model_dump"):
            out.append(b.model_dump())
    return out


def _usage_of(msg: Any) -> dict[str, int]:
    um = getattr(msg, "usage_metadata", None) or {}
    details = um.get("input_token_details") or {}
    raw = (getattr(msg, "response_metadata", None) or {}).get("usage") or {}
    server = raw.get("server_tool_use") or {}
    return {
        "input_tokens": int(um.get("input_tokens", 0)),
        "output_tokens": int(um.get("output_tokens", 0)),
        "cache_read_tokens": int(details.get("cache_read", 0)),
        "cache_creation_tokens": int(details.get("cache_creation", 0)),
        "web_search_requests": int(server.get("web_search_requests", 0) or 0),
    }


class AnthropicNodeLLM:
    """Real model: ChatAnthropic(model=MODEL_ID, max_retries=5) per call, effort per node."""

    def __init__(self, max_tokens: int = 16000) -> None:
        self.max_tokens = max_tokens

    def _model(self, effort: str, fallback: bool) -> Any:
        from langchain_anthropic import ChatAnthropic

        s = get_settings()
        model_id = os.environ.get("REFUSAL_FALLBACK_MODEL") if fallback else None
        kwargs: dict[str, Any] = {
            "model": model_id or s.model_id,
            "max_tokens": self.max_tokens,
            "max_retries": 5,
            "effort": effort,
        }
        if s.anthropic_api_key:
            kwargs["api_key"] = s.anthropic_api_key
        return ChatAnthropic(**kwargs)

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
        model = self._model(effort, fallback)
        t0 = time.monotonic()
        if web_search_max_uses is None:
            structured = model.with_structured_output(
                schema, method="json_schema", include_raw=True
            )
            out = structured.invoke(list(messages))
            raw = out["raw"]
            return LLMResult(
                parsed=out.get("parsed"),
                content=_blocks(raw.content),
                stop_reason=(raw.response_metadata or {}).get("stop_reason"),
                usage=_usage_of(raw),
                latency_s=time.monotonic() - t0,
            )
        # Web round: the server tool cannot be combined with forced-tool structured output, so
        # the report is requested as JSON in the final text block and validated by the graph.
        bound = model.bind_tools(
            [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": web_search_max_uses}]
        )
        convo = list(messages)
        blocks: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        stop: str | None = None
        for _ in range(MAX_PAUSE_TURNS):
            msg = bound.invoke(convo)
            new_blocks = _blocks(msg.content)
            blocks += new_blocks
            for k, v in _usage_of(msg).items():
                usage[k] = usage.get(k, 0) + v
            stop = (msg.response_metadata or {}).get("stop_reason")
            if stop == "pause_turn":
                convo = [*convo, msg]  # the server resumes its own tool loop
                continue
            if stop != "tool_use":
                break
            # Only the web search server tool is offered, but the model sometimes ends a turn on
            # a client-side tool call (seen live). Answer each call with an error result so the
            # model finishes its answer with what it has, instead of failing the whole node.
            calls = [b for b in new_blocks if b.get("type") == "tool_use"]
            log.info("%s: stray tool_use %s; asking the model to finish", node,
                     [c.get("name") for c in calls])  # fmt: skip
            if not calls:
                convo = [*convo, msg]
                continue
            from langchain_core.messages import HumanMessage

            convo = [*convo, msg, HumanMessage(content=[
                {"type": "tool_result", "tool_use_id": c["id"], "is_error": True,
                 "content": "This tool is not available. Use web_search only, or finish your "
                            "answer now with what you already know."}
                for c in calls
            ])]  # fmt: skip
        return LLMResult(
            content=blocks, stop_reason=stop, usage=usage, latency_s=time.monotonic() - t0
        )


# ---- fakes --------------------------------------------------------------
@dataclass
class FakeRefusal:
    """Scripted response: the model refused (stop_reason == 'refusal')."""


@dataclass
class FakeReply:
    """Scripted raw reply (content blocks as returned by the API), parsed by the graph."""

    content: list[dict[str, Any]]
    stop_reason: str | None = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class FakeCall:
    node: str
    persona: str | None
    messages: list[Any]
    effort: str
    web_search_max_uses: int | None
    fallback: bool


class FakeNodeLLM:
    """Scripted, deterministic. ``scripts`` maps ``"node:persona"`` or ``"node"`` to a list of
    responses consumed in order (the last repeats). A response is a BaseModel, a dict (validated
    against the call's schema), ``FakeRefusal``, ``FakeReply`` or an Exception (raised). Keys with
    no script fall through to ``default`` when given, else raise."""

    def __init__(
        self, scripts: dict[str, list[Any]] | None = None, default: NodeLLM | None = None
    ) -> None:
        self._scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self._default = default
        self._lock = threading.Lock()
        self.calls: list[FakeCall] = []

    def calls_for(self, node: str) -> list[FakeCall]:
        return [c for c in self.calls if c.node == node]

    def _next(self, key: str) -> Any:
        q = self._scripts[key]
        return q.pop(0) if len(q) > 1 else q[0]

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
        with self._lock:
            self.calls.append(
                FakeCall(node, persona, list(messages), effort, web_search_max_uses, fallback)
            )
            key = next((k for k in (f"{node}:{persona}", node) if k in self._scripts), None)
            item = self._next(key) if key else None
        if key is None:
            if self._default is None:
                raise KeyError(f"no fake script for node {node!r} persona {persona!r}")
            return self._default.run(
                node,
                messages,
                schema=schema,
                effort=effort,
                persona=persona,
                web_search_max_uses=web_search_max_uses,
                context=context,
                fallback=fallback,
            )
        if isinstance(item, BaseException):
            raise item
        usage = {"input_tokens": 100, "output_tokens": 50}
        if isinstance(item, FakeRefusal):
            return LLMResult(stop_reason="refusal", usage=usage)
        if isinstance(item, FakeReply):
            return LLMResult(
                content=item.content, stop_reason=item.stop_reason, usage=item.usage or usage
            )
        parsed = item if isinstance(item, BaseModel) else schema.model_validate(item)
        content = [{"type": "text", "text": parsed.model_dump_json()}]
        return LLMResult(parsed=parsed, content=content, usage=usage)


class DefaultFakeNodeLLM:
    """FAKE_LLM=1 behaviour: valid, deterministic output derived from ``context`` so a whole graph
    runs without keys. Guessers never recognise anything and rate the story 4."""

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
        if node.startswith("veteran_"):  # the Tavern's Veteran: scripted Brannoc
            from financequest.agents.veteran.fake import VeteranFakeLLM

            return VeteranFakeLLM().run(
                node, messages, schema=schema, effort=effort, persona=persona,
                web_search_max_uses=web_search_max_uses, context=context, fallback=fallback,
            )  # fmt: skip
        if node.startswith("campaign_"):  # spec 003 agent nodes: scripted Campaign Master
            from financequest.agents.campaign.fake import CampaignFakeLLM

            return CampaignFakeLLM().run(
                node, messages, schema=schema, effort=effort, persona=persona,
                web_search_max_uses=web_search_max_uses, context=context, fallback=fallback,
            )  # fmt: skip
        from financequest.reid import schemas as sc

        ctx = context or {}
        parsed: BaseModel
        if node == "extract_case":
            parsed = sc.SourceCaseDraft(
                company=str(ctx.get("title", "Unnamed")),
                lesson="A fake lesson.",
                identifying_terms=[str(ctx.get("title", "Unnamed"))],
                beats=[
                    sc.SourceBeatDraft(real_date="start", headline="Start", facts=[]),
                    sc.SourceBeatDraft(real_date="end", headline="End", facts=[]),
                ],
            )
        elif node == "write_disguise":
            tokens = list(ctx.get("tokens", []))
            parsed = sc.DisguiseDraft(
                company_name="Lantern Works",
                sector="Industrials",
                industry="Lantern manufacturing",
                industry_moved=False,
                beats=[
                    sc.DisguiseBeat(
                        story_day_index=i,
                        headline="Lantern Works reports news" + " again" * i,
                        facts=[f"Figure {t}." for t in tokens[i : i + 1]],
                    )
                    for i in range(int(ctx.get("n_beats", 2)))
                ],
            )
        else:
            parsed = sc.GuesserReport(
                top3=[
                    sc.CompanyGuess(company="Fakecorp Alpha", confidence=10),
                    sc.CompanyGuess(company="Fakecorp Beta", confidence=5),
                    sc.CompanyGuess(company="Fakecorp Gamma", confidence=2),
                ],
                start_confidence=5,
                readability=4,
            )
        return LLMResult(
            parsed=parsed,
            content=[{"type": "text", "text": parsed.model_dump_json()}],
            usage={"input_tokens": 1, "output_tokens": 1},
        )


def get_node_llm(scripts: dict[str, list[Any]] | None = None) -> NodeLLM:
    """Scripts given -> FakeNodeLLM (falling back to the default fake); FAKE_LLM=1 -> default
    fake; otherwise the real ChatAnthropic-backed runner."""
    if scripts is not None:
        return FakeNodeLLM(scripts, default=DefaultFakeNodeLLM())
    if get_settings().fake_llm:
        return DefaultFakeNodeLLM()
    return AnthropicNodeLLM()
