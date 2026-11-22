# ruff: noqa: F811, E501
"""@spec: 003-campaign-engine (the supporting hand: help for a player in trouble)"""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from sse_helpers import campaign_state, play_to_decide, post_sse
from test_all_in_plot import ALL_IN, ledger_final, trades
from test_campaign_api import COMMIT, enron, new_player, start  # noqa: F401
from test_edu_moments import record
from test_scene_allows_moves import act, open_scene, types

from financequest.agents.campaign import fake
from financequest.campaign import edu, rules, service
from financequest.campaign.events import campaign_events
from financequest.db.models_campaign import CampaignRun, Trade
from financequest.db.session import get_engine

HOLD = "I hold what I have because I want to see more first"
BUY_HALF = "I invest half of my coins because the cash flow looks fine to me"
SELL_ALL = "I sell all of it because the price keeps falling"
DAY_HIGH, DAY_LOW = 13, 61  # board closes 42.93 and 26.41: a drop of more than 30%


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    fake.clear_offers()
    fake.clear_damage()
    yield
    fake.clear_offers()
    fake.clear_damage()


def fresh(client: TestClient) -> tuple[dict[str, str], str]:
    h = new_player(client)
    cid, _ = start(client, h)
    return h, cid


def with_run(cid: str, fn: Any) -> Any:
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None
        pack = service.pack_of(db, run)
        out = fn(db, run, pack)
        db.add(run)
        db.commit()
        return out


def hurt(cid: str, hp: int) -> None:
    """Real damage through the engine (at most 10 HP at a time)."""

    def go(db: Session, run: CampaignRun, pack: Any) -> None:
        left = hp
        while left > 0:
            service.apply_hp_loss(db, run, pack, min(10, left), "a costly slip")
            left -= 10

    with_run(cid, go)


def set_day(cid: str, day: int) -> None:
    with_run(cid, lambda db, run, pack: setattr(run, "clock_day", day))


def turn(client: TestClient, h: dict[str, str], cid: str, text: str = HOLD) -> dict[str, Any]:
    """A decision in an open story scene: the moment the engine looks at the player's situation."""
    open_scene(h, cid, "story")
    return act(client, h, cid, text)


def state(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    return campaign_state(client, h, cid)


def assert_offer(done: dict[str, Any], kind: str, reason: str) -> dict[str, Any]:
    offer = done["offer"]
    assert offer["kind"] == kind and offer["reason"] == reason, offer
    assert offer["by"]["name"] and offer["by"]["role"]
    assert offer["kind"] in rules.SUPPORT_KINDS and offer["reason"] in rules.SUPPORT_REASONS
    card = done["offer_card"]
    assert card["kind"] == "offer" and card["offer_kind"] == kind and card["terms"] == offer["terms"]
    return dict(offer)


# ---- each trigger opens exactly one supporting hand --------------------------------------------
def test_low_hp_offers_a_patron_grant_that_restores_hp_and_budget_with_exact_maths(
    client: TestClient, enron: str
) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)  # 35 HP left: at or under 40% of 100
    assert state(client, h, cid)["offer"] is None  # nothing happens before the engine looks
    done = turn(client, h, cid)
    offer = assert_offer(done, "patron_grant", "low_hp")
    assert offer["terms"] == {"hp": 20, "gift_eur": 200.0, "repay": "none"}  # 20% of the starting HP
    assert "bouncing_back" in [m["concept_key"] for m in done["edu_new"]]
    st = state(client, h, cid)
    assert st["market_scene"]["beat"] == "offer" and st["offer"]["reason"] == "low_hp"
    assert st["support_used"] is False and types(cid).count("support_offer") == 1

    done = act(client, h, cid, "I accept the help, thank you")
    assert done["fast_forward"] is False and done["offer"] is None
    st = state(client, h, cid)
    assert st["hp"] == 55 and st["hp_eur"] == 550 and st["support_used"] is True
    assert st["purse"]["cash_eur"] == 550 and st["purse"]["grant"]["amount_eur"] == 200
    assert st["purse"]["grant"]["label"] == "Patron's help: +200 gp, no repayment"
    row = trades(cid)[-1]
    assert (row.action, row.beat, row.amount_cents, row.text) == ("grant", "support", 20000, "Patron's help: +200 gp")
    assert done["card"]["grant"]["amount_eur"] == 200 and "support_taken" in types(cid)

    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    b = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h).json()["breakdown"]
    assert b["patron_grant_eur"] == 200 and b["starting_budget"] == 550
    # the decision-day scene put 400 in at the same board price as in the unhurt game (607.45, -392.55):
    # the gift restores the purse and is not a profit
    assert (b["cash_kept"], b["invested"], b["final_value"], b["pl_eur"]) == (150.0, 400.0, 157.45, -392.55)
    mine = ledger_final(cid)
    assert (mine.final, mine.pnl, mine.budget) == (Decimal("157.45"), Decimal("-392.55"), Decimal("550.00"))
    assert "loan_repay_eur" not in b


