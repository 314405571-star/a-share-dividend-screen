"""akshare adapter and CLI.

Everything that touches the network lives here; the three conditions live in
:mod:`dividendscreen.pool`, :mod:`dividendscreen.insiders` and
:mod:`dividendscreen.notices`.

Unit discipline is the point of the adapter. Both feeds return bare numbers
whose units are not stated in the payload, so the run prints a diagnostic
before it prints a result: the dividend/financing distribution, and the
distribution of reduction sizes. If either looks like the wrong unit, the
report says so instead of producing a confident wrong answer.

    python -m src.dividendscreen.akshare_source screen --out output
"""

from __future__ import annotations

import argparse
import csv
import logging
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from .insiders import Reduction, Rule, review_rows, select
from .notices import Hit, Notice, NoticeSource, ScanReport, scan
from .pool import Company, Criteria, Units, describe_units, screen

__all__ = ["AkshareSource", "AkshareNoticeSource", "run_screen", "main", "normalise_code"]

log = logging.getLogger("dividendscreen")


# ------------------------------------------------------------------ helpers
def normalise_code(value) -> str:
    """'1', 1, 1.0 and '000001' all become '000001'."""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    text = text.split(".")[0]
    return text.zfill(6) if text.isdigit() else text


def _pick(row: dict, names: Iterable[str]):
    for name in names:
        if name in row:
            return row[name]
    return None


def _to_float(value) -> float | None:
    try:
        if value is None or value == "" or value == "-":
            return None
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _to_date(value) -> date | None:
    if value is None or value == "":
        return None
    text = str(value)[:10].replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------- source
class AkshareSource:
    def __init__(self, cache_dir: str | Path = "cache") -> None:
        self.cache_dir = Path(cache_dir)

    # -- dividends ------------------------------------------------------
    def companies(self) -> list[Company]:
        import akshare as ak  # lazy: the core imports offline

        frame = ak.stock_history_dividend()
        out: list[Company] = []
        for row in frame.to_dict("records"):
            listed = _to_date(_pick(row, ("上市日期",)))
            if listed is None:
                continue
            out.append(Company(
                code=normalise_code(_pick(row, ("代码", "股票代码"))),
                name=str(_pick(row, ("名称", "股票简称")) or ""),
                listed=listed,
                dividends=_to_float(_pick(row, ("累计股息",))) or 0.0,
                financing=_to_float(_pick(row, ("融资总额",))) or 0.0,
                dividend_count=int(_to_float(_pick(row, ("分红次数",))) or 0),
                financing_count=int(_to_float(_pick(row, ("融资次数",))) or 0),
            ))
        return out

    # -- reductions -----------------------------------------------------
    def reductions(self) -> list[Reduction]:
        import akshare as ak

        frame = ak.stock_ggcg_em(symbol="股东减持")
        out: list[Reduction] = []
        for row in frame.to_dict("records"):
            code = _pick(row, ("stock_code", "代码", "股票代码"))
            holder = _pick(row, ("holder_name", "股东名称"))
            amount = _pick(row, ("change_num", "变动数量", "持股变动信息-变动数量"))
            if code is None or holder is None or amount is None:
                continue
            out.append(Reduction(
                code=normalise_code(code),
                holder=str(holder),
                shares_wan=abs(_to_float(amount) or 0.0),
                ratio_pct=_to_float(_pick(row, ("change_total_ratio", "占总股本比例"))),
                day=_to_date(_pick(row, ("notice_date", "公告日期", "变动截止日期"))),
                raw_amount=str(amount),
            ))
        return out


class AkshareNoticeSource:
    """One call per day, cached to CSV. ``notices_on`` never raises on a good day."""

    def __init__(self, cache_dir: str | Path = "cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, day: str) -> Path:
        return self.cache_dir / f"notices_{day.replace('-', '')}.csv"

    def notices_on(self, day: str) -> list[Notice]:
        path = self._cache_path(day)
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                return [Notice(r["code"], r["title"], r["day"]) for r in csv.DictReader(fh)]

        import akshare as ak

        frame = ak.stock_notice_report(date=day.replace("-", ""))
        out: list[Notice] = []
        if frame is not None and not frame.empty:
            for row in frame.to_dict("records"):
                code = _pick(row, ("代码", "股票代码", "证券代码"))
                title = _pick(row, ("公告标题", "标题", "名称"))
                if code is None or title is None:
                    continue
                out.append(Notice(normalise_code(code), str(title), day))

        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["code", "title", "day"])
            for notice in out:
                writer.writerow([notice.code, notice.title, notice.day])
        return out


# --------------------------------------------------------------- diagnostics
def diagnose_reductions(reductions: Sequence[Reduction], rule: Rule) -> str:
    sizes = [abs(r.shares_wan) for r in reductions if r.shares_wan]
    if not sizes:
        return "no reduction rows"
    median = statistics.median(sizes)
    flagged = sum(1 for s in sizes if s >= rule.min_shares_wan) / len(sizes)
    text = (f"{len(sizes)} rows, median |shares| = {median:,.1f}, "
            f"{flagged:.1%} above {rule.min_shares_wan:g}")
    if flagged > 0.8:
        text += ("  ← more than 80% flagged: the column is probably in shares, "
                 "not 万股; raise --min-shares by 10,000× or check the feed")
    elif median < 1:
        text += "  ← median below 1: the column may not be 万股"
    return text


