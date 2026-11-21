"""Mock transactions and the spending-category -> candidate-company map (PoC, no bank data).

Real bank data is out of scope for the hackathon: every session sees the same fictional history
for Lena. The pipeline reads the merchants, groups spending by category and picks a listed company
for the category. Each category lists several companies (the merchant itself and its peers), so a
player cannot tell from their own spending which company a quest is about; the player only ever
sees the category label.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Transaction:
    days_ago: int
    merchant: str
    amount_eur: Decimal  # negative = spending
    category: str

    def as_dict(self, today: date) -> dict[str, str]:
        return {
            "date": (today - timedelta(days=self.days_ago)).isoformat(),
            "merchant": self.merchant,
            "amount_eur": str(self.amount_eur),
            "category": self.category,
            "category_label": CATEGORIES[self.category].label if self.category in CATEGORIES
            else "Other",
        }


@dataclass(frozen=True)
class Company:
    name: str
    ticker: str  # yfinance symbol
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    interest: str  # spec 003 interest chip this maps to
    companies: tuple[Company, ...]


CATEGORIES: dict[str, Category] = {
    c.key: c
    for c in (
        Category(
            "music",
            "Music & streaming",
            "Music",
            (
                Company("Spotify Technology", "SPOT", ("Spotify",)),
                Company("Sirius XM Holdings", "SIRI", ("SiriusXM", "Sirius XM")),
                Company("Warner Music Group", "WMG", ("Warner Music",)),
                Company("Netflix", "NFLX"),
            ),
        ),
        Category(
            "sportswear",
            "Sportswear & sneakers",
            "Fashion",
            (
                Company("Nike", "NKE"),
                Company("adidas", "ADS.DE", ("Adidas",)),
                Company("Puma", "PUM.DE"),
                Company("Under Armour", "UAA"),
                Company("Foot Locker", "FL"),
            ),
        ),
        Category(
            "fashion",
            "Online fashion",
            "Fashion",
            (
                Company("Zalando", "ZAL.DE"),
                Company("ASOS", "ASC.L"),
                Company("Inditex", "ITX.MC", ("Zara",)),
                Company("H&M", "HM-B.ST", ("Hennes & Mauritz",)),
            ),
        ),
        Category(
            "mobility",
            "Rides & mobility",
            "Mobility",
            (
                Company("Uber Technologies", "UBER", ("Uber",)),
                Company("Lyft", "LYFT"),
                Company("Grab Holdings", "GRAB", ("Grab",)),
            ),
        ),
        Category(
            "food_delivery",
            "Food delivery",
            "Tech",
            (
                Company("Delivery Hero", "DHER.DE"),
                Company("Just Eat Takeaway.com", "TKWY.AS", ("Just Eat", "Takeaway.com")),
                Company("DoorDash", "DASH"),
            ),
        ),
        Category(
            "gaming",
            "Games & consoles",
            "Gaming",
            (
                Company("Ubisoft Entertainment", "UBI.PA", ("Ubisoft",)),
                Company("Take-Two Interactive", "TTWO", ("Take-Two",)),
                Company("Electronic Arts", "EA"),
                Company("Nintendo", "7974.T"),
            ),
        ),
    )
}

# Lena, 18, apprentice. Amounts in EUR, spending negative.
LENA: tuple[Transaction, ...] = (
    Transaction(1, "Spotify", Decimal("-10.99"), "music"),
    Transaction(2, "Lieferando", Decimal("-18.40"), "food_delivery"),
    Transaction(3, "Uber", Decimal("-12.60"), "mobility"),
    Transaction(5, "Zalando", Decimal("-59.95"), "fashion"),
    Transaction(6, "Steam", Decimal("-19.99"), "gaming"),
    Transaction(8, "Nike Store", Decimal("-89.99"), "sportswear"),
    Transaction(9, "Lieferando", Decimal("-14.20"), "food_delivery"),
    Transaction(11, "Uber", Decimal("-9.80"), "mobility"),
    Transaction(14, "Training wage", Decimal("1050.00"), "income"),
    Transaction(15, "PlayStation Store", Decimal("-29.99"), "gaming"),
    Transaction(18, "Zalando", Decimal("-34.50"), "fashion"),
    Transaction(21, "Uber", Decimal("-15.10"), "mobility"),
    Transaction(24, "adidas", Decimal("-64.95"), "sportswear"),
    Transaction(27, "Wolt", Decimal("-21.30"), "food_delivery"),
)


def transactions_for(session_id: object) -> tuple[Transaction, ...]:  # noqa: ARG001 - PoC
    """Every session gets Lena's history in the PoC."""
    return LENA


def spending_by_category(txs: tuple[Transaction, ...]) -> list[tuple[str, Decimal]]:
    """Categories ranked by spend (largest first), only those we have companies for."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for t in txs:
        if t.amount_eur < 0 and t.category in CATEGORIES:
            totals[t.category] += -t.amount_eur
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


def candidate_queue(
    txs: tuple[Transaction, ...], used: set[str], seed: int
) -> list[tuple[Category, Company]]:
    """Every (category, company) not yet used by this player, ordered for variety.

    Categories rotate (by ``seed``, e.g. the day number) so consecutive quests come from
    different spending areas; within a category the companies rotate the same way, so the
    merchant the player actually paid is not always the one picked.
    """
    cats = [CATEGORIES[k] for k, _ in spending_by_category(txs)]
    if not cats:
        return []
    shift = seed % len(cats)
    cats = cats[shift:] + cats[:shift]
    out: list[tuple[Category, Company]] = []
    depth = max(len(c.companies) for c in cats)
    for level in range(depth):
        for cat in cats:
            comps = cat.companies
            comp = comps[(seed + level) % len(comps)] if level < len(comps) else None
            if comp is not None and comp.ticker not in used:
                out.append((cat, comp))
    seen: set[str] = set()
    return [(c, p) for c, p in out if not (p.ticker in seen or seen.add(p.ticker))]
