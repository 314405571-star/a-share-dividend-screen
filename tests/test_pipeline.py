"""End-to-end test of the adapter orchestration, with a fake feed.

    python tests/test_pipeline.py
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.dividendscreen.akshare_source import run_screen  # noqa: E402
from src.dividendscreen.insiders import Reduction, Rule  # noqa: E402
from src.dividendscreen.notices import Notice  # noqa: E402
from src.dividendscreen.pool import Company, Criteria, Units  # noqa: E402

AS_OF = date(2026, 11, 19)


class FakeSource:
    def __init__(self, companies, reductions):
        self._companies = companies
        self._reductions = reductions

    def companies(self):
        return list(self._companies)

    def reductions(self):
        return list(self._reductions)


class FakeNotices:
    def __init__(self, notices):
        self._by_day = {}
        for notice in notices:
            self._by_day.setdefault(notice.day, []).append(notice)

    def notices_on(self, day):
        return list(self._by_day.get(day, []))


def build():
    companies = [
        Company("600001", "甲", date(2014, 5, 1), 90.0, 20.0, 12, 2),
        Company("600002", "乙", date(2016, 5, 1), 60.0, 15.0, 9, 1),
        Company("600003", "丙", date(2024, 5, 1), 40.0, 10.0, 4, 1),
    ]
    reductions = [
        Reduction("600001", "某某控股", 2600, 1.4, date(2026, 6, 1)),
        Reduction("600002", "少量股东", 300, 0.2, date(2026, 6, 1)),
    ]
    notices = [Notice("600002", "关于筹划重大资产重组的公告", "2026-11-10")]
    return companies, reductions, notices


def test_run_writes_the_three_review_files():
    companies, reductions, notices = build()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = run_screen(
            as_of=AS_OF, out_dir=root, criteria=Criteria(as_of=AS_OF),
            rule=Rule(), notice_days=15, units=Units.declared("yi"),
            source=FakeSource(companies, reductions),
            notice_source=FakeNotices(notices),
        )
        assert result["pool"] == 2          # the 2024 listing is too young
        assert result["reductions"] == 1    # only the 2600万股 row clears the bar
        assert result["hits"] == 1

        pool = next(root.glob("初筛池_*.csv"))
        with pool.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert [r["代码"] for r in rows] == ["600001", "600002"]
        assert rows[0]["口径"] == "可比"

        review = next(root.glob("减持清单_*.csv"))
        with review.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["人工结论"] == ""       # a person fills this in
        assert rows[0]["代码"] == "600001"


def test_missing_units_declaration_is_reported_as_a_proxy():
    companies, reductions, _ = build()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_screen(as_of=AS_OF, out_dir=root, criteria=Criteria(as_of=AS_OF),
                   units=Units(), scan_notices=False, source=FakeSource(companies, reductions))
        pool = next(root.glob("初筛池_*.csv"))
        with pool.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["口径"] == "代理指标"


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