# --------------------------------------------------------------------- run
def _write(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_screen(
    *,
    as_of: date,
    out_dir: str | Path = "output",
    cache_dir: str | Path = "cache",
    criteria: Criteria | None = None,
    rule: Rule | None = None,
    notice_days: int = 365,
    limit: int | None = None,
    units: Units | None = None,
    scan_notices: bool = True,
    source: AkshareSource | None = None,
    notice_source: NoticeSource | None = None,
) -> dict:
    criteria = criteria or Criteria(as_of=as_of)
    rule = rule or Rule()
    source = source or AkshareSource(cache_dir)
    notice_source = notice_source or AkshareNoticeSource(cache_dir)
    out_dir = Path(out_dir)

    companies = source.companies()
    if limit:
        companies = companies[:limit]
    units = units or Units()
    report = screen(companies, criteria, units)

    print(f"universe {len(companies)}  ·  units: {units.regime} "
          f"({'comparable' if units.comparable else 'proxy'})")
    print(f"  {units.note}")
    stats = describe_units(companies)
    if stats:
        print(f"  dividends median {stats['median_dividends']:.3g} · "
              f"financing median {stats['median_financing']:.3g} · "
              f"quotient median {stats['median_ratio']:.3g} · p90 {stats['p90_ratio']:.3g}")
    for key, value in report.funnel.items():
        print(f"  {key:<14}{value:>6}")

    pool = report.selected
    pool_codes = {v.company.code for v in pool}
    names = {c.code: c.name for c in companies}

    stamp = as_of.strftime("%Y%m%d")
    _write(out_dir / f"初筛池_{stamp}.csv", [
        {
            "代码": v.company.code,
            "名称": v.company.name,
            "上市日期": v.company.listed.isoformat(),
            "累计股息": v.company.dividends,
            "融资总额": v.company.financing,
            "分红次数": v.company.dividend_count,
            "融资次数": v.company.financing_count,
            "分红融资比": None if v.ratio is None else round(v.ratio, 3),
            "口径": "可比" if units.comparable else ("代理指标" if units.regime == "mixed" else "未声明单位"),
        }
        for v in sorted(pool, key=lambda x: (x.ratio or 0), reverse=True)
    ])

    reductions: list[Reduction] = []
    if pool_codes:
        all_reductions = source.reductions()
        print(f"\n  reduction feed: {diagnose_reductions(all_reductions, rule)}")
        reductions = select(all_reductions, pool_codes, rule)
        rows = []
        for row in review_rows(reductions, rule):
            rows.append({
                "代码": row.code,
                "名称": names.get(row.code, ""),
                "股东": row.holder,
                "变动数量(万股)": row.shares_wan,
                "占总股本%": row.ratio_pct,
                "日期": row.day,
                "触发条件": row.why,
                "人工结论": "",
                "备注": "",
                "原始数值": row.raw_amount,
            })
        if rows:
            _write(out_dir / f"减持清单_{stamp}.csv", rows)
        print(f"  large reductions in the pool: {len(reductions)} rows")

    hits: list[Hit] = []
    notices_report: ScanReport | None = None
    if scan_notices and pool_codes:
        start = as_of - timedelta(days=notice_days)
        notices_report = scan(notice_source, sorted(pool_codes), start, as_of)
        hits = notices_report.hits
        print(f"  notices: {notices_report.days_ok}/{notices_report.days_requested} days, "
              f"coverage {notices_report.coverage:.1%}, {len(hits)} hits")
        if notices_report.days_failed:
            print(f"  ⚠ {notices_report.days_failed} days failed — see the coverage column")
        if hits:
            _write(out_dir / f"公告疑点_{stamp}.csv", [
                {
                    "代码": h.code,
                    "名称": names.get(h.code, ""),
                    "日期": h.day,
                    "公告标题": h.title,
                    "命中关键词": "、".join(h.keywords),
                    "类别": h.category,
                    "人工结论": "",
                    "备注": "",
                }
                for h in hits
            ])

    return {
        "companies": len(companies),
        "pool": len(pool),
        "reductions": len(reductions),
        "hits": len(hits),
        "coverage": notices_report.coverage if notices_report else None,
        "out": out_dir,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Listed 5y · dividends/financing ≥ 3 · insider review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("screen")
    run.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    run.add_argument("--years", type=int, default=5)
    run.add_argument("--ratio", type=float, default=3.0)
    run.add_argument("--min-shares", type=float, default=1000.0, help="万股")
    run.add_argument("--min-ratio-pct", type=float, default=1.0, help="占总股本 %%")
    run.add_argument("--notice-days", type=int, default=365)
    run.add_argument("--dividend-unit", choices=["auto", "yi", "percent"], default="auto",
                     help="yi: both columns are 亿元 (a real ratio); percent: 累计股息 is %%")
    run.add_argument("--out", default="output")
    run.add_argument("--cache", default="cache")
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--no-notices", action="store_true")
    run.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.cmd != "screen":
        return 1

    result = run_screen(
        as_of=date.fromisoformat(args.date),
        out_dir=args.out,
        cache_dir=args.cache,
        criteria=Criteria(as_of=date.fromisoformat(args.date), min_years=args.years,
                          min_ratio=args.ratio),
        rule=Rule(min_shares_wan=args.min_shares, min_ratio_pct=args.min_ratio_pct),
        notice_days=args.notice_days,
        limit=args.limit,
        units=Units.declared(args.dividend_unit),
        scan_notices=not args.no_notices,
    )
    print(f"\nwrote to {result['out']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
