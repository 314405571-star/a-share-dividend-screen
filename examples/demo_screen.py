"""Offline demo: a synthetic market, the three conditions, and the review files.

No network, no akshare. The adapter is exercised with a fake source, so the
whole run — diagnostics, funnel, CSV writing — is reproducible on any machine.

    python examples/demo_screen.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dividendscreen.akshare_source import run_screen  # noqa: E402
from src.dividendscreen.insiders import Reduction, Rule  # noqa: E402
from src.dividendscreen.notices import Notice  # noqa: E402
from src.dividendscreen.pool import Company, Criteria, Units  # noqa: E402

AS_OF = date(2026, 11, 19)
OUT = Path(__file__).resolve().parent / "output"
SEED = 11


def build_companies(rng: random.Random, n: int = 60) -> list[Company]:
    """Ten names that clear conditions 1–2, fifty that miss for one reason or another."""
    companies: list[Company] = []
    for i in range(n):
        if i < 10:
            listed = AS_OF - timedelta(days=365 * 9)
            financing = round(rng.uniform(15, 60), 1)
            dividends = round(financing * rng.uniform(3.2, 5.5), 1)
            count = rng.randint(6, 15)
        else:
            listed = AS_OF - timedelta(days=rng.randint(200, 3000))
            financing = rng.choice([0.0, round(rng.uniform(3, 90), 1)])
            dividends = 0.0 if financing == 0 else round(financing * rng.uniform(0.2, 2.6), 1)
            count = rng.randint(0, 8)
        companies.append(Company(
            code=f"{600000 + i:06d}",
            name=f"样本{i:02d}",
            listed=listed,
            dividends=dividends,
            financing=financing,
            dividend_count=count,
            financing_count=rng.randint(0, 4),
        ))
    return companies


def build_reductions(rng: random.Random, companies: list[Company]) -> list[Reduction]:
    holders = ["某某控股", "某某投资", "某某基金", "员工持股平台", "某某创投"]
    out: list[Reduction] = []
    for index, company in enumerate(companies[:6]):
        shares = [2600.0, 400.0, 1500.0, 120.0, 1800.0, 650.0][index]
        out.append(Reduction(
            code=company.code,
            holder=rng.choice(holders),
            shares_wan=shares,
            ratio_pct=round(shares / 10000 * rng.uniform(0.6, 1.4), 3),
            day=AS_OF - timedelta(days=rng.randint(20, 500)),
            raw_amount=f"{shares}",
        ))
    return out


class FakeNoticeSource:
    """Returns a handful of announcements on fixed days; counts its calls."""

    def __init__(self, notices: list[Notice]) -> None:
        self._by_day: dict[str, list[Notice]] = {}
        for notice in notices:
            self._by_day.setdefault(notice.day, []).append(notice)
        self.calls = 0

    def notices_on(self, day: str) -> list[Notice]:
        self.calls += 1
        return list(self._by_day.get(day, []))


def build_notices(companies: list[Company]) -> list[Notice]:
    day1 = (AS_OF - timedelta(days=20)).isoformat()
    day2 = (AS_OF - timedelta(days=5)).isoformat()
    pool = [c.code for c in companies]
    return [
        Notice(pool[2], "关于筹划重大资产重组的停牌公告", day1),
        Notice(pool[2], "关于股东增持公司股份的公告", day2),          # excluded
        Notice(pool[4], "控股股东拟协议转让部分股份的提示性公告", day2),
        Notice(pool[6], "关于回购公司股份的进展公告", day1),          # excluded
    ]


class FakeSource:
    def __init__(self, companies, reductions):
        self._companies = companies
        self._reductions = reductions

    def companies(self):
        return list(self._companies)

    def reductions(self):
        return list(self._reductions)


def main() -> int:
    rng = random.Random(SEED)
    companies = build_companies(rng)
    reductions = build_reductions(rng, companies)
    notice_source = FakeNoticeSource(build_notices(companies))

    print("Three-condition screen — offline demo")
    print(f"  as of {AS_OF}  ·  synthetic universe {len(companies)}\n")

    result = run_screen(
        as_of=AS_OF,
        out_dir=OUT,
        criteria=Criteria(as_of=AS_OF),
        units=Units.declared("yi"),
        rule=Rule(),
        notice_days=60,
        source=FakeSource(companies, reductions),
        notice_source=notice_source,
    )

    print(f"\n  notice fetches: {notice_source.calls} (one per day, not one per stock)")
    print(f"  pool: {result['pool']}  ·  reductions flagged: {result['reductions']}"
          f"  ·  notice hits: {result['hits']}")
    print(f"  coverage: {result['coverage']:.0%}")
    print(f"\n  files in {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}:")
    for path in sorted(OUT.glob("*.csv")):
        print(f"    {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
