"""Unit tests for run_full_analysis and API routes."""

from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.analysis_engine import run_full_analysis
from backend.main import app
from backend.models import AnalysisError, ContractInput, DataFetchError


def _make_df(
    closes: list[float],
    start_date: str = "2023-01-02",
    volumes: list[float] | None = None,
    amounts: list[float] | None = None,
    open_interests: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    dates = pd.bdate_range(start=start_date, periods=n)
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
        "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes],
        "volume": volumes,
        "amount": amounts,
        "open_interest": open_interests,
    })


# ── run_full_analysis tests ─────────────────────────────────


class TestRunFullAnalysis:
    def _make_pair(self):
        closes_a = [100.0 + i * 0.5 for i in range(180)]
        closes_b = [200.0 + i * 0.3 for i in range(180)]
        df_a = _make_df(closes_a, start_date="2023-01-02")
        df_b = _make_df(closes_b, start_date="2023-01-02")
        ca = ContractInput(code="159985", contract_type="ETF", weight=1.0)
        cb = ContractInput(code="M0", contract_type="期货主力连续", weight=1.0)
        return df_a, df_b, ca, cb

    def test_returns_analysis_response(self):
        df_a, df_b, ca, cb = self._make_pair()
        result = run_full_analysis(df_a, df_b, ca, cb)
        assert result.basic_info_a is not None
        assert result.basic_info_b is not None
        assert result.correlation is not None
        assert result.charts_data is not None

    def test_contract_names(self):
        df_a, df_b, ca, cb = self._make_pair()
        result = run_full_analysis(df_a, df_b, ca, cb)
        assert "159985" in result.contract_a_name
        assert "M0" in result.contract_b_name

    def test_annual_returns_merged(self):
        df_a, df_b, ca, cb = self._make_pair()
        result = run_full_analysis(df_a, df_b, ca, cb)
        assert len(result.annual_returns) > 0
        for ar in result.annual_returns:
            assert hasattr(ar, "year")
            assert hasattr(ar, "return_a")
            assert hasattr(ar, "return_b")

    def test_charts_data_lengths(self):
        df_a, df_b, ca, cb = self._make_pair()
        result = run_full_analysis(df_a, df_b, ca, cb)
        cd = result.charts_data
        assert len(cd.dates_a) == len(cd.prices_a) == len(cd.ma20_a) == len(cd.ma60_a)
        assert len(cd.dates_b) == len(cd.prices_b) == len(cd.ma20_b) == len(cd.ma60_b)
        assert len(cd.overlap_dates) == len(cd.price_ratio) == len(cd.price_spread)
        assert len(cd.norm_prices_a) == len(cd.norm_prices_b) == len(cd.overlap_dates)
        assert len(cd.rolling_corr) == len(cd.overlap_dates)

    def test_normalized_prices_start_at_100(self):
        df_a, df_b, ca, cb = self._make_pair()
        result = run_full_analysis(df_a, df_b, ca, cb)
        cd = result.charts_data
        assert abs(cd.norm_prices_a[0] - 100.0) < 0.01
        assert abs(cd.norm_prices_b[0] - 100.0) < 0.01

    def test_monthly_returns_merged(self):
        df_a, df_b, ca, cb = self._make_pair()
        result = run_full_analysis(df_a, df_b, ca, cb)
        cd = result.charts_data
        assert len(cd.months) == len(cd.monthly_returns_a) == len(cd.monthly_returns_b)
        assert len(cd.months) > 0

    def test_weights_applied(self):
        closes = [100.0] * 120
        df_a = _make_df(closes)
        df_b = _make_df(closes)
        ca = ContractInput(code="A", contract_type="ETF", weight=2.0)
        cb = ContractInput(code="B", contract_type="ETF", weight=0.5)
        result = run_full_analysis(df_a, df_b, ca, cb)
        # ratio = (100*2) / (100*0.5) = 4.0
        assert abs(result.charts_data.price_ratio[0] - 4.0) < 0.01


# ── API endpoint tests ──────────────────────────────────────


client = TestClient(app)


class TestAnalyzeEndpoint:
    def _mock_df(self):
        return _make_df([100.0 + i * 0.5 for i in range(180)], start_date="2023-01-02")

    def test_same_contract_returns_400(self):
        resp = client.post("/api/analyze", json={
            "contract_a": {"code": "159985", "contract_type": "ETF"},
            "contract_b": {"code": "159985", "contract_type": "ETF"},
        })
        assert resp.status_code == 400

    def test_same_code_different_type_ok(self):
        """Same code but different type should not be rejected."""
        with patch("backend.api.fetch_contract_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = self._mock_df()
            resp = client.post("/api/analyze", json={
                "contract_a": {"code": "159985", "contract_type": "ETF"},
                "contract_b": {"code": "159985", "contract_type": "期货主力连续"},
            })
            assert resp.status_code == 200

    @patch("backend.api.fetch_contract_data", new_callable=AsyncMock)
    def test_success_response_structure(self, mock_fetch):
        mock_fetch.return_value = self._mock_df()
        resp = client.post("/api/analyze", json={
            "contract_a": {"code": "159985", "contract_type": "ETF"},
            "contract_b": {"code": "M0", "contract_type": "期货主力连续"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "basic_info_a" in data
        assert "basic_info_b" in data
        assert "charts_data" in data
        assert "contract_a_name" in data
        assert "contract_b_name" in data

    @patch("backend.api.fetch_contract_data", new_callable=AsyncMock)
    def test_data_fetch_error_returns_500(self, mock_fetch):
        mock_fetch.side_effect = DataFetchError("159985", "接口超时")
        resp = client.post("/api/analyze", json={
            "contract_a": {"code": "159985", "contract_type": "ETF"},
            "contract_b": {"code": "M0", "contract_type": "期货主力连续"},
        })
        assert resp.status_code == 500

    @patch("backend.api.run_full_analysis")
    @patch("backend.api.fetch_contract_data", new_callable=AsyncMock)
    def test_analysis_error_returns_500(self, mock_fetch, mock_analysis):
        mock_fetch.return_value = self._mock_df()
        mock_analysis.side_effect = AnalysisError("correlation", "数据不足")
        resp = client.post("/api/analyze", json={
            "contract_a": {"code": "159985", "contract_type": "ETF"},
            "contract_b": {"code": "M0", "contract_type": "期货主力连续"},
        })
        assert resp.status_code == 500

    def test_missing_fields_returns_422(self):
        """Pydantic validation error for missing required fields."""
        resp = client.post("/api/analyze", json={
            "contract_a": {"code": "159985"},
        })
        assert resp.status_code == 422
