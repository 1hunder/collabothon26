"""Plain data the SSE driver (api/sse.py) streams. No FastAPI imports: builders in turns.py
produce a ``StreamPlan`` and the driver runs it.

Three phases per narrated reply, so no transaction is ever held across an LLM call:
  A. prepare (short transaction): validate, log the player's input, build the gated context
  B. work (no transaction): the LangGraph graph, guards included
  C. commit (short transaction): apply engine effects, store the guarded reply in the event log
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Streamed:
    """A fully guarded and committed reply, ready to stream."""

    text: str
    done: dict[str, Any]
    cards: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamPlan:
    campaign_id: uuid.UUID
    replay: Streamed | None = None  # an idempotent repeat: stream the stored reply
    work: Callable[[], Any] | None = None
    commit: Callable[[Any], Streamed] | None = None
    deadline_s: float = 15.0
    on_timeout: Callable[[], Any] | None = None  # produce a result instead of ``lost_thread``
    after: Callable[[Streamed], None] | None = None  # background follow-up (rolling summary)
    serialize: bool = True  # hold the per-campaign lock across work + commit (all but Buddy)
