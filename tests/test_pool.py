"""Tests for conditions 1 and 2.

Run with:  python tests/test_pool.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.dividendscreen.pool import (  # noqa: E402
    Company,
    Criteria,
    Units,
    describe_units,
    ratio,
    screen,
    years_before,
)

AS_OF = date(2026, 11, 19)


def company(code="600000", listed=date(2015, 1, 1), dividends=30.0,
            financing=10.0, count=5) -> Company:
    return Company(code=code, name=f"n{code}", listed=listed, dividends=dividends,
                   financing=financing, dividend_count=count, financing_count=1)


def test_listing_cutoff_is_whole_years():
    criteria = Criteria(as_of=AS_OF, min_years=5)
    assert Company("a", "a", date(2021, 11, 19), 30, 10, 5).listed == date(2021, 11, 19)
    on_the_line = [company(code="a", listed=date(2021, 11, 19))]
    just_young = [company(code="b", listed=date(2021, 11, 20))]
    assert screen(on_the_line, criteria).selected
    assert not screen(just_young, criteria).selected
    assert screen(just_young, criteria).verdicts[0].reasons == ("too_young",)


def test_feb_29_clamps_to_the_28th():
    assert years_before(date(2024, 2, 29), 5) == date(2019, 2, 28)
    assert years_before(date(2026, 11, 19), 5) == date(2021, 11, 19)


def test_ratio_needs_financing():
    assert ratio(company(financing=0)) is None
    assert ratio(company(dividends=30, financing=10)) == 3.0


def test_screen_records_one_reason_per_failure():
    criteria = Criteria(as_of=AS_OF)
    cases = {
        "too_young": company(listed=date(2024, 1, 1)),
        "no_financing": company(financing=0, dividends=0),
        "no_dividend": company(dividends=0, count=0),
        "below_ratio": company(dividends=20, financing=10),
    }
    for expected, item in cases.items():
        verdict = screen([item], criteria).verdicts[0]
        assert not verdict.passed
        assert expected in verdict.reasons, (expected, verdict.reasons)


def test_funnel_partitions_the_universe():
    criteria = Criteria(as_of=AS_OF)
    rows = [
        company("a", date(2024, 1, 1)),                    # too young
        company("b", financing=0),                         # no financing
        company("c", dividends=0, count=0),                # no dividend
        company("d", dividends=20, financing=10),          # 2.0 < 3
        company("e", dividends=40, financing=10),          # 4.0 -> passes
    ]
    funnel = screen(rows, criteria).funnel
    counted = sum(value for key, value in funnel.items() if key != "total")
    assert counted == funnel["total"] == 5
    assert funnel["selected"] == 1


def test_units_default_to_the_proxy_regime():
    # The source module's own note says 累计股息 is a percentage, so the default
    # must not pretend the quotient is a ratio.
    assert Units().regime == "mixed"
    assert Units().comparable is False
    assert Units.declared("yi").comparable is True
    assert Units.declared("percent").comparable is False


def test_describe_units_reports_the_distribution():
    rows = [company("a", dividends=30, financing=10), company("b", dividends=10, financing=10)]
    stats = describe_units(rows)
    assert stats["n"] == 2
    assert stats["median_dividends"] == 20.0
    assert stats["median_ratio"] == 2.0


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
