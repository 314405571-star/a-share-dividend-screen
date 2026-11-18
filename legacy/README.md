# Legacy: the original script, verbatim

`screen_v1.py` is the script this repo grew out of, extracted without a single
edit. Every "the original did X" claim in
[`../docs/算法总结.md`](../docs/算法总结.md) can be checked against it.

It is a straight-line script: fetch dividends, filter, fetch reductions, print,
scan notices, print a usage note. It needs `akshare` and network access, and
prints rather than writes.

What this repo changes, with a test for each:

- the notice scan steps 30 days at a time, over 1,080 days — 36 dates out of
  ~1,090, and a fetch per stock rather than a fetch per day;
- request failures are swallowed by `except: continue`, so a hole in coverage
  reads as "no hits";
- the dividend/financing quotient is called a proxy in a comment and used as a
  ratio everywhere else; nothing declares the unit;
- "large reduction" is a share count, so the money involved varies by 20× with
  the share price;
- `5 * 365` days and `datetime.now()` make results drift with the calendar;
- `astype(str).str.zfill(6)` breaks on a float code (`1.0` → `0001.0`);
- the human review step exists only as printed instructions — there is no file
  to hand to the person doing the review.

None of these raise an exception. That is the point.
