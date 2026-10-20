"""One-time: freeze the pre-Alpaca (before 2016-01-04) equity history from
the yfinance caches into data/banked/. Includes a Jan-Mar 2016 overlap so
`data.alpaca_equity_bars.splice_banked` can rescale the seam after every
dividend-driven re-adjustment. Gitignored; regenerate only from a trusted
yfinance cache (2026-10-20 — see DATA_SOURCES.md).

Usage: uv run python3 scripts/bank_pre2016.py [--force]
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.pipeline import write_parquet_atomic  # noqa: E402

BANKED = ROOT / "data" / "banked"
OVERLAP_END = "2016-03-31"
SOURCES = {
    "sp500_pre2016.parquet": ROOT / "data" / "raw" / "sp500_prices.parquet",
    "spy_pre2016.parquet": ROOT / "data" / "raw" / "spy_filter.parquet",
}


def main(force: bool = False) -> None:
    BANKED.mkdir(exist_ok=True)
    for name, src in SOURCES.items():
        dst = BANKED / name
        if dst.exists() and not force:
            print(f"{dst} exists — skipping (use --force)")
            continue
        df = pd.read_parquet(src)
        banked = df.loc[: OVERLAP_END]
        if banked.index[0] > pd.Timestamp("2010-01-05") and "sp500" in name:
            raise SystemExit(f"{src} starts {banked.index[0].date()} — not a full-history cache, refusing")
        write_parquet_atomic(banked, dst)
        print(f"banked {name}: {banked.index[0].date()} -> {banked.index[-1].date()}, {banked.shape}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
