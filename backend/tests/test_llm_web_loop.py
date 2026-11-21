"""The web-search loop recovers when the model ends a turn on a client-side tool call."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from financequest import llm as llm_mod


class _Schema(BaseModel):
    x: int = 0


class _Bound:
    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = replies
        self.calls: list[list[Any]] = []

    def invoke(self, convo: list[Any]) -> AIMessage:
        self.calls.append(list(convo))
        return self.replies.pop(0)


class _Model:
    def __init__(self, bound: _Bound) -> None:
        self.bound = bound

    def bind_tools(self, _tools: Any) -> _Bound:
        return self.bound


def _msg(content: list[dict[str, Any]], stop: str) -> AIMessage:
    return AIMessage(content=content, response_metadata={"stop_reason": stop})  # type: ignore[arg-type]


def test_stray_tool_use_gets_an_error_result_and_the_answer_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = _Bound([
        _msg([{"type": "text", "text": "Let me fetch it."},
              {"type": "tool_use", "id": "toolu_1", "name": "web_fetch", "input": {}}], "tool_use"),
        _msg([{"type": "text", "text": "# Case\\nDone"}], "end_turn"),
    ])  # fmt: skip
    node = llm_mod.AnthropicNodeLLM(1000)
    monkeypatch.setattr(node, "_model", lambda effort, fallback: _Model(bound))
    res = node.run("research_company", [HumanMessage(content="go")], schema=_Schema,
                   effort="high", web_search_max_uses=3)  # fmt: skip
    assert res.stop_reason == "end_turn"
    assert len(bound.calls) == 2
    result_msg = bound.calls[1][-1]
    assert isinstance(result_msg, HumanMessage)
    block = result_msg.content[0]
    assert isinstance(block, dict) and block["type"] == "tool_result"
    assert block["tool_use_id"] == "toolu_1" and block["is_error"] is True
