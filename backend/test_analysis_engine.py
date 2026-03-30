"""Unit tests for analysis_engine core calculation functions."""

import numpy as np
import pandas as pd
import pytest

from backend.analysis_engine import (
    calc_annual_returns,
    calc_basic_info,
    calc_max_drawdown,
    calc_volatility,
)


def _make_df(
    closes: list[float],
    start_date: str = "2023-01-02",
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
    amounts: list[float] | None = None,
    open_interests: list[float] | None = None,
) -> pd.DataFrame:
    """Helper to build a unified DataFrame for testing."""
    n = len(closes)
    dates = pd.bdate_range(start=start_date, periods=n)
    if highs is None:
        highs = [c * 1.02 for c in closes]
    if lows is None:
        lows = [c * 0.98 for c in closes]
    if volumes is None:
        volumes = [1000.0] * n
    if amounts is None:
        amounts = [50000.0] * n
    if open_interests is None:
        open_interests = [2000.0] * n

    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
        "amount": amounts,
        "open_interest": open_interests,
    })


# ── calc_basic_info ─────────────────────────────────────────


class TestCalcBasicInfo:
    def test_change_pct(self):
        df = _make_df([100.0, 110.0, 120.0])
        info = calc_basic_info(df, "ETF")
        expected = (120.0 / 100.0 - 1) * 100
        assert abs(info.change_pct - expected) < 0.01

    def test_high_low(self):
        df = _make_df([100.0, 200.0, 150.0], highs=[110.0, 220.0, 160.0], lows=[90.0, 180.0, 140.0])
        info = calc_basic_info(df, "ETF")
        assert info.high == 220.0
        assert info.low == 90.0

    def test_avg_volume(self):
        df = _make_df([100.0, 100.0], volumes=[1000.0, 3000.0])
        info = calc_basic_info(df, "ETF")
        assert info.avg_volume == 2000.0

    def test_etf_has_avg_amount(self):
        df = _make_df([100.0, 100.0], amounts=[5000.0, 7000.0])
        info = calc_basic_info(df, "ETF")
        assert info.avg_amount == 6000.0
        assert info.avg_open_interest is None

    def test_futures_has_avg_open_interest(self):
        df = _make_df([100.0, 100.0], open_interests=[3000.0, 5000.0])
        info = calc_basic_info(df, "期货主力连续")
        assert info.avg_open_interest == 4000.0
        assert info.avg_amount is None

    def test_date_range(self):
        df = _make_df([100.0, 110.0, 120.0], start_date="2023-06-01")
        info = calc_basic_info(df, "ETF")
        assert len(info.date_range) == 2
        assert info.date_range[0] == "2023-06-01"


# ── calc_annual_returns ─────────────────────────────────────


class TestCalcAnnualReturns:
    def test_single_year(self):
        df = _make_df([100.0, 110.0, 120.0], start_date="2023-01-02")
        result = calc_annual_returns(df)
        assert 2023 in result
        expected = (120.0 / 100.0 - 1) * 100
        assert abs(result[2023] - expected) < 0.01

    def test_multi_year(self):
        # Build a df spanning 2022 and 2023
        dates = list(pd.bdate_range("2022-12-28", periods=3)) + list(pd.bdate_range("2023-01-02", periods=3))
        closes = [100.0, 105.0, 110.0, 200.0, 210.0, 220.0]
        df = pd.DataFrame({
            "date": dates,
            "open": closes,
            "close": closes,
            "high": closes,
            "low": closes,
            "volume": [1000] * 6,
            "amount": [50000] * 6,
            "open_interest": [2000] * 6,
        })
        result = calc_annual_returns(df)
        assert 2022 in result
        assert 2023 in result
        # 2022: 110/100 - 1 = 10%
        assert abs(result[2022] - 10.0) < 0.01
        # 2023: 220/200 - 1 = 10%
        assert abs(result[2023] - 10.0) < 0.01

    def test_single_row_year_returns_zero(self):
        df = _make_df([100.0], start_date="2023-03-01")
        result = calc_annual_returns(df)
        assert result[2023] == 0.0


# ── calc_volatility ─────────────────────────────────────────


class TestCalcVolatility:
    def test_constant_prices_zero_vol(self):
        df = _make_df([100.0] * 10)
        vol = calc_volatility(df)
        assert vol.annualized_vol == 0.0
        assert vol.daily_return_mean == 0.0
        assert vol.daily_return_std == 0.0

    def test_annualized_vol_formula(self):
        closes = [100.0, 102.0, 99.0, 101.0, 103.0, 98.0, 100.0]
        df = _make_df(closes)
        vol = calc_volatility(df)
        daily_returns = pd.Series(closes).pct_change().dropna()
        expected_vol = float(daily_returns.std() * np.sqrt(252) * 100)
        assert abs(vol.annualized_vol - expected_vol) < 0.01

    def test_daily_return_stats(self):
        closes = [100.0, 105.0, 110.0]
        df = _make_df(closes)
        vol = calc_volatility(df)
        daily_returns = pd.Series(closes).pct_change().dropna()
        assert abs(vol.daily_return_mean - daily_returns.mean() * 100) < 0.01
        assert abs(vol.daily_return_std - daily_returns.std() * 100) < 0.01


