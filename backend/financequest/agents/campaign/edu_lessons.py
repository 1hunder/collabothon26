"""Prepared lessons: one per educational concept. They are the fallback when a generated lesson
fails the guards, and they are what FAKE_LLM=1 returns. Every figure in ``example`` and ``check``
is a small round number about an imaginary case; every figure about the player's own game comes
from the moment's snapshot (engine facts, whole numbers, gold pieces)."""

from __future__ import annotations

from typing import Any

from financequest.campaign.edu import TERMS


def _n(d: dict[str, Any] | None, key: str, default: int = 0) -> int:
    try:
        return int((d or {}).get(key, default))
    except (TypeError, ValueError):
        return default


def _mix(right: str, wrong: list[str], salt: str) -> tuple[list[str], int]:
    """Three options with the right one at a position that varies by concept (not always first)."""
    at = sum(map(ord, salt)) % 3
    opts = list(wrong)
    opts.insert(at, right)
    return opts, at


def _lesson(what: str, idea: str, example: str, takeaway: str, q: str, right: str,
            wrong: list[str], salt: str) -> dict[str, Any]:
    options, idx = _mix(right, wrong, salt)
    return {"what_happened": what, "idea": idea, "example": example, "takeaway": takeaway,
            "check": {"question": q, "options": options, "answer_index": idx}}  # fmt: skip


