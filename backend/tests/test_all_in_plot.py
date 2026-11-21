# ruff: noqa: F811, E501
"""@spec: 003-campaign-engine (the all-in plot: nothing left at stake)"""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import campaign_state, play_to_decide
from test_campaign_api import COMMIT, _scripted_agents, enron, new_player, start  # noqa: F401
from test_scene_allows_moves import act, open_scene, types

from financequest.agents.campaign import fake
from financequest.campaign import ledger, service
from financequest.db.models_campaign import CampaignRun, Trade
from financequest.db.session import get_engine

ALL_IN = "I invest all of my coins because the cash flow looks fine to me"


@pytest.fixture(autouse=True)
def _clean_offers() -> Iterator[None]:
    fake.clear_offers()
    yield
    fake.clear_offers()


def setup(client: TestClient, beat: str = "story") -> tuple[dict[str, str], str]:
    h = new_player(client)
    cid, _ = start(client, h)
    open_scene(h, cid, beat)
    return h, cid


def trades(cid: str) -> list[Trade]:
    with Session(get_engine()) as db:
        return service.trades_of(db, uuid.UUID(cid))


def ledger_final(cid: str) -> ledger.LedgerResult:
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None
        pack = service.pack_of(db, run)
        return service.ledger_result(run, pack, service.trades_of(db, run.id))


# ---- the engine: a loan in the result maths -------------------------------------------------
def test_ledger_result_subtracts_the_repayment_exactly() -> None:
    pos = ledger.Position(Decimal("500"), Decimal("20"))  # 500 borrowed, 20 shares held
    r = ledger.result(Decimal(1000), pos, Decimal("10"), Decimal(500), Decimal("550.00"))
    assert r.cash == Decimal("500.00") and r.value_now == Decimal("200.00")
    assert r.final == Decimal("150.00")  # 500 + 200 - 550
    assert r.pnl == Decimal("-850.00") and r.invested == Decimal("1000.00")
    plain = ledger.result(Decimal(1000), ledger.Position(Decimal("500"), Decimal("20")), Decimal("10"))
    assert plain.final == Decimal("700.00") and plain.invested == Decimal("500.00")


# ---- all in early: a buyback offer ----------------------------------------------------------
def test_all_in_early_gets_a_buyback_offer_and_accepting_sells_at_the_board_price(
    client: TestClient, enron: str
) -> None:
    h, cid = setup(client)
    done = act(client, h, cid, ALL_IN)
    assert done["all_in"] is True and done["fast_forward"] is False
    offer = done["offer"]
    assert offer["kind"] == "buyback" and offer["by"]["name"] and offer["by"]["role"] == "Guild broker"
    assert offer["terms"]["price"] == "today's board price"
    st = campaign_state(client, h, cid)
    assert st["market_scene"]["beat"] == "offer" and st["offer"]["kind"] == "buyback"
    assert st["all_in"] is True and st["phase"] == "play"
    assert st["purse"]["cash_eur"] == 0 and offer["terms"]["max_eur"] == st["purse"]["position_eur"]
    held = st["purse"]["position_eur"]
    assert "all_in_offer" in types(cid)

    done = act(client, h, cid, "sell half")
    st = campaign_state(client, h, cid)
    assert done["offer"] is None and st["offer"] is None and st["market_scene"] is None
    assert st["purse"]["cash_eur"] == pytest.approx(held / 2, abs=0.01)
    assert st["purse"]["total_eur"] == pytest.approx(held, abs=0.01)  # at the board price: no gain
    sold = trades(cid)[-1]
    assert (sold.action, sold.beat) == ("sell", "offer") and sold.amount_cents == round(held * 50)
    assert st["all_in"] is False and st["phase"] == "play"


