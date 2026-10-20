"""splice_banked and the CBOE parser — pure functions of the 2026-10-20 data migration."""

import pandas as pd

from data.alpaca_equity_bars import splice_banked
from data.cboe import _parse_cboe_csv


def test_splice_rescales_banked_to_fresh_level():
    idx_b = pd.bdate_range("2015-10-01", "2016-03-31")
    banked = pd.DataFrame({"AAA": 50.0, "BBB": 20.0}, index=idx_b)
    idx_f = pd.bdate_range("2016-01-04", "2016-06-30")
    fresh = pd.DataFrame({"AAA": 100.0, "BBB": 20.0}, index=idx_f)  # AAA re-based 2x, BBB unchanged
    out = splice_banked(banked, fresh, "2016-03-31")
    assert out.index[0] == idx_b[0] and out.index[-1] == idx_f[-1]
    assert abs(out.loc["2015-12-31", "AAA"] - 100.0) < 1e-9
    assert abs(out.loc["2015-12-31", "BBB"] - 20.0) < 1e-9
    assert (out.loc["2016-01-04":, "AAA"] == 100.0).all()


def test_splice_median_ignores_one_bad_overlap_day():
    idx_b = pd.bdate_range("2015-12-01", "2016-03-31")
    banked = pd.DataFrame({"AAA": 50.0}, index=idx_b)
    idx_f = pd.bdate_range("2016-01-04", "2016-03-31")
    fresh = pd.DataFrame({"AAA": 100.0}, index=idx_f)
    fresh.iloc[3, 0] = 1000.0  # a single bad print must not move the ratio
    out = splice_banked(banked, fresh, "2016-03-31")
    assert abs(out.loc["2015-12-31", "AAA"] - 100.0) < 1e-9


def test_splice_keeps_symbols_absent_from_fresh():
    idx_b = pd.bdate_range("2015-12-01", "2016-03-31")
    banked = pd.DataFrame({"AAA": 50.0, "GONE": 7.0}, index=idx_b)
    fresh = pd.DataFrame({"AAA": 100.0}, index=pd.bdate_range("2016-01-04", "2016-02-29"))
    out = splice_banked(banked, fresh, "2016-03-31")
    assert out.loc["2015-12-31", "GONE"] == 7.0 and "GONE" in out.columns


def test_cboe_parser():
    text = "DATE,OPEN,HIGH,LOW,CLOSE\n10/16/2026,17.0,18.0,16.5,17.5\n10/19/2026,18.37,18.93,17.39,18.44\n"
    s = _parse_cboe_csv(text, "VIX")
    assert s.name == "^VIX" and s.index[-1] == pd.Timestamp("2026-10-19") and s.iloc[-1] == 18.44


def test_splice_drops_banked_history_when_overlap_ratio_is_unstable():
    """A reused ticker: banked and fresh are different instruments."""
    import numpy as np
    idx_b = pd.bdate_range("2015-12-01", "2016-03-31")
    banked = pd.DataFrame({"SW": 17.0 + np.arange(len(idx_b)) * 0.01}, index=idx_b)
    idx_f = pd.bdate_range("2016-01-04", "2016-03-31")
    fresh = pd.DataFrame({"SW": 160.0 + np.arange(len(idx_f)) * 1.5}, index=idx_f)  # ratio drifts 9x -> 11x
    out = splice_banked(banked, fresh, "2016-03-31")
    assert out.loc[:"2015-12-31", "SW"].isna().all()
    assert (out.loc["2016-01-04":, "SW"] == fresh["SW"]).all()