# term -> (idea, example, takeaway, question, right answer, two wrong answers)
TERM_LESSONS: dict[str, tuple[str, str, str, str, str, list[str]]] = {
    "revenue": (
        "Revenue is the money a company bills for what it sold. It is the top line of its books. "
        "Costs have not been taken out yet, so revenue is not profit.",
        "Imagine a baker sells 100 loaves for 2 gp each. Her revenue is 200 gp. Flour and wages still come out of that.",
        "Revenue is what comes in before costs.", "A baker sells 100 loaves at 2 gp each. What is her revenue?",
        "200 gp", ["100 gp", "2 gp"]),
    "profit": (
        "Profit is what is left of revenue after all costs are taken out. A company can have big sales and "
        "still make little profit if its costs are also big.",
        "Imagine a shop earns 100 gp from sales and spends 80 gp on costs. It keeps 20 gp as profit.",
        "Profit equals revenue minus costs.", "A shop earns 100 gp and spends 80 gp on costs. What is its profit?",
        "20 gp", ["80 gp", "180 gp"]),
    "earnings": (
        "Earnings is another word for profit: what is left after costs, on paper. It is an accounting figure. "
        "It tells you little about how much coin is really in the vault.",
        "Imagine a guild books earnings of 30 gp, but its customers have paid only 10 gp so far. The vault holds far less than the books suggest.",
        "Earnings are profit on paper, not coin in the vault.", "What do earnings measure?",
        "Profit on paper after costs", ["Coin in the vault", "The share price"]),
    "cash flow": (
        "Cash flow follows the coin that really moves in and out of a company. A company can show a profit "
        "and still run short of cash, for example when customers pay late.",
        "Imagine a shop sells goods worth 100 gp on credit. Its books show a profit of 20 gp, but no coin has arrived yet.",
        "Cash flow is the real coin; profit is the paper figure.", "What does cash flow follow?",
        "Coin that really moves in and out", ["Profit on paper", "The share price"]),
    "debt": (
        "Debt is money a company owes and must repay, usually with interest. Debt is not bad in itself. "
        "But large debt next to thin cash leaves little room for bad news.",
        "Imagine a guild owes 80 gp and holds only 10 gp in cash. A single bad month could leave it unable to repay.",
        "Debt must be repaid, so compare it with cash.", "A guild owes 80 gp and holds 10 gp in cash. Which is true?",
        "It owes much more than it holds", ["It holds more than it owes", "It owes nothing"]),
    "equity": (
        "Equity is what would be left for the owners if everything were sold and all debts repaid. "
        "It is the owners' part of the company.",
        "Imagine a guild owns goods worth 100 gp and owes 80 gp. The owners' equity is 20 gp.",
        "Equity is what the owners keep after the debts are paid.",
        "A guild owns goods worth 100 gp and owes 80 gp. What is the equity?",
        "20 gp", ["80 gp", "180 gp"]),
    "dividend": (
        "A dividend is a share of a company's profit paid out to its owners in coin. A company may pay "
        "one, pay none, or cut it. The company decides, and nothing is promised.",
        "Imagine a company pays 2 gp for each share you own. With 10 shares, you receive 20 gp.",
        "A dividend is profit paid out to owners.", "You own 10 shares and each pays 2 gp. How much do you receive?",
        "20 gp", ["10 gp", "2 gp"]),
    "share": (
        "A share is a small slice of ownership in a company. If you hold shares, you own a part of it. "
        "The share price goes up and down with what people expect.",
        "Imagine a company is split into 100 shares. If you hold 10 of them, you own one tenth of it.",
        "A share is a small slice of a company.", "A company has 100 shares and you hold 10. What part do you own?",
        "One tenth", ["One half", "All of it"]),
    "price": (
        "A price is what a buyer and a seller agree on today. It changes when people's expectations change. "
        "A price shows what people think, not whether a company is truly good.",
        "Imagine 10 people want one rare apple and only 5 apples exist. The price climbs until some give up.",
        "A price shows what people expect right now.", "More buyers than sellers. What does the price usually do?",
        "It rises", ["It falls", "It stays the same"]),
    "risk": (
        "Risk is the chance that things turn out worse than you hoped, including losing coins. More possible "
        "gain usually comes with more risk. You cannot remove risk, but you can understand it.",
        "Imagine you could lose 10 gp or gain 10 gp on a coin flip. The risk is the 10 gp you might lose.",
        "Risk is the chance of a worse result than you hoped.", "What is risk?",
        "The chance of a worse result", ["A sure gain", "A kind of profit"]),
    "diversification": (
        "Diversification means spreading your coins over several things, so one bad surprise cannot sink "
        "everything. It does not remove risk. It stops one problem from hurting you all at once.",
        "Imagine you carry 10 eggs. In one basket, a drop breaks all 10. In two baskets of 5, a drop breaks at most 5.",
        "Spreading coins limits the damage of one surprise.",
        "You split 10 eggs into two baskets of 5 and drop one. How many break at most?",
        "5", ["10", "0"]),
    "margin": (
        "A margin compares profit with sales: how much of each coin of sales is left after costs. "
        "A shrinking margin means costs are growing faster than sales.",
        "Imagine a shop sells 100 gp and keeps 20 gp as profit. Its margin is 20 percent.",
        "A margin is the part of sales that stays as profit.", "A shop sells 100 gp and keeps 20 gp. What is its margin?",
        "20 percent", ["80 percent", "2 percent"]),
    "ledger": (
        "A ledger is the formal record of what a company earned, owed and owned. Each ledger shows one side "
        "of the story. Reading two of them side by side shows what each one leaves out.",
        "Imagine one ledger shows a profit of 20 gp and another shows cash falling by 10 gp. Together they warn you to ask why.",
        "Read two ledgers side by side.", "Why read two ledgers together?",
        "Each one leaves something out", ["They always agree", "One is enough"]),
}


