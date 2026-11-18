"""A three-condition A-share screen: age, cash returned, and insider review.

The core (:mod:`pool`, :mod:`insiders`, :mod:`notices`) is pure standard
library. :mod:`akshare_source` is the network adapter and the CLI.
"""

from .insiders import Reduction, ReviewRow, Rule, is_large, review_rows, select
from .notices import (
    CASH_KEYWORDS,
    EXCLUDE_KEYWORDS,
    MA_KEYWORDS,
    Hit,
    Notice,
    ScanReport,
    classify,
    match,
    scan,
)
from .pool import (
    Company,
    Criteria,
    ScreenReport,
    Units,
    Verdict,
    describe_units,
    ratio,
    screen,
    years_before,
)

__all__ = [
    "CASH_KEYWORDS",
    "Company",
    "Criteria",
    "EXCLUDE_KEYWORDS",
    "Hit",
    "MA_KEYWORDS",
    "Notice",
    "Reduction",
    "ReviewRow",
    "Rule",
    "ScanReport",
    "ScreenReport",
    "Units",
    "Verdict",
    "classify",
    "describe_units",
    "is_large",
    "match",
    "ratio",
    "review_rows",
    "scan",
    "screen",
    "select",
    "years_before",
]
