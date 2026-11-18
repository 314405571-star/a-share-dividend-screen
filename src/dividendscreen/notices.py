"""Condition 3-B: scan announcement titles for restructurings and cash-outs.

The notebook version walked *stocks* on the outside and *months* on the inside,
so a 50-name pool over three years downloaded the same 36 daily reports 1,800
times — and, because it stepped 30 days at a time, it only ever looked at 36
scattered days out of 1,000. Announcements published on any other day were
invisible, and the output looked complete.

This module walks **dates** on the outside and matches the whole pool inside:
one fetch per day, every day covered, and a coverage report that says how many
days failed. The feed is still a title grep; that is why the output is a review
queue with an empty verdict column, not a filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Protocol, Sequence

__all__ = [
    "MA_KEYWORDS",
    "CASH_KEYWORDS",
    "EXCLUDE_KEYWORDS",
    "Notice",
    "Hit",
    "ScanReport",
    "NoticeSource",
    "classify",
    "match",
    "scan",
]

#: Words that make a title worth reading for condition 3-B.
MA_KEYWORDS = ("并购", "重大资产重组", "资产重组", "收购", "借壳", "卖壳")
CASH_KEYWORDS = ("清仓式减持", "协议转让", "股份转让", "大额套现")

#: Words that usually mean the opposite of a red flag.
EXCLUDE_KEYWORDS = ("增持", "回购", "股权激励", "员工持股", "终止", "不构成重大资产重组")


@dataclass(frozen=True)
class Notice:
    code: str
    title: str
    day: str


@dataclass(frozen=True)
class Hit:
    code: str
    day: str
    title: str
    keywords: tuple[str, ...]
    category: str              # "ma" | "cash" | "both"


@dataclass
class ScanReport:
    codes: int = 0
    days_requested: int = 0
    days_ok: int = 0
    days_failed: int = 0
    notices_seen: int = 0
    hits: list[Hit] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.days_ok / self.days_requested if self.days_requested else 0.0

    @property
    def by_code(self) -> dict[str, list[Hit]]:
        grouped: dict[str, list[Hit]] = {}
        for hit in self.hits:
            grouped.setdefault(hit.code, []).append(hit)
        return grouped


class NoticeSource(Protocol):
    def notices_on(self, day: str) -> list[Notice]:
        ...


def classify(title: str) -> tuple[tuple[str, ...], str]:
    """Keywords this title matches, and the category ("", "ma", "cash", "both")."""
    if any(word in title for word in EXCLUDE_KEYWORDS):
        return (), ""
    ma = tuple(word for word in MA_KEYWORDS if word in title)
    cash = tuple(word for word in CASH_KEYWORDS if word in title)
    if ma and cash:
        return ma + cash, "both"
    if ma:
        return ma, "ma"
    if cash:
        return cash, "cash"
    return (), ""


def match(notices: Iterable[Notice], codes: Sequence[str] | set[str]) -> list[Hit]:
    wanted = set(codes)
    hits = []
    for notice in notices:
        if notice.code not in wanted:
            continue
        keywords, category = classify(notice.title)
        if keywords:
            hits.append(Hit(notice.code, notice.day, notice.title, keywords, category))
    return hits


def scan(source: NoticeSource, codes: Sequence[str], start: date, end: date) -> ScanReport:
    """One fetch per day over ``[start, end]``; every day is counted."""
    report = ScanReport(codes=len(set(codes)))
    day = start
    while day <= end:
        key = day.strftime("%Y-%m-%d")
        report.days_requested += 1
        try:
            notices = source.notices_on(key)
        except Exception as exc:            # a failed day must show up in the report
            report.days_failed += 1
            report.errors.append((key, f"{type(exc).__name__}: {exc}"))
        else:
            report.days_ok += 1
            report.notices_seen += len(notices)
            report.hits.extend(match(notices, codes))
        day += timedelta(days=1)
    return report
