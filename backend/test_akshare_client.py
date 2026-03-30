"""Unit tests for akshare_client.fetch_contract_data."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from backend.akshare_client import fetch_contract_data
from backend.models import DataFetchError


def _make_etf_df(n: int = 30) -> pd.DataFrame:
    """Create a fake ETF DataFrame with Chinese column names."""
    dates = pd.date_range(end=datetime.now(), periods=n, freq="B")
    return pd.DataFrame({
        "日期": dates.strftime("%Y-%m-%d"),
        "开盘": range(100, 100 + n),
        "收盘": range(101, 101 + n),
        "最高": range(102, 102 + n),
        "最低": range(99, 99 + n),
        "成交量": [1000] * n,
        "成交额": [50000.0] * n,
    })


def _make_futures_df(n: int = 30) -> pd.DataFrame:
    """Create a fake futures DataFrame with Chinese column names."""
    dates = pd.date_range(end=datetime.now(), periods=n, freq="B")
    return pd.DataFrame({
        "日期": dates.strftime("%Y-%m-%d"),
        "开盘价": range(3000, 3000 + n),
        "收盘价": range(3010, 3010 + n),
        "最高价": range(3020, 3020 + n),
        "最低价": range(2990, 2990 + n),
        "成交量": [5000] * n,
        "持仓量": [80000] * n,
    })


# ── ETF tests ───────────────────────────────────────────────

@patch("backend.akshare_client.ak.stock_zh_a_hist")
def test_fetch_etf_returns_unified_columns(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("159985", "ETF"))
    assert list(df.columns) == [
        "date", "open", "close", "high", "low",
        "volume", "amount", "open_interest",
    ]
    assert df["amount"].notna().all()
    assert df["open_interest"].isna().all()


@patch("backend.akshare_client.ak.stock_zh_a_hist")
def test_fetch_etf_sorted_ascending(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("159985", "ETF"))
    dates = df["date"].tolist()
    assert dates == sorted(dates)


@patch("backend.akshare_client.ak.stock_zh_a_hist", side_effect=Exception("fail"))
@patch("backend.akshare_client.ak.fund_etf_hist_em")
def test_fetch_etf_fallback(mock_fund, mock_hist):
    mock_fund.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("159985", "ETF"))
    assert not df.empty
    mock_fund.assert_called_once()


# ── Futures tests ───────────────────────────────────────────

@patch("backend.akshare_client.ak.futures_main_sina")
def test_fetch_futures_returns_unified_columns(mock_sina):
    mock_sina.return_value = _make_futures_df()
    df = asyncio.run(fetch_contract_data("M0", "期货主力连续"))
    assert list(df.columns) == [
        "date", "open", "close", "high", "low",
        "volume", "amount", "open_interest",
    ]
    assert df["open_interest"].notna().all()
    assert df["amount"].isna().all()


@patch("backend.akshare_client.ak.futures_main_sina")
def test_fetch_futures_sorted_ascending(mock_sina):
    mock_sina.return_value = _make_futures_df()
    df = asyncio.run(fetch_contract_data("M0", "期货主力连续"))
    dates = df["date"].tolist()
    assert dates == sorted(dates)


# ── Error handling ──────────────────────────────────────────

@patch("backend.akshare_client.ak.futures_main_sina", side_effect=Exception("timeout"))
def test_fetch_futures_api_error_raises(mock_sina):
    with pytest.raises(DataFetchError) as exc_info:
        asyncio.run(fetch_contract_data("M0", "期货主力连续"))
    assert "M0" in str(exc_info.value)


@patch("backend.akshare_client.ak.stock_zh_a_hist", side_effect=Exception("fail"))
@patch("backend.akshare_client.ak.fund_etf_hist_em", side_effect=Exception("fail2"))
def test_fetch_etf_both_fail_raises(mock_fund, mock_hist):
    with pytest.raises(DataFetchError) as exc_info:
        asyncio.run(fetch_contract_data("159985", "ETF"))
    assert "159985" in str(exc_info.value)


@patch("backend.akshare_client.ak.futures_main_sina", return_value=pd.DataFrame())
def test_fetch_futures_empty_data_raises(mock_sina):
    with pytest.raises(DataFetchError):
        asyncio.run(fetch_contract_data("M0", "期货主力连续"))


def test_fetch_unsupported_type_raises():
    with pytest.raises(DataFetchError) as exc_info:
        asyncio.run(fetch_contract_data("XYZ", "股票"))
    assert "不支持的合约类型" in str(exc_info.value)


# ── A股股票 tests ───────────────────────────────────────────

@patch("backend.akshare_client.ak.stock_zh_a_hist")
def test_fetch_a_stock_returns_unified_columns(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("600519", "A股股票"))
    assert list(df.columns) == [
        "date", "open", "close", "high", "low",
        "volume", "amount", "open_interest",
    ]
    assert df["amount"].notna().all()
    assert df["open_interest"].isna().all()


@patch("backend.akshare_client.ak.stock_zh_a_hist")
def test_fetch_a_stock_sorted_ascending(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("600519", "A股股票"))
    dates = df["date"].tolist()
    assert dates == sorted(dates)


@patch("backend.akshare_client.ak.stock_zh_a_hist", side_effect=Exception("fail"))
def test_fetch_a_stock_api_error_raises(mock_hist):
    with pytest.raises(DataFetchError) as exc_info:
        asyncio.run(fetch_contract_data("600519", "A股股票"))
    assert "600519" in str(exc_info.value)


@patch("backend.akshare_client.ak.stock_zh_a_hist", return_value=pd.DataFrame())
def test_fetch_a_stock_empty_data_raises(mock_hist):
    with pytest.raises(DataFetchError):
        asyncio.run(fetch_contract_data("600519", "A股股票"))


# ── 美股 tests ──────────────────────────────────────────────

@patch("backend.akshare_client.ak.stock_us_hist")
def test_fetch_us_stock_returns_unified_columns(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("105.AAPL", "美股"))
    assert list(df.columns) == [
        "date", "open", "close", "high", "low",
        "volume", "amount", "open_interest",
    ]
    assert df["amount"].notna().all()
    assert df["open_interest"].isna().all()


@patch("backend.akshare_client.ak.stock_us_hist")
def test_fetch_us_stock_sorted_ascending(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("105.AAPL", "美股"))
    dates = df["date"].tolist()
    assert dates == sorted(dates)


@patch("backend.akshare_client.ak.stock_us_hist", side_effect=Exception("fail"))
def test_fetch_us_stock_api_error_raises(mock_hist):
    with pytest.raises(DataFetchError) as exc_info:
        asyncio.run(fetch_contract_data("105.AAPL", "美股"))
    assert "105.AAPL" in str(exc_info.value)


@patch("backend.akshare_client.ak.stock_us_hist", return_value=pd.DataFrame())
def test_fetch_us_stock_empty_data_raises(mock_hist):
    with pytest.raises(DataFetchError):
        asyncio.run(fetch_contract_data("105.AAPL", "美股"))


# ── 港股 tests ──────────────────────────────────────────────

@patch("backend.akshare_client.ak.stock_hk_hist")
def test_fetch_hk_stock_returns_unified_columns(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("09988", "港股"))
    assert list(df.columns) == [
        "date", "open", "close", "high", "low",
        "volume", "amount", "open_interest",
    ]
    assert df["amount"].notna().all()
    assert df["open_interest"].isna().all()


@patch("backend.akshare_client.ak.stock_hk_hist")
def test_fetch_hk_stock_sorted_ascending(mock_hist):
    mock_hist.return_value = _make_etf_df()
    df = asyncio.run(fetch_contract_data("09988", "港股"))
    dates = df["date"].tolist()
    assert dates == sorted(dates)


@patch("backend.akshare_client.ak.stock_hk_hist", side_effect=Exception("fail"))
def test_fetch_hk_stock_api_error_raises(mock_hist):
    with pytest.raises(DataFetchError) as exc_info:
        asyncio.run(fetch_contract_data("09988", "港股"))
    assert "09988" in str(exc_info.value)


@patch("backend.akshare_client.ak.stock_hk_hist", return_value=pd.DataFrame())
def test_fetch_hk_stock_empty_data_raises(mock_hist):
    with pytest.raises(DataFetchError):
        asyncio.run(fetch_contract_data("09988", "港股"))