def test_position_down_offers_a_rescue_buyback_at_the_board_price(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    turn(client, h, cid, BUY_HALF)
    assert state(client, h, cid)["offer"] is None and state(client, h, cid)["purse"]["position_eur"] == 500
    set_day(cid, DAY_LOW)  # the coins are now worth about 38% less than was paid
    done = turn(client, h, cid)
    offer = assert_offer(done, "rescue_buyback", "position_down")
    held = state(client, h, cid)["purse"]["position_eur"]
    assert offer["terms"]["max_eur"] == held and offer["terms"]["price"] == "today's board price" and held < 350

    done = act(client, h, cid, "sell half")
    st = state(client, h, cid)
    assert st["offer"] is None and st["support_used"] is True
    assert st["purse"]["cash_eur"] == pytest.approx(500 + held / 2, abs=0.01)
    sold = trades(cid)[-1]
    assert (sold.action, sold.beat) == ("sell", "offer") and abs(sold.amount_cents - held * 50) <= 1
    assert done["fast_forward"] is False


def test_a_sale_at_a_loss_offers_a_loan_on_the_usual_terms(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    turn(client, h, cid, BUY_HALF)
    set_day(cid, DAY_LOW)
    done = turn(client, h, cid, SELL_ALL)  # sold for far less than 25% under cost
    offer = assert_offer(done, "loan", "loss_sale")
    assert offer["terms"] == {"principal_eur": 500.0, "interest_pct": 10, "repay_eur": 550.0,
                              "due": "at the end of the horizon"}  # fmt: skip
    done = act(client, h, cid, "I take the loan")
    assert done["card"]["loan"]["principal_eur"] == 500 and state(client, h, cid)["support_used"] is True
    assert trades(cid)[-1].action == "loan"


def test_hp_reaching_zero_is_broke_and_gets_a_patron_grant(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    hurt(cid, 100)
    assert state(client, h, cid)["hp"] == 0
    offer = assert_offer(turn(client, h, cid), "patron_grant", "broke")
    assert offer["terms"]["gift_eur"] == 200.0
    act(client, h, cid, "I accept")
    st = state(client, h, cid)
    assert st["hp"] == 20 and st["purse"]["cash_eur"] == 200


def test_just_above_the_thresholds_is_not_trouble(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    hurt(cid, 55)  # 45 HP: above 40%
    assert turn(client, h, cid)["offer"] is None
    assert "support_offer" not in types(cid)


# ---- once per campaign, never beside another offer -------------------------------------------------
def test_declining_continues_the_story_and_the_hand_is_not_offered_twice(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)
    turn(client, h, cid)
    done = act(client, h, cid, "No, thank you")
    st = state(client, h, cid)
    assert done["fast_forward"] is False and done["offer"] is None and done.get("phase", "play") == "play"
    assert st["phase"] == "play" and st["market_scene"] is None and st["offer"] is None
    assert st["support_used"] is False and "support_declined" in types(cid) and "lock" not in types(cid)
    hurt(cid, 10)  # still in trouble
    assert turn(client, h, cid)["offer"] is None
    assert types(cid).count("support_offer") == 1


def test_ignoring_the_hand_twice_lets_the_story_go_on_without_a_fast_forward(
    client: TestClient, enron: str
) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)
    turn(client, h, cid)
    assert act(client, h, cid, "Let's head to the library")["fast_forward"] is False
    assert state(client, h, cid)["offer"] is not None
    second = act(client, h, cid, "I would rather wander to the market now")
    st = state(client, h, cid)
    assert second["fast_forward"] is False and st["offer"] is None and st["phase"] == "play"
    assert types(cid).count("offer_ignored") == 1 and "support_declined" in types(cid)


def test_no_second_offer_while_an_all_in_offer_is_open_and_one_after_it_was_used(
    client: TestClient, enron: str
) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)
    done = turn(client, h, cid, ALL_IN)  # in trouble AND all in: the all-in offer wins the moment
    assert done["offer"]["kind"] == "buyback" and "reason" not in done["offer"]
    assert "support_offer" not in types(cid) and types(cid).count("all_in_offer") == 1
    done = act(client, h, cid, "sell half")  # they took the all-in offer: the plot goes on
    assert done["offer"] is None and done["reasoning_prompt"]  # the "why?" question comes first
    done = act(client, h, cid, "because the price keeps falling")
    offer = assert_offer(done, "patron_grant", "low_hp")  # the hand can still come, once
    assert offer["terms"]["hp"] == 20
    assert types(cid).count("all_in_offer") == 1 and types(cid).count("support_offer") == 1


def test_an_open_support_offer_blocks_the_all_in_offer_and_the_other_way_round(
    client: TestClient, enron: str
) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)
    turn(client, h, cid)
    assert state(client, h, cid)["offer"]["reason"] == "low_hp"
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None
        assert service.support_reason(db, run, service.pack_of(db, run)) is None  # one open offer at a time


# ---- loans: never more than half of the starting budget in total -----------------------------------
def test_a_second_loan_is_smaller_and_the_total_never_passes_half_the_budget(
    client: TestClient, enron: str
) -> None:
    fake.script_offer("loan")
    fake.script_support("loan")
    h, cid = fresh(client)
    done = turn(client, h, cid, ALL_IN)
    assert done["offer"]["kind"] == "loan" and done["offer"]["terms"]["principal_eur"] == 500.0
    done = act(client, h, cid, "I borrow 300")
    assert done["card"]["loan"]["principal_eur"] == 300

    hurt(cid, 65)
    done = turn(client, h, cid)
    offer = assert_offer(done, "loan", "low_hp")
    assert offer["terms"]["principal_eur"] == 200.0 and offer["terms"]["repay_eur"] == 220.0
    act(client, h, cid, "I take the loan")
    st = state(client, h, cid)
    assert st["purse"]["loan"]["principal_eur"] == 500 and st["purse"]["loan"]["repay_eur"] == 550
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None
        assert service.loan_capacity(run, service.trades_of(db, run.id)) == 0
        assert "loan" not in service.offer_facts(db, run, service.pack_of(db, run))  # nothing left to lend
    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    b = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h).json()["breakdown"]
    assert b["loan_repay_eur"] == 550 and b["loan"]["principal_eur"] == 500
    assert b["final_value"] == pytest.approx(b["cash_kept"] + b["value_now"] - 550, abs=0.005)
    assert b["pl_eur"] == pytest.approx(b["final_value"] - b["starting_budget"], abs=0.005)


