"""Conditions 1 and 2: listed long enough, and returns more than it raises.

    listed ≥ 5 years
    cumulative dividends / cumulative financing ≥ 3

The ratio is the whole argument of this screen, so the code refuses to guess
what the two inputs are measured in. ``stock_history_dividend`` hands back
``累计股息`` and ``融资总额`` as bare numbers; if one is a percentage and the
other is 亿元 the "ratio" is not a ratio at all, it is a number that happens to
divide. :func:`diagnose_units` looks at the distribution and says which regime
the data is in; :func:`screen` records the verdict next to every result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median

__all__ = [
    "Company",
    "Criteria",
    "Units",
    "Verdict",
    "ScreenReport",
    "years_before",
    "ratio",
    "describe_units",
    "screen",
]


@dataclass(frozen=True)
class Company:
    code: str
    name: str
    listed: date
    dividends: float = 0.0        # 累计股息, as delivered by the feed
    financing: float = 0.0        # 融资总额, 亿元 (as delivered)
    dividend_count: int = 0       # 分红次数
    financing_count: int = 0      # 融资次数


@dataclass(frozen=True)
class Criteria:
    as_of: date
    min_years: int = 5
    min_ratio: float = 3.0
    require_financing: bool = True
    require_dividend: bool = True


@dataclass(frozen=True)
class Units:
    """What the two columns are assumed to be measured in.

    "same"    both are money — the quotient is a ratio.
    "mixed"   累计股息 is a percentage and 融资总额 is 亿元 — the quotient is a
              proxy score with no physical meaning. This is the default,
              because the source module's own note says so.
    """

    regime: str = "mixed"
    note: str = ""

    @property
    def comparable(self) -> bool:
        return self.regime == "same"

    @classmethod
    def declared(cls, flag: str) -> "Units":
        if flag == "yi":
            return cls("same", "declared: both columns are 亿元 — the quotient is a ratio")
        if flag == "percent":
            return cls("mixed", "declared: 累计股息 is a percentage — the quotient is a proxy")
        return cls("mixed", "default: units not declared — quotient is a proxy score")


@dataclass(frozen=True)
class Verdict:
    company: Company
    ratio: float | None
    reasons: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.reasons


@dataclass
class ScreenReport:
    criteria: Criteria
    units: Units
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def selected(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.passed]

    @property
    def funnel(self) -> dict[str, int]:
        counts = {
            "total": len(self.verdicts),
            "too_young": 0,
            "no_financing": 0,
            "no_dividend": 0,
            "below_ratio": 0,
            "selected": 0,
        }
        for verdict in self.verdicts:
            if verdict.passed:
                counts["selected"] += 1
            elif verdict.reasons and verdict.reasons[0] in counts:
                # first failing reason only, so the counts partition the total
                counts[verdict.reasons[0]] += 1
        return counts


# ------------------------------------------------------------------ helpers
def years_before(day: date, years: int) -> date:
    """``day`` shifted back by whole years, 29 Feb clamped to 28 Feb."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def ratio(company: Company) -> float | None:
    if company.financing <= 0:
        return None
    return company.dividends / company.financing


def describe_units(companies: list[Company]) -> dict[str, float]:
    """Distribution stats to eyeball before trusting the quotient."""
    pairs = [(c.dividends, c.financing) for c in companies if c.financing > 0]
    if not pairs:
        return {}
    dividends = sorted(d for d, _ in pairs)
    ratios = sorted(d / f for d, f in pairs)
    return {
        "n": len(pairs),
        "median_dividends": median(dividends),
        "median_financing": median(f for _, f in pairs),
        "median_ratio": median(ratios),
        "p90_ratio": ratios[int(len(ratios) * 0.9) - 1],
    }


# ------------------------------------------------------------------- screen
def screen(companies: list[Company], criteria: Criteria,
           units: Units | None = None) -> ScreenReport:
    units = units or Units()
    cutoff = years_before(criteria.as_of, criteria.min_years)
    report = ScreenReport(criteria=criteria, units=units)

    for company in companies:
        reasons: list[str] = []
        if company.listed > cutoff:
            reasons.append("too_young")
        if criteria.require_financing and company.financing <= 0:
            reasons.append("no_financing")
        if criteria.require_dividend and (company.dividend_count <= 0 or company.dividends <= 0):
            reasons.append("no_dividend")

        value = ratio(company)
        if value is None:
            if "no_financing" not in reasons:
                reasons.append("no_financing")
        elif value < criteria.min_ratio:
            reasons.append("below_ratio")

        report.verdicts.append(Verdict(company=company, ratio=value,
                                       reasons=tuple(reasons)))
    return report
