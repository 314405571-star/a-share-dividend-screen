"""Tests for the announcement scan.

Run with:  python tests/test_notices.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.dividendscreen.notices import (  # noqa: E402
    Notice,
    classify,
    match,
    scan,
)


class FakeSource:
    """Returns the notices for the day, and counts how many times it was asked."""

    def __init__(self, by_day, fail_on=()):
        self.by_day = by_day
        self.fail_on = set(fail_on)
        self.calls = []

    def notices_on(self, day):
        self.calls.append(day)
        if day in self.fail_on:
            raise RuntimeError("feed down")
        return self.by_day.get(day, [])


def test_classify_splits_ma_from_cash():
    assert classify("关于筹划重大资产重组的停牌公告")[1] == "ma"
    assert classify("控股股东拟协议转让部分股份")[1] == "cash"
    keywords, category = classify("重大资产重组及股份转让公告")
    assert category == "both"
    assert "重大资产重组" in keywords


def test_exclusions_remove_counter_signals():
    for title in ("关于股东增持公司股份的公告", "关于回购公司股份的进展公告",
                  "关于终止重大资产重组的公告", "股权激励计划草案"):
        assert classify(title) == ((), "")


def test_match_only_returns_pool_codes():
    notices = [
        Notice("600001", "重大资产重组停牌", "2026-11-10"),
        Notice("600002", "重大资产重组停牌", "2026-11-10"),
        Notice("600003", "季度报告", "2026-11-10"),
    ]
    hits = match(notices, {"600001"})
    assert [h.code for h in hits] == ["600001"]
    assert hits[0].keywords == ("重大资产重组", "资产重组")


def test_scan_asks_every_day_not_every_stock():
    start, end = date(2026, 11, 1), date(2026, 11, 30)
    source = FakeSource({})
    report = scan(source, ["600001", "600002"], start, end)
    assert report.days_requested == 30
    assert len(source.calls) == 30          # one fetch per day, not per stock-day
    assert report.coverage == 1.0


def test_scan_finds_a_notice_on_an_odd_day():
    # The notebook stepped 30 days at a time from an arbitrary start, so a
    # notice published between two steps was invisible.
    start, end = date(2026, 11, 1), date(2026, 11, 30)
    source = FakeSource({"2026-11-07": [Notice("600001", "收购报告书", "2026-11-07")]})
    report = scan(source, ["600001"], start, end)
    assert len(report.hits) == 1
    assert report.hits[0].day == "2026-11-07"


def test_failed_days_are_counted_not_hidden():
    start, end = date(2026, 11, 1), date(2026, 11, 10)
    source = FakeSource({}, fail_on={"2026-11-03", "2026-11-04"})
    report = scan(source, ["600001"], start, end)
    assert report.days_failed == 2
    assert report.days_ok == 8
    assert abs(report.coverage - 0.8) < 1e-9
    assert len(report.errors) == 2


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {name}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
