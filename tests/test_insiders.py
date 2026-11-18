"""Tests for the reduction review queue.

Run with:  python tests/test_insiders.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.dividendscreen.insiders import (  # noqa: E402
    Reduction,
    Rule,
    is_large,
    review_rows,
    select,
)


def test_share_threshold():
    rule = Rule(min_shares_wan=1000, min_ratio_pct=None)
    assert is_large(Reduction("a", "h", 1200), rule)
    assert not is_large(Reduction("a", "h", 900), rule)


def test_ratio_threshold_catches_a_small_but_large_stake():
    # 400 万股 is below the share bar, but 3% of equity is not small.
    rule = Rule(min_shares_wan=1000, min_ratio_pct=2.0)
    assert is_large(Reduction("a", "h", 400, ratio_pct=3.0), rule)
    assert not is_large(Reduction("a", "h", 400, ratio_pct=0.5), rule)


def test_modes():
    row = Reduction("a", "h", 1500, ratio_pct=0.2)
    assert is_large(row, Rule(mode="shares"))
    assert not is_large(row, Rule(mode="ratio", min_ratio_pct=1.0))
    assert not is_large(row, Rule(mode="and", min_ratio_pct=1.0))
    assert is_large(row, Rule(mode="or", min_ratio_pct=1.0))


def test_negative_amounts_are_absolute():
    assert is_large(Reduction("a", "h", -2600), Rule(min_shares_wan=1000))


def test_select_restricts_to_the_pool():
    rows = [
        Reduction("a", "h", 2000),
        Reduction("b", "h", 2000),
        Reduction("c", "h", 50),
    ]
    picked = select(rows, {"a", "c"})
    assert [r.code for r in picked] == ["a"]


def test_review_rows_leave_the_verdict_blank():
    rows = review_rows([Reduction("a", "某某控股", 2600, ratio_pct=1.2,
                                  day=date(2026, 5, 6))])
    assert rows[0].manual_verdict == ""
    assert rows[0].shares_wan == 2600.0
    assert rows[0].day == "2026-05-06"
    assert "1000" in rows[0].why


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