# ── calc_max_drawdown ───────────────────────────────────────


class TestCalcMaxDrawdown:
    def test_simple_drawdown(self):
        # Peak at 200, trough at 100 → -50%
        closes = [100.0, 150.0, 200.0, 150.0, 100.0, 120.0]
        df = _make_df(closes)
        dd = calc_max_drawdown(df)
        assert abs(dd.max_drawdown_pct - (-50.0)) < 0.01
        assert dd.peak_price == 200.0
        assert dd.trough_price == 100.0

    def test_no_drawdown(self):
        # Monotonically increasing → drawdown is 0
        closes = [100.0, 110.0, 120.0, 130.0]
        df = _make_df(closes)
        dd = calc_max_drawdown(df)
        assert dd.max_drawdown_pct == 0.0

    def test_peak_before_trough(self):
        closes = [100.0, 200.0, 50.0, 150.0]
        df = _make_df(closes)
        dd = calc_max_drawdown(df)
        # Peak at index 1 (200), trough at index 2 (50) → -75%
        assert abs(dd.max_drawdown_pct - (-75.0)) < 0.01
        assert dd.peak_price == 200.0
        assert dd.trough_price == 50.0
        # peak_date should be before trough_date
        assert dd.peak_date < dd.trough_date


from backend.analysis_engine import (
    calc_correlation,
    calc_monthly_returns,
    calc_price_ratio_spread,
    calc_trend,
    calc_volume_trend,
)


# ── calc_correlation ────────────────────────────────────────


class TestCalcCorrelation:
    def _make_pair(self):
        """Two correlated DataFrames with overlapping dates."""
        dates = pd.bdate_range("2023-01-02", periods=100)
        closes_a = [100.0 + i * 0.5 for i in range(100)]
        closes_b = [200.0 + i * 0.8 for i in range(100)]
        df_a = _make_df(closes_a, start_date="2023-01-02")
        df_b = _make_df(closes_b, start_date="2023-01-02")
        return df_a, df_b

    def test_overlap_days(self):
        df_a, df_b = self._make_pair()
        info = calc_correlation(df_a, df_b)
        assert info.overlap_days == 100

    def test_perfect_positive_correlation(self):
        """Two perfectly linearly related price series should have corr ~1."""
        dates = pd.bdate_range("2023-01-02", periods=100)
        closes_a = [100.0 + i for i in range(100)]
        closes_b = [50.0 + i * 2 for i in range(100)]
        df_a = _make_df(closes_a)
        df_b = _make_df(closes_b)
        info = calc_correlation(df_a, df_b)
        assert info.price_corr > 0.99

    def test_partial_overlap(self):
        """DataFrames with different date ranges should only count overlapping days."""
        df_a = _make_df([100.0 + i for i in range(50)], start_date="2023-01-02")
        df_b = _make_df([200.0 + i for i in range(50)], start_date="2023-02-01")
        info = calc_correlation(df_a, df_b)
        assert info.overlap_days < 50

    def test_rolling_corr_bounds(self):
        df_a, df_b = self._make_pair()
        info = calc_correlation(df_a, df_b)
        assert info.rolling_corr_min <= info.rolling_corr_mean <= info.rolling_corr_max


# ── calc_trend ──────────────────────────────────────────────


class TestCalcTrend:
    def test_recent_changes(self):
        closes = [100.0 + i for i in range(120)]
        df = _make_df(closes)
        trend = calc_trend(df)
        # 5d change: (latest / 5-days-ago - 1) * 100
        expected_5d = (closes[-1] / closes[-5] - 1) * 100
        assert abs(trend.recent_changes["5d"] - expected_5d) < 0.01

    def test_ma_values(self):
        closes = [100.0] * 120
        df = _make_df(closes)
        trend = calc_trend(df)
        assert abs(trend.ma_values["MA5"] - 100.0) < 0.01
        assert abs(trend.ma_values["MA120"] - 100.0) < 0.01

    def test_bullish_trend(self):
        """Monotonically increasing prices → 多头排列."""
        closes = [100.0 + i * 2 for i in range(120)]
        df = _make_df(closes)
        trend = calc_trend(df)
        assert trend.trend_status == "多头排列"

    def test_bearish_trend(self):
        """Monotonically decreasing prices → 空头排列."""
        closes = [500.0 - i * 2 for i in range(120)]
        df = _make_df(closes)
        trend = calc_trend(df)
        assert trend.trend_status == "空头排列"

    def test_latest_price(self):
        closes = [100.0, 110.0, 120.0] + [120.0] * 117
        df = _make_df(closes)
        trend = calc_trend(df)
        assert trend.latest_price == 120.0