def test_a_full_loan_leaves_no_loan_to_offer_but_another_kind(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    with_run(cid, lambda db, run, pack: db.add(Trade(
        campaign_id=run.id, seq=1, beat="offer", story_day=run.clock_day, text="Loan from Ismene Dray",
        action="loan", amount_cents=50000, shares="0", price="550", cash_after_cents=150000, shares_after="0")))
    hurt(cid, 65)
    done = turn(client, h, cid)
    assert done["offer"]["kind"] != "loan"


# ---- the second look ---------------------------------------------------------------------------------
def test_second_look_reveals_an_unfound_unlocked_clue_without_spending_focus(
    client: TestClient, enron: str
) -> None:
    fake.script_support("second_look")
    h, cid = fresh(client)
    hurt(cid, 65)
    before = state(client, h, cid)
    done = turn(client, h, cid)
    offer = assert_offer(done, "second_look", "low_hp")
    assert offer["terms"] == {"gives": "one clue", "cost": "free"}
    done = act(client, h, cid, "Yes, show me")
    after = state(client, h, cid)
    assert len(after["clues"]) == len(before["clues"]) + 1 and len(done["clue_ids_given"]) == 1
    assert after["focus_left"] == before["focus_left"] and after["support_used"] is True
    assert after["clues"][-1]["clue_id"] == done["clue_ids_given"][0]


def test_second_look_restores_one_focus_when_no_clue_is_left(client: TestClient, enron: str) -> None:
    fake.script_support("second_look")
    h, cid = fresh(client)

    def drain(db: Session, run: CampaignRun, pack: Any) -> None:
        from financequest.campaign.view import gated_view, visible_evidence

        for e in visible_evidence(pack, gated_view(run)):
            service.grant_clue(db, run, pack, e.id, "location")
        run.focus_left = 1

    with_run(cid, drain)
    hurt(cid, 65)
    offer = assert_offer(turn(client, h, cid), "second_look", "low_hp")
    assert offer["terms"] == {"gives": "one Focus", "cost": "free"}
    done = act(client, h, cid, "Yes, please")
    assert state(client, h, cid)["focus_left"] == 2 and done["clue_ids_given"] == []


# ---- a locked campaign never gets an offer -------------------------------------------------------------
def test_locked_campaigns_never_get_a_supporting_hand(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    assert client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h).status_code == 200
    hurt(cid, 100)
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None and run.phase == "timeskip"
        assert service.support_reason(db, run, service.pack_of(db, run)) is None
    assert "support_offer" not in types(cid)


# ---- the normal path stays exactly as it was ---------------------------------------------------------------
def test_normal_play_has_no_offer_and_the_contract_keys_are_unchanged(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    done = turn(client, h, cid, BUY_HALF)
    assert done["offer"] is None and "offer_card" not in done
    st = state(client, h, cid)
    assert st["support_used"] is False and "grant" not in st["purse"]
    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    b = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h).json()["breakdown"]
    assert set(b) == {"starting_budget", "cash_kept", "invested", "value_now", "fees", "final_value",
                      "pl_eur", "pl_pct"}  # fmt: skip
    assert "support_offer" not in types(cid)


# ---- the supportive closing line --------------------------------------------------------------------------
def big_loss_debrief(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    done = turn(client, h, cid, ALL_IN)
    assert done["offer"]["kind"] == "buyback"
    assert act(client, h, cid, "No, I decline")["fast_forward"] is True
    assert client.get(f"/campaigns/{cid}/reveal", headers=h).status_code == 200
    return post_sse(client, f"/campaigns/{cid}/debrief", h)[1]


def test_a_big_loss_without_support_gets_a_supportive_closing_line(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    deb = big_loss_debrief(client, h, cid)
    assert ledger_final(cid).final <= Decimal("600")
    assert deb["closing"] and "loss" in deb["closing"] and deb["closing"] in deb["text"]
    assert deb["text"].index(deb["closing"]) < deb["text"].index(deb["reflection_question"])


def test_no_closing_line_when_a_supporting_hand_was_taken(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)  # in trouble: take the patron's hand, then lose big anyway
    turn(client, h, cid)
    act(client, h, cid, "I accept the help")
    assert "support_taken" in types(cid)
    deb = big_loss_debrief(client, h, cid)
    assert "closing" not in deb


# ---- edu: bouncing_back ---------------------------------------------------------------------------------
def test_bouncing_back_is_detected_and_respects_the_three_pending_cap(client: TestClient, enron: str) -> None:
    assert [c.concept_key for c in edu.detect(edu.EduFacts(support={"kind": "loan", "reason": "low_hp", "amount": 500}))] == ["bouncing_back"]
    assert edu.CATALOG["bouncing_back"] == "Bouncing back from a loss"
    h, cid = fresh(client)
    new = record(cid, h, news=True, trade={"action": "buy", "amount": 5}, loan_offered=True)
    assert len(new) == 3  # three moments are waiting
    assert record(cid, h, support={"kind": "patron_grant", "reason": "low_hp", "amount": 200}) == []
    with Session(get_engine()) as db:
        skipped = [e.payload for e in campaign_events(db, uuid.UUID(cid)) if e.type == "edu_skipped"]
    assert any(p["concept_key"] == "bouncing_back" for p in skipped)


def test_the_bouncing_back_lesson_is_prepared_and_neutral(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    hurt(cid, 65)
    done = turn(client, h, cid)
    moment = next(m for m in done["edu_new"] if m["concept_key"] == "bouncing_back")
    r = client.post(f"/campaigns/{cid}/edu/{moment['id']}/lesson", headers=h)
    assert r.status_code == 200, r.text
    les = r.json()
    assert les["title"] == "Bouncing back from a loss" and "200 gp" in les["what_happened"]
    assert len(les["check"]["options"]) == 3


def test_a_deep_fall_from_the_best_while_underwater_counts_as_trouble(client: TestClient, enron: str) -> None:
    """Bought early, rode a peak, now below cost but less than 30% under it: still in trouble."""
    import dataclasses

    from financequest.campaign.pack import Row

    h, cid = fresh(client)
    turn(client, h, cid, BUY_HALF)
    buy = trades(cid)[-1]
    paid = Decimal(buy.amount_cents) / 100 / Decimal(buy.shares)
    d = buy.story_day

    def row(day: int, close: Decimal) -> Row:
        return Row(day, f"d{day}", close, close, close, close)

    def check(db: Session, run: CampaignRun, pack: Any) -> list[str | None]:
        out = []
        for later in (Decimal("0.95"), Decimal("1.1")):  # under cost / above cost
            rows = (row(d, paid), row(d + 1, paid * Decimal("1.5")), row(d + 2, paid * later))
            run.clock_day = d + 2
            out.append(service.support_reason(db, run, dataclasses.replace(pack, rows=rows)))
        db.rollback()
        return out

    assert with_run(cid, check) == ["position_down", None]


def test_a_market_loss_is_met_after_a_decision_not_on_a_walk(client: TestClient, enron: str) -> None:
    h, cid = fresh(client)
    turn(client, h, cid, BUY_HALF)
    set_day(cid, DAY_LOW)  # the coins are now worth about 38% less than was paid
    st = state(client, h, cid)
    lib = next(x["id"] for x in st["locations"] if x["key"] == "library")
    post_sse(client, f"/campaigns/{cid}/move", h, {"location_id": lib})
    assert state(client, h, cid)["offer"] is None  # arriving somewhere is not the moment
    done = turn(client, h, cid)  # holding in a scene is
    assert_offer(done, "rescue_buyback", "position_down")
