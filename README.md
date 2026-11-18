# A-Share Dividend Screen

**Three conditions, two of them arithmetic — and a review queue where the
third one belongs.**

    listed ≥ 5 years
    cumulative dividends / cumulative financing ≥ 3
    no large founder selling, no restructuring, no shell sale

The first two are a subtract-and-divide. The third is not automateable: the
insider feed has no holder-type field, and guessing "founder" from a name like
`某某控股` is how confident nonsense gets produced. So it is a queue with an
empty verdict column, not a filter.

What the repo does add is discipline in the two places the original script was
quiet: **what the ratio's units actually are**, and **how many days the
announcement scan really covered**.

Core is pure standard library, 21 tests, no network needed to run anything.

[English](README.md) | [中文](README.zh-CN.md)

---

## The two traps

### 1. The ratio may not be a ratio

`stock_history_dividend()` returns `累计股息` and `融资总额` as bare numbers. If
both are 亿元 the quotient is a real multiple — "the company has returned three
times what it raised". If `累计股息` is a **percentage**, the quotient has no
physical meaning at all; it is a ranking score that happens to divide.

The original script's own comment says it is a percentage, then labels the
result a ratio. So the default here is honest:

```python
Units()                  # "mixed"  → the 3 is a proxy, and the CSV says so
Units.declared("yi")     # "same"   → a real multiple
```

```bash
python -m src.dividendscreen.akshare_source screen --dividend-unit yi
```

Before printing a pool the run prints the distribution, so you can check the
assumption instead of trusting it:

```
dividends median 67.5 · financing median 37.9 · quotient median 1.78 · p90 4.49
```

A median quotient around 0.02 is a good sign the two columns are not the same
unit. For a strict absolute ratio, use Tushare's dividend endpoint; the adapter
has a single method (`companies()`) to replace.

### 2. The announcement scan covered 36 days out of 1,090

The original loops stocks on the outside and months on the inside:

```python
while current <= end:
    ak.stock_notice_report(date=current)   # returns the whole market for that day
    current += 30 days
```

Two consequences. It downloads the same daily report once **per stock** — 50
names × 36 months = 1,800 calls, 1,764 of them duplicates. And because it steps
30 days at a time, it only ever looks at 36 scattered dates; announcements
published on any other day are invisible, while the output says "no keyword
hits found".

This repo walks **dates** on the outside and matches the pool inside: one fetch
per day, every day, with a coverage report that counts failed days separately
from quiet ones.

---

## Quick start

```bash
pip install -r requirements.txt

# Offline: 60 synthetic companies, a fake feed, the three review files
python examples/demo_screen.py

# Tests (standard library only)
python tests/test_pool.py
python tests/test_insiders.py
python tests/test_notices.py
python tests/test_pipeline.py
```

Live, against akshare (free):

```bash
python -m src.dividendscreen.akshare_source screen \
    --dividend-unit yi --notice-days 365 --out output
```

---

## What the demo produces

```
universe 60  ·  units: same (comparable)
  dividends median 67.5 · financing median 37.9 · quotient median 1.78 · p90 4.49
  total             60
  too_young         31
  no_financing      14
  no_dividend        2
  below_ratio        3
  selected          10
  reduction feed: 6 rows, median |shares| = 1,075.0, 50.0% above 1000
  large reductions in the pool: 3 rows
  notices: 61/61 days, coverage 100.0%, 2 hits
```

Three files land in `output/`:

| File | Who fills it |
|---|---|
| `初筛池_<date>.csv` — conditions 1–2, with the ratio and its unit verdict | automatic |
| `减持清单_<date>.csv` — large reductions, **empty `人工结论` column** | a person |
| `公告疑点_<date>.csv` — matched notice titles, same empty column | a person |

The review criteria are in [docs/算法总结.md](docs/算法总结.md) §5: is the seller
a founder, is the sale large, is the notice a real restructuring or shell sale.

---

## Bugs this repo fixes

The original script is preserved verbatim in [`legacy/`](legacy/).

| # | Defect | Effect | Fix |
|---|---|---|---|
| 1 | Announcement scan steps 30 days | 36 of 1,090 days covered; the rest invisible, output looks clean | walk every day |
| 2 | One notice fetch per stock per month | 1,800 requests, 98% duplicates | one fetch per day, match the pool |
| 3 | `except: continue` around each request | holes in coverage, silently | failed days counted and reported |
| 4 | Ratio units assumed, never stated | a threshold of 3 means different things in the two regimes | explicit `Units`, printed in the CSV |
| 5 | "Large" measured in shares only | 10M shares is ¥50m at ¥5 and ¥1bn at ¥100 | shares **or** % of equity |
| 6 | `5 × 365` days, `datetime.now()` | one day off in leap years; results drift with the clock | whole-year cutoff, explicit `as_of` |
| 7 | `astype(str)` on the code column | a float code becomes `0001.0` | strip the decimal, zero-fill |
| 8 | The manual step only existed as `print` | nothing to hand to a reviewer | three CSVs with empty verdict columns |

---

## Repository layout

```
.
├── src/dividendscreen/
│   ├── pool.py               # conditions 1–2, units, funnel (pure)
│   ├── insiders.py           # reduction thresholds, review rows
│   ├── notices.py            # per-day scan, keyword matching, coverage
│   └── akshare_source.py     # adapter + CLI
├── examples/
│   ├── demo_screen.py        # synthetic market + fake feed
│   └── output/               # the three review files (generated)
├── legacy/screen_v1.py       # the original script, unmodified
├── docs/算法总结.md
├── tests/
└── requirements.txt
```

---

## Honest limitations

- **Not a backtest.** No entry, no exit, no cost. "A company that returns cash"
  is not the same as "a stock that goes up".
- **The third condition cannot be automated.** No holder-type field exists; the
  notices have to be read.
- **The reduction feed is not complete.** `stock_ggcg_em` returns recent
  records, not full history — an empty list does not mean "no selling".
- **Titles are a coarse filter.** "股份转让" is common and often harmless;
  "发行股份购买资产" contains none of the keywords. Read hits, and do not read
  silence as safety.
- **Units depend on the feed.** A strict absolute ratio needs Tushare or
  a manual export.
- **The five-year gate excludes a lot of good companies**, by design.

---

## Disclaimer

For research and education only — **not investment advice**.

## License

MIT