def prepared_lesson(concept_key: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The prepared lesson for a concept, filled with the moment's own figures when it has them."""
    gp = facts.get("gp") or {}
    day = f" on {facts['day']}" if facts.get("day") else ""
    if concept_key == "concept_question":
        term = str(facts.get("term") or "cash flow")
        if term not in TERM_LESSONS:
            term = "cash flow"
        idea, example, take, q, right, wrong = TERM_LESSONS[term]
        return _lesson(f"You asked what {term} means{day}. Here it is in plain words.",
                       idea, example, take, q, right, wrong, concept_key + term)
    if concept_key == "news_reaction":
        return _lesson(
            f"Breaking news reached the square{day}. You now have to decide what it changes for you.",
            "News is new information. Prices often move fast when it arrives, because many people react at "
            "once. Ask three things: what exactly happened, is it a fact or a rumour, and does it change how "
            "the company earns or spends coin?",
            "Imagine a baker hears that a rival shop will open next door. Before changing anything, she checks "
            "if it is true, how many customers it could take, and when it opens.",
            "Check the facts before you react to news.", "What is a good first step after surprising news?",
            "Check whether it is a fact or a rumour",
            ["Do the opposite of everyone else", "Wait for the price to tell you"], concept_key)
    if concept_key == "first_trade":
        t = facts.get("trade") or {}
        verb = "bought" if t.get("action") == "buy" else "sold"
        return _lesson(
            f"You made your first trade{day}: you {verb} coins for {_n(t, 'amount')} gp. Your purse now holds "
            f"{_n(gp, 'cash')} gp in cash and {_n(gp, 'position')} gp in coins of the company.",
            "When you buy shares, your cash turns into a slice of the company. The slice rises and falls with "
            "the price. Your cash does not. So what you own is your cash plus your shares, counted at today's price.",
            "Imagine you have 100 gp and spend 40 gp on shares. You hold 60 gp in cash and 40 gp in shares. If the shares are worth 50 gp tomorrow, you own 110 gp.",
            "You own your cash plus your shares at today's price.",
            "You hold 60 gp in cash and 40 gp in shares. What do you own in total today?",
            "100 gp", ["60 gp", "40 gp"], concept_key)
    if concept_key == "cash_vs_profit":
        return _lesson(
            f"You looked at records that show earnings and cash{day}. They can tell two different stories.",
            "Profit, or earnings, is what is left after costs are counted on paper. Cash is the coin that really "
            "arrived. A company can show a profit and still run short of cash, for example when customers pay late.",
            "Imagine a shop sells goods worth 100 gp on credit. Its books show a profit of 20 gp. But no customer has paid yet, so its cash has not grown.",
            "Earnings are paper. Cash is real coin. Check both.",
            "A shop shows a profit but its customers have not paid yet. What has not grown?",
            "Its cash", ["Its earnings on paper", "Its sales"], concept_key)
    if concept_key == "debt_and_equity":
        loan = facts.get("loan")
        what = (f"A moneylender's offer made you think about debt{day}: {_n(loan, 'principal')} gp now, "
                f"{_n(loan, 'repay')} gp to repay." if loan else
                f"You came across debt figures in the company's records{day}.")
        return _lesson(
            what,
            "Debt is money a company owes and must repay. Equity is what would be left for the owners after "
            "all debts are repaid. A company with big debts and little equity has little room for bad news.",
            "Imagine a guild owns goods worth 100 gp and owes 80 gp. The owners' share, the equity, is only 20 gp.",
            "Equity is what the owners keep after the debts are paid.",
            "A guild owns goods worth 100 gp and owes 80 gp. What is left for the owners?",
            "20 gp", ["80 gp", "180 gp"], concept_key)
    if concept_key == "price_move":
        pr = facts.get("price")
        what = (f"The price board shows the price going from {_n(pr, 'first')} to {_n(pr, 'last')}, "
                f"a change of {abs(_n(pr, 'change_pct'))} percent over the days shown." if pr else
                f"You looked at the price board{day}.")
        return _lesson(
            what,
            "A price moves when more people want to buy than sell, or the other way round. News, results and "
            "rumours change what people expect. A price move shows what people expect, not whether the company is truly good.",
            "Imagine 10 people want one rare apple and only 5 apples exist. The price climbs. If 10 apples appear for 5 buyers, it falls.",
            "Prices follow expectations, so ask what changed.",
            "More people want to buy than sell. What usually happens to the price?",
            "It rises", ["It falls", "It stays the same"], concept_key)
    if concept_key == "concentration":
        return _lesson(
            f"Most of your gold, {_n(facts, 'share_pct', 100)} percent, sits in one company{day}: "
            f"{_n(gp, 'position')} gp of {_n(gp, 'total')} gp.",
            "Putting nearly everything in one company is called concentration. If that company has bad news, your "
            "whole purse suffers. Spreading coins over several companies is called diversification.",
            "Imagine you carry 10 eggs in one basket and drop it. All 10 break. With 5 eggs in each of two baskets, you lose at most 5.",
            "Spreading your coins limits the damage of one bad surprise.",
            "You carry 5 eggs in each of two baskets and drop one. How many break?",
            "5", ["10", "0"], concept_key)
    if concept_key == "bouncing_back":
        sup = facts.get("support") or {}
        kind = sup.get("kind")
        amount = _n(sup, "amount")
        offered = {
            "patron_grant": f"A patron offered you a gift of {amount} gp, with nothing to repay.",
            "loan": f"A moneylender offered you up to {amount} gp now, to be repaid with interest.",
            "rescue_buyback": f"A broker offered to buy part of your coins at today's board price, up to {amount} gp worth.",
            "second_look": "A mentor offered you a free look: a clue, or a moment of rest.",
        }.get(str(kind), "Someone offered you a helping hand.")
        return _lesson(
            f"Things went badly for you{day}. {offered}",
            "Everyone who invests has setbacks. What matters is how you answer one. Take a pause, look at what "
            "actually happened, and separate what you could control from what you could not. Help can come as a "
            "gift, a loan or advice. A gift costs nothing. A loan must be repaid with interest, so it adds a new risk.",
            "Imagine you lose 20 gp on a trade. You could rush a bigger trade to win it back, or you could stop, "
            "write down what you missed, and decide calmly. Rushing to win back a loss often makes it larger.",
            "A loss is a lesson. Pause before you act to win it back.",
            "You just lost 20 gp. What is a calm first step?",
            "Pause and look at what happened", ["Trade bigger to win it back at once", "Ignore it and hope"],
            concept_key)
    if concept_key == "loan_cost":
        loan = facts.get("loan")
        what = (f"A moneylender offered you {_n(loan, 'principal')} gp now, to be repaid with "
                f"{_n(loan, 'repay')} gp later." if loan else f"A moneylender offered you a loan{day}.")
        return _lesson(
            what,
            "A loan gives you coin now, but you repay more later. The extra is called interest. It is the price "
            "of borrowing. A loan is only worth it if what you do with the coin earns more than the interest.",
            "Imagine you borrow 100 gp and must repay 110 gp. The interest is 10 gp. If you earn only 5 gp with the coin, you end up 5 gp worse off.",
            "Borrowed coin always costs interest, so count it first.",
            "You borrow 100 gp and repay 110 gp. How much was the interest?",
            "10 gp", ["100 gp", "110 gp"], concept_key)
    if concept_key == "thin_reasoning":
        return _lesson(
            f"You made a choice{day} without giving much reasoning for it.",
            "A good decision has reasons you can point to: a fact you read, a number you compared, a risk you "
            "weighed. Writing them down helps you learn later, whether the choice worked out or not.",
            "Imagine two friends pick a team. One says it feels right. The other says the team won 8 of its last 10 games. Only the second can learn from the result.",
            "Name the evidence behind each choice.", "Which is the stronger reason for a choice?",
            "A fact you checked", ["A feeling", "What a friend did"], concept_key)
    if concept_key == "luck_vs_skill":
        roll, lost = facts.get("roll") or {}, _n(facts, "hp_loss")
        title = roll.get("title") or "a risky move"
        if lost:
            what = f"You lost {lost} HP, worth {lost * 10} gp, in a moment that was partly down to chance."
        elif roll.get("result") == "success":
            what = f"Chance was kind to you{day}, in the attempt called {title}."
        else:
            what = f"Chance went against you{day}, in the attempt called {title}."
        return _lesson(
            what,
            "Some results come from luck and some from judgement. You control your process: what you check and "
            "what you risk. You do not control chance. A good choice can end badly, and a poor one can end well.",
            "Imagine you call heads on 10 coin flips. You may win 7 times or only 3. Your call was the same each time. Only luck changed.",
            "Judge your process, not only the result.",
            "A careful choice ends badly through bad luck. Was the choice necessarily poor?",
            "No, luck played a part", ["Yes, always", "Only if it lost coin"], concept_key)
    raise KeyError(concept_key)


__all__ = ["prepared_lesson", "TERM_LESSONS", "TERMS"]
