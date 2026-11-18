"""Condition 3-A: surface large shareholder reductions for a human to read.

Nothing here decides whether a seller is a founder. The feed does not carry a
holder-type field, and guessing from a name ("XX投资", "XX控股") is exactly the
kind of inference that produces confident nonsense. The module's job is to
filter down to the rows worth a person's attention and to hand back a table
with an empty "manual verdict" column.

Two thresholds, because a share count alone is not size:

* ``min_shares_wan`` — a 10-million-share sale is ¥50m at ¥5 and ¥1bn at ¥100.
* ``min_ratio_pct`` — share of total equity, which is comparable across prices.

Either one flags the row (``mode="or"``): the list is a review queue, not a
verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Sequence

__all__ = ["Reduction", "Rule", "ReviewRow", "is_large", "select", "review_rows"]


@dataclass(frozen=True)
class Reduction:
    code: str
    holder: str
    shares_wan: float            # 变动数量, 万股 (sign ignored)
    ratio_pct: float | None = None   # 占总股本, %
    day: date | None = None
    raw_amount: str = ""         # what the feed actually said, for audit


@dataclass(frozen=True)
class Rule:
    min_shares_wan: float = 1000.0
    min_ratio_pct: float | None = 1.0
    mode: str = "or"             # "or" | "and" | "shares" | "ratio"


@dataclass(frozen=True)
class ReviewRow:
    code: str
    holder: str
    shares_wan: float
    ratio_pct: float | None
    day: str
    why: str                     # which threshold tripped
    #: Left blank on purpose — a person fills this in.
    manual_verdict: str = ""
    note: str = ""
    raw_amount: str = ""


def is_large(reduction: Reduction, rule: Rule = Rule()) -> bool:
    shares = abs(reduction.shares_wan)
    ratio = reduction.ratio_pct
    by_shares = shares >= rule.min_shares_wan
    by_ratio = ratio is not None and rule.min_ratio_pct is not None and ratio >= rule.min_ratio_pct

    if rule.mode == "shares":
        return by_shares
    if rule.mode == "ratio":
        return by_ratio
    if rule.mode == "and":
        return by_shares and by_ratio
    return by_shares or by_ratio


def _why(reduction: Reduction, rule: Rule) -> str:
    parts = []
    if abs(reduction.shares_wan) >= rule.min_shares_wan:
        parts.append(f"≥{rule.min_shares_wan:g}万股")
    if (reduction.ratio_pct is not None and rule.min_ratio_pct is not None
            and reduction.ratio_pct >= rule.min_ratio_pct):
        parts.append(f"≥{rule.min_ratio_pct:g}%股本")
    return " / ".join(parts)


def select(reductions: Iterable[Reduction], codes: Sequence[str] | set[str],
           rule: Rule = Rule()) -> list[Reduction]:
    """Large reductions, restricted to the pool, newest first."""
    wanted = set(codes)
    picked = [r for r in reductions if r.code in wanted and is_large(r, rule)]
    picked.sort(key=lambda r: (r.code, r.day or date.min), reverse=False)
    return picked


def review_rows(reductions: Iterable[Reduction], rule: Rule = Rule()) -> list[ReviewRow]:
    """One row per flagged reduction, with an empty column for the human call."""
    rows = []
    for r in reductions:
        rows.append(ReviewRow(
            code=r.code,
            holder=r.holder,
            shares_wan=round(abs(r.shares_wan), 2),
            ratio_pct=None if r.ratio_pct is None else round(r.ratio_pct, 4),
            day=r.day.isoformat() if r.day else "",
            why=_why(r, rule),
            raw_amount=r.raw_amount,
        ))
    return rows
