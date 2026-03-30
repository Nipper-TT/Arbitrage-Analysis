"""Pydantic 请求/响应数据模型 & 自定义异常"""

from pydantic import BaseModel


# ── 自定义异常 ──────────────────────────────────────────────

class DataFetchError(Exception):
    """AKShare 数据获取失败"""

    def __init__(self, code: str, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(f"获取合约 {code} 数据失败: {reason}")


class AnalysisError(Exception):
    """分析计算过程中的错误"""

    def __init__(self, step: str, reason: str):
        self.step = step
        self.reason = reason
        super().__init__(f"分析步骤 [{step}] 失败: {reason}")


# ── 请求模型 ────────────────────────────────────────────────

class ContractInput(BaseModel):
    code: str
    contract_type: str
    weight: float = 1.0


class AnalysisRequest(BaseModel):
    contract_a: ContractInput
    contract_b: ContractInput
    years: int = 3


# ── 响应模型 ────────────────────────────────────────────────

class BasicInfo(BaseModel):
    date_range: list[str]
    start_price: float
    latest_price: float
    change_pct: float
    high: float
    low: float
    avg_volume: float
    avg_amount: float | None = None
    avg_open_interest: float | None = None


class AnnualReturn(BaseModel):
    year: int
    return_a: float
    return_b: float


class VolatilityInfo(BaseModel):
    annualized_vol: float
    daily_return_mean: float
    daily_return_std: float


class DrawdownInfo(BaseModel):
    max_drawdown_pct: float
    peak_date: str
    peak_price: float
    trough_date: str
    trough_price: float


class CorrelationInfo(BaseModel):
    overlap_days: int
    price_corr: float
    return_corr: float
    rolling_corr_mean: float
    rolling_corr_min: float
    rolling_corr_max: float


class TrendInfo(BaseModel):
    recent_changes: dict[str, float]
    ma_values: dict[str, float]
    latest_price: float
    trend_status: str


class VolumeTrendInfo(BaseModel):
    recent_3m_avg: float
    prev_3m_avg: float
    change_pct: float


class PriceRatioSpreadInfo(BaseModel):
    latest_ratio: float
    mean_ratio: float
    max_ratio: float
    min_ratio: float
    latest_spread: float
    mean_spread: float


class ArbitrageAnalysis(BaseModel):
    ratio_percentile: float
    spread_percentile: float
    correlation_level: str
    ratio_zscore: float
    spread_zscore: float
    suggestion: str
    detail: str


class MonthlyReturnInfo(BaseModel):
    avg_monthly_return: float
    positive_months_ratio: str
    max_monthly_return: float
    min_monthly_return: float


class TimeSeriesData(BaseModel):
    """图表所需的时间序列数据"""
    dates_a: list[str]
    prices_a: list[float]
    ma20_a: list[float | None]
    ma60_a: list[float | None]
    dates_b: list[str]
    prices_b: list[float]
    ma20_b: list[float | None]
    ma60_b: list[float | None]
    # 价比价差（基于重叠日期）
    overlap_dates: list[str]
    price_ratio: list[float]
    price_spread: list[float]
    ratio_mean: float
    spread_mean: float
    # 归一化价格
    norm_prices_a: list[float]
    norm_prices_b: list[float]
    # 滚动相关性
    rolling_corr: list[float | None]
    rolling_corr_mean: float
    # 月度收益
    months: list[str]
    monthly_returns_a: list[float]
    monthly_returns_b: list[float]


class AnalysisResponse(BaseModel):
    basic_info_a: BasicInfo
    basic_info_b: BasicInfo
    annual_returns: list[AnnualReturn]
    volatility_a: VolatilityInfo
    volatility_b: VolatilityInfo
    drawdown_a: DrawdownInfo
    drawdown_b: DrawdownInfo
    correlation: CorrelationInfo
    trend_a: TrendInfo
    trend_b: TrendInfo
    volume_trend_a: VolumeTrendInfo
    volume_trend_b: VolumeTrendInfo
    price_ratio_spread: PriceRatioSpreadInfo
    arbitrage_analysis: ArbitrageAnalysis
    monthly_return_a: MonthlyReturnInfo
    monthly_return_b: MonthlyReturnInfo
    charts_data: TimeSeriesData
    contract_a_name: str
    contract_b_name: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