# ── calc_volume_trend ───────────────────────────────────────


class TestCalcVolumeTrend:
    def test_no_change(self):
        """Constant volume → change_pct ≈ 0."""
        # ~180 trading days ≈ ~8 months
        closes = [100.0] * 180
        volumes = [1000.0] * 180
        df = _make_df(closes, volumes=volumes)
        vt = calc_volume_trend(df)
        assert abs(vt.change_pct) < 0.01

    def test_increasing_volume(self):
        """Volume doubles in later months → positive change_pct."""
        # First 90 days: volume 1000, last 90 days: volume 2000
        closes = [100.0] * 180
        volumes = [1000.0] * 90 + [2000.0] * 90
        df = _make_df(closes, volumes=volumes)
        vt = calc_volume_trend(df)
        assert vt.change_pct > 0

    def test_recent_and_prev_avg(self):
        closes = [100.0] * 180
        volumes = [1000.0] * 180
        df = _make_df(closes, volumes=volumes)
        vt = calc_volume_trend(df)
        assert abs(vt.recent_3m_avg - 1000.0) < 0.01
        assert abs(vt.prev_3m_avg - 1000.0) < 0.01


# ── calc_price_ratio_spread ─────────────────────────────────


class TestCalcPriceRatioSpread:
    def test_equal_weights(self):
        df_a = _make_df([200.0, 200.0, 200.0])
        df_b = _make_df([100.0, 100.0, 100.0])
        info = calc_price_ratio_spread(df_a, df_b, 1.0, 1.0)
        assert abs(info.latest_ratio - 2.0) < 0.01
        assert abs(info.mean_ratio - 2.0) < 0.01
        assert abs(info.latest_spread - 100.0) < 0.01

    def test_with_weights(self):
        df_a = _make_df([200.0, 200.0])
        df_b = _make_df([100.0, 100.0])
        info = calc_price_ratio_spread(df_a, df_b, 2.0, 0.5)
        # ratio = (200*2) / (100*0.5) = 400/50 = 8
        assert abs(info.latest_ratio - 8.0) < 0.01
        # spread = 200*2 - 100*0.5 = 400 - 50 = 350
        assert abs(info.latest_spread - 350.0) < 0.01

    def test_max_min_ratio(self):
        df_a = _make_df([100.0, 200.0, 300.0])
        df_b = _make_df([100.0, 100.0, 100.0])
        info = calc_price_ratio_spread(df_a, df_b, 1.0, 1.0)
        assert abs(info.min_ratio - 1.0) < 0.01
        assert abs(info.max_ratio - 3.0) < 0.01


# ── calc_monthly_returns ────────────────────────────────────


class TestCalcMonthlyReturns:
    def test_single_month(self):
        closes = [100.0, 105.0, 110.0, 115.0, 120.0]
        df = _make_df(closes, start_date="2023-03-01")
        info = calc_monthly_returns(df)
        expected = (120.0 / 100.0 - 1) * 100
        assert abs(info.avg_monthly_return - expected) < 0.01
        assert info.positive_months_ratio == "1/1"

    def test_positive_months_ratio_format(self):
        # Span two months: Jan and Feb
        dates = list(pd.bdate_range("2023-01-02", periods=20)) + list(pd.bdate_range("2023-02-01", periods=20))
        # Jan: increasing, Feb: decreasing
        closes_jan = [100.0 + i for i in range(20)]
        closes_feb = [200.0 - i for i in range(20)]
        closes = closes_jan + closes_feb
        df = pd.DataFrame({
            "date": dates,
            "open": closes,
            "close": closes,
            "high": closes,
            "low": closes,
            "volume": [1000] * 40,
            "amount": [50000] * 40,
            "open_interest": [2000] * 40,
        })
        info = calc_monthly_returns(df)
        # Jan positive, Feb negative → "1/2"
        assert info.positive_months_ratio == "1/2"

    def test_max_min_monthly(self):
        dates = list(pd.bdate_range("2023-01-02", periods=20)) + list(pd.bdate_range("2023-02-01", periods=20))
        closes_jan = [100.0] * 19 + [150.0]  # +50%
        closes_feb = [200.0] * 19 + [100.0]  # -50%
        closes = closes_jan + closes_feb
        df = pd.DataFrame({
            "date": dates,
            "open": closes,
            "close": closes,
            "high": closes,
            "low": closes,
            "volume": [1000] * 40,
            "amount": [50000] * 40,
            "open_interest": [2000] * 40,
        })
        info = calc_monthly_returns(df)
        assert abs(info.max_monthly_return - 50.0) < 0.01
        assert abs(info.min_monthly_return - (-50.0)) < 0.01