def test_the_offer_is_made_once_per_campaign(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    act(client, h, cid, ALL_IN)
    act(client, h, cid, "sell a quarter of it")  # takes the offer: the plot goes on
    open_scene(h, cid, "story")
    done = act(client, h, cid, "I put everything back in: invest all")
    assert done["offer"] is None and done["fast_forward"] is False  # no second offer, no fast-forward
    assert types(cid).count("all_in_offer") == 1


# ---- a loan offer -----------------------------------------------------------------------------
def test_loan_offer_accepted_adds_cash_and_the_outcome_subtracts_the_repayment(
    client: TestClient, enron: str
) -> None:
    fake.script_offer("loan")
    h, cid = setup(client)
    done = act(client, h, cid, ALL_IN)
    offer = done["offer"]
    assert offer["kind"] == "loan" and offer["by"]["role"] == "Moneylender"
    assert offer["terms"] == {"principal_eur": 500.0, "interest_pct": 10, "repay_eur": 550.0,
                              "due": "at the end of the horizon"}  # 50% of 1000, 10% flat

    done = act(client, h, cid, "I take the loan")
    purse = done["purse"]
    assert purse["cash_eur"] == 500 and purse["loan"]["repay_eur"] == 550
    assert purse["loan"]["label"] == (
        f"Loan from {offer['by']['name']}: +€500 now, repay €550 at the end")
    assert purse["net_eur"] == pytest.approx(purse["total_eur"] - 550, abs=0.01)
    loan_row = trades(cid)[-1]
    assert (loan_row.action, loan_row.amount_cents) == ("loan", 50000)
    assert campaign_state(client, h, cid)["offer"] is None

    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    r = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    assert r.status_code == 200, r.text
    b = r.json()["breakdown"]
    assert b["loan_repay_eur"] == 550 and b["loan"]["principal_eur"] == 500
    assert b["final_value"] == pytest.approx(b["cash_kept"] + b["value_now"] - 550, abs=0.005)
    mine = ledger_final(cid)
    assert (mine.final, mine.cash, mine.value_now) == (
        Decimal(str(b["final_value"])).quantize(Decimal("0.01")), Decimal(str(b["cash_kept"])).quantize(
            Decimal("0.01")), Decimal(str(b["value_now"])).quantize(Decimal("0.01")))  # fmt: skip
    assert b["pl_eur"] == pytest.approx(b["final_value"] - b["starting_budget"], abs=0.005)


# ---- declining, ignoring, and the last checkpoint: the plot moves to its finish --------------
def assert_fast_forwarded(client: TestClient, h: dict[str, str], cid: str, done: dict[str, Any]) -> None:
    assert done["fast_forward"] is True and done["phase"] == "timeskip"
    st = campaign_state(client, h, cid)
    assert st["phase"] == "timeskip" and st["market_scene"] is None
    assert "lock" in types(cid) and "time_skip" in types(cid)
    rv = client.get(f"/campaigns/{cid}/reveal", headers=h)
    assert rv.status_code == 200, rv.text
    b = rv.json()["breakdown"]
    mine = ledger_final(cid)
    assert b["final_value"] == float(mine.final) and b["pl_eur"] == float(mine.pnl)
    assert b["cash_kept"] == float(mine.cash) and b["value_now"] == float(mine.value_now)
    assert client.get(f"/campaigns/{cid}", headers=h).json()["phase"] == "reveal"


def test_declining_the_offer_fast_forwards_to_the_outcome(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    act(client, h, cid, ALL_IN)
    done = act(client, h, cid, "No, I decline")
    assert_fast_forwarded(client, h, cid, done)
    from financequest.db.models import Decision

    with Session(get_engine()) as db:
        dec = db.exec(select(Decision).where(Decision.campaign_id == uuid.UUID(cid))).one()
        assert dec.reasoning == "the cash flow looks fine to me" and dec.action == "invest"
    assert types(cid).count("all_in_offer") == 1  # never looped


def test_doing_something_else_twice_fast_forwards(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    act(client, h, cid, ALL_IN)
    first = act(client, h, cid, "Let's head to the library")
    assert first["fast_forward"] is False
    st = campaign_state(client, h, cid)
    assert st["offer"] is not None and st["market_scene"]["beat"] == "offer"  # still open, once
    second = act(client, h, cid, "I would rather wander to the market now")
    assert_fast_forwarded(client, h, cid, second)
    assert types(cid).count("offer_ignored") == 1


def test_all_in_at_the_last_checkpoint_fast_forwards_without_an_offer(
    client: TestClient, enron: str
) -> None:
    h, cid = setup(client, "news")
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None
        run.news_shown = True  # the last checkpoint is already revealed
        db.add(run)
        db.commit()
    done = act(client, h, cid, ALL_IN)
    assert done["offer"] is None
    assert_fast_forwarded(client, h, cid, done)
    assert "all_in_offer" not in types(cid)


def test_pulling_everything_out_and_saying_done_fast_forwards(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    act(client, h, cid, "buy 20 because the cash flow keeps falling")
    open_scene(h, cid, "story")
    done = act(client, h, cid, "I sell all of it, I'm done")
    assert_fast_forwarded(client, h, cid, done)
    assert "all_in_offer" not in types(cid)


def test_a_normal_decision_is_not_all_in(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    done = act(client, h, cid, "I invest 400 coins: the cash flow worries me")
    assert done["all_in"] is False and done["offer"] is None and done["fast_forward"] is False
    st = campaign_state(client, h, cid)
    assert st["all_in"] is False and st["market_scene"] is None and st["purse"]["loan"] is None
    assert "all_in_offer" not in types(cid)
