"""分析引擎（全部计算逻辑）"""

import numpy as np
import pandas as pd

from backend.models import (
    AnalysisResponse,
    AnnualReturn,
    ArbitrageAnalysis,
    BasicInfo,
    ContractInput,
    CorrelationInfo,
    DrawdownInfo,
    MonthlyReturnInfo,
    PriceRatioSpreadInfo,
    TimeSeriesData,
    TrendInfo,
    VolatilityInfo,
    VolumeTrendInfo,
)


def calc_basic_info(df: pd.DataFrame, contract_type: str) -> BasicInfo:
    """
    计算单合约基本行情指标。

    参数:
        df: 统一列名 DataFrame [date, open, close, high, low, volume, amount, open_interest]
        contract_type: "ETF" 或 "期货主力连续"

    返回:
        BasicInfo 模型实例
    """
    date_range = [
        str(df["date"].iloc[0].date()),
        str(df["date"].iloc[-1].date()),
    ]
    start_price = float(df["close"].iloc[0])
    latest_price = float(df["close"].iloc[-1])
    change_pct = (latest_price / start_price - 1) * 100
    high = float(df["high"].max())
    low = float(df["low"].min())
    avg_volume = float(df["volume"].mean())

    avg_amount = None
    avg_open_interest = None

    if contract_type in ("ETF", "A股股票", "美股", "港股"):
        avg_amount = float(df["amount"].mean())
    elif contract_type == "期货主力连续":
        avg_open_interest = float(df["open_interest"].mean())

    return BasicInfo(
        date_range=date_range,
        start_price=start_price,
        latest_price=latest_price,
        change_pct=round(change_pct, 4),
        high=high,
        low=low,
        avg_volume=round(avg_volume, 4),
        avg_amount=round(avg_amount, 4) if avg_amount is not None else None,
        avg_open_interest=round(avg_open_interest, 4) if avg_open_interest is not None else None,
    )


def calc_annual_returns(df: pd.DataFrame) -> dict[int, float]:
    """
    按自然年分组，计算每年收益率。

    收益率 = (该年最后一个交易日收盘价 / 该年第一个交易日收盘价 - 1) * 100

    返回:
        dict 映射 年份 -> 收益率百分比
    """
    df = df.copy()
    df["year"] = df["date"].dt.year
    result: dict[int, float] = {}
    for year in sorted(df["year"].unique()):
        year_df = df[df["year"] == year]
        if len(year_df) > 1:
            first_close = year_df["close"].iloc[0]
            last_close = year_df["close"].iloc[-1]
            ret = (last_close / first_close - 1) * 100
        else:
            ret = 0.0
        result[int(year)] = round(float(ret), 4)
    return result


def calc_volatility(df: pd.DataFrame) -> VolatilityInfo:
    """
    计算波动率指标。

    - 日收益率 = close.pct_change()
    - 年化波动率 = daily_return_std * sqrt(252) * 100
    - daily_return_mean 和 daily_return_std 以百分比表示

    返回:
        VolatilityInfo 模型实例
    """
    daily_returns = df["close"].pct_change().dropna()
    daily_return_mean = float(daily_returns.mean() * 100)
    daily_return_std = float(daily_returns.std() * 100)
    annualized_vol = float(daily_returns.std() * np.sqrt(252) * 100)

    return VolatilityInfo(
        annualized_vol=round(annualized_vol, 4),
        daily_return_mean=round(daily_return_mean, 4),
        daily_return_std=round(daily_return_std, 4),
    )


def calc_max_drawdown(df: pd.DataFrame) -> DrawdownInfo:
    """
    使用扩展窗口最大值法计算最大回撤。

    - peak = close.expanding().max()
    - drawdown = (close - peak) / peak
    - 记录高点/低点的日期和价格

    返回:
        DrawdownInfo 模型实例
    """
    prices = df["close"]
    dates = df["date"]

    peak = prices.expanding().max()
    drawdown = (prices - peak) / peak

    trough_idx = drawdown.idxmin()
    trough_price = float(prices.loc[trough_idx])
    trough_date = str(dates.loc[trough_idx].date())

    # 高点是从序列起始到低点之间的最大值位置
    peak_idx = prices.loc[: trough_idx].idxmax()
    peak_price = float(prices.loc[peak_idx])
    peak_date = str(dates.loc[peak_idx].date())

    max_drawdown_pct = float(drawdown.min() * 100)

    return DrawdownInfo(
        max_drawdown_pct=round(max_drawdown_pct, 4),
        peak_date=peak_date,
        peak_price=peak_price,
        trough_date=trough_date,
        trough_price=trough_price,
    )


def calc_correlation(df_a: pd.DataFrame, df_b: pd.DataFrame) -> CorrelationInfo:
    """
    计算两个合约之间的相关性指标。

    - 基于重叠交易日（inner join on date）
    - 价格相关系数：Pearson on close prices
    - 收益率相关系数：Pearson on daily returns
    - 60日滚动收益率相关系数：均值/最小值/最大值（排除NaN）

    返回:
        CorrelationInfo 模型实例
    """
    merged = pd.merge(
        df_a[["date", "close"]].rename(columns={"close": "close_a"}),
        df_b[["date", "close"]].rename(columns={"close": "close_b"}),
        on="date",
        how="inner",
    )
    overlap_days = len(merged)

    # 价格相关系数
    price_corr = float(merged["close_a"].corr(merged["close_b"]))

    # 日收益率相关系数
    merged["return_a"] = merged["close_a"].pct_change()
    merged["return_b"] = merged["close_b"].pct_change()
    return_corr = float(merged["return_a"].corr(merged["return_b"]))

    # 60日滚动收益率相关系数
    rolling_corr = merged["return_a"].rolling(60).corr(merged["return_b"])
    rolling_clean = rolling_corr.dropna()
    rolling_corr_mean = float(rolling_clean.mean()) if len(rolling_clean) > 0 else 0.0
    rolling_corr_min = float(rolling_clean.min()) if len(rolling_clean) > 0 else 0.0
    rolling_corr_max = float(rolling_clean.max()) if len(rolling_clean) > 0 else 0.0

    return CorrelationInfo(
        overlap_days=overlap_days,
        price_corr=round(price_corr, 4),
        return_corr=round(return_corr, 4),
        rolling_corr_mean=round(rolling_corr_mean, 4),
        rolling_corr_min=round(rolling_corr_min, 4),
        rolling_corr_max=round(rolling_corr_max, 4),
    )


def calc_trend(df: pd.DataFrame) -> TrendInfo:
    """
    计算近期趋势信息。

    - recent_changes: 近5日/20日/60日涨跌幅
    - ma_values: MA5/MA20/MA60/MA120 均线值
    - latest_price: 最新收盘价
    - trend_status: 基于均线排列判断趋势

    返回:
        TrendInfo 模型实例
    """
    closes = df["close"]
    latest = float(closes.iloc[-1])

    # 近期涨跌幅
    recent_changes: dict[str, float] = {}
    for days, label in [(5, "5d"), (20, "20d"), (60, "60d")]:
        if len(closes) >= days:
            pct = (latest / float(closes.iloc[-days]) - 1) * 100
            recent_changes[label] = round(pct, 4)
        else:
            recent_changes[label] = 0.0

    # 均线值
    ma5 = float(closes.tail(5).mean())
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(60).mean())
    ma120 = float(closes.tail(120).mean())
    ma_values = {
        "MA5": round(ma5, 4),
        "MA20": round(ma20, 4),
        "MA60": round(ma60, 4),
        "MA120": round(ma120, 4),
    }

    # 趋势状态判断
    if latest > ma5 > ma20 > ma60:
        trend_status = "多头排列"
    elif latest < ma5 < ma20 < ma60:
        trend_status = "空头排列"
    elif latest > ma20 and ma5 > ma20:
        trend_status = "短期偏多"
    elif latest < ma20 and ma5 < ma20:
        trend_status = "短期偏空"
    else:
        trend_status = "震荡整理"

    return TrendInfo(
        recent_changes=recent_changes,
        ma_values=ma_values,
        latest_price=latest,
        trend_status=trend_status,
    )


def calc_volume_trend(df: pd.DataFrame) -> VolumeTrendInfo:
    """
    计算成交量趋势。

    - 按月分组计算月均成交量
    - recent_3m_avg: 最近3个月月均成交量的平均
    - prev_3m_avg: 最早3个月月均成交量的平均
    - change_pct: (recent / prev - 1) * 100

    返回:
        VolumeTrendInfo 模型实例
    """
    df_copy = df.copy()
    df_copy["month"] = df_copy["date"].dt.to_period("M")
    monthly_vol = df_copy.groupby("month")["volume"].mean()

    recent_3m_avg = float(monthly_vol.tail(3).mean())
    prev_3m_avg = float(monthly_vol.head(3).mean())
    change_pct = (recent_3m_avg / prev_3m_avg - 1) * 100 if prev_3m_avg != 0 else 0.0

    return VolumeTrendInfo(
        recent_3m_avg=round(recent_3m_avg, 4),
        prev_3m_avg=round(prev_3m_avg, 4),
        change_pct=round(change_pct, 4),
    )


def calc_price_ratio_spread(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    weight_a: float,
    weight_b: float,
) -> PriceRatioSpreadInfo:
    """
    计算价比和价差。

    - price_ratio = (close_a * weight_a) / (close_b * weight_b)
    - price_spread = close_a * weight_a - close_b * weight_b
    - 返回 ratio 的 latest/mean/max/min，spread 的 latest/mean

    返回:
        PriceRatioSpreadInfo 模型实例
    """
    merged = pd.merge(
        df_a[["date", "close"]].rename(columns={"close": "close_a"}),
        df_b[["date", "close"]].rename(columns={"close": "close_b"}),
        on="date",
        how="inner",
    )

    ratio = (merged["close_a"] * weight_a) / (merged["close_b"] * weight_b)
    spread = merged["close_a"] * weight_a - merged["close_b"] * weight_b

    return PriceRatioSpreadInfo(
        latest_ratio=round(float(ratio.iloc[-1]), 4),
        mean_ratio=round(float(ratio.mean()), 4),
        max_ratio=round(float(ratio.max()), 4),
        min_ratio=round(float(ratio.min()), 4),
        latest_spread=round(float(spread.iloc[-1]), 4),
        mean_spread=round(float(spread.mean()), 4),
    )


def calc_monthly_returns(df: pd.DataFrame) -> MonthlyReturnInfo:
    """
    计算月度收益统计。

    - 按自然月分组，月度收益 = (月末收盘价 / 月初收盘价 - 1) * 100
    - avg_monthly_return: 月均收益率
    - positive_months_ratio: "N/M" 格式
    - max_monthly_return / min_monthly_return

    返回:
        MonthlyReturnInfo 模型实例
    """
    df_copy = df.copy()
    df_copy["month_str"] = df_copy["date"].dt.to_period("M").astype(str)

    monthly = df_copy.groupby("month_str")["close"].agg(["first", "last"])
    monthly["return"] = (monthly["last"] / monthly["first"] - 1) * 100

    avg_monthly_return = float(monthly["return"].mean())
    positive_count = int((monthly["return"] > 0).sum())
    total_count = len(monthly)
    positive_months_ratio = f"{positive_count}/{total_count}"
    max_monthly_return = float(monthly["return"].max())
    min_monthly_return = float(monthly["return"].min())

    return MonthlyReturnInfo(
        avg_monthly_return=round(avg_monthly_return, 4),
        positive_months_ratio=positive_months_ratio,
        max_monthly_return=round(max_monthly_return, 4),
        min_monthly_return=round(min_monthly_return, 4),
    )


def calc_arbitrage_analysis(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    weight_a: float,
    weight_b: float,
    correlation: CorrelationInfo,
) -> ArbitrageAnalysis:
    """基于相关性、百分位和Z-score生成套利分析建议。"""
    merged = pd.merge(
        df_a[["date", "close"]].rename(columns={"close": "close_a"}),
        df_b[["date", "close"]].rename(columns={"close": "close_b"}),
        on="date", how="inner",
    )
    ratio = (merged["close_a"] * weight_a) / (merged["close_b"] * weight_b)
    spread = merged["close_a"] * weight_a - merged["close_b"] * weight_b

    latest_ratio = float(ratio.iloc[-1])
    latest_spread = float(spread.iloc[-1])

    from scipy.stats import percentileofscore
    ratio_pct = round(float(percentileofscore(ratio, latest_ratio)), 2)
    spread_pct = round(float(percentileofscore(spread, latest_spread)), 2)

    ratio_z = round(float((latest_ratio - ratio.mean()) / ratio.std()), 4) if ratio.std() > 0 else 0.0
    spread_z = round(float((latest_spread - spread.mean()) / spread.std()), 4) if spread.std() > 0 else 0.0

    # 相关性水平
    corr = correlation.return_corr
    if corr > 0.8:
        corr_level = "强正相关"
    elif corr > 0.5:
        corr_level = "中等正相关"
    elif corr > 0.2:
        corr_level = "弱正相关"
    elif corr > -0.2:
        corr_level = "不相关"
    elif corr > -0.5:
        corr_level = "弱负相关"
    else:
        corr_level = "强负相关"

    # 生成建议
    details = []
    if corr < 0.3:
        suggestion = "⚠️ 不建议配对交易"
        details.append(f"两品种收益率相关性仅{corr:.2f}（{corr_level}），不满足配对交易的基本前提。")
    else:
        if spread_pct > 85 or ratio_pct > 85:
            suggestion = "📉 价差/价比偏高，关注做空价差机会"
            details.append(f"当前价差处于历史{spread_pct:.0f}%分位，价比处于{ratio_pct:.0f}%分位，显著高于均值。")
            details.append("若两品种保持较强相关性，价差有均值回归的可能，可关注做空A/做多B的配对机会。")
        elif spread_pct < 15 or ratio_pct < 15:
            suggestion = "📈 价差/价比偏低，关注做多价差机会"
            details.append(f"当前价差处于历史{spread_pct:.0f}%分位，价比处于{ratio_pct:.0f}%分位，显著低于均值。")
            details.append("若两品种保持较强相关性，价差有均值回归的可能，可关注做多A/做空B的配对机会。")
        else:
            suggestion = "⏸️ 价差处于正常区间，暂无明显套利信号"
            details.append(f"当前价差处于历史{spread_pct:.0f}%分位，价比处于{ratio_pct:.0f}%分位，接近均值水平。")

        if abs(spread_z) > 2:
            details.append(f"价差Z-score为{spread_z:.2f}，偏离均值超过2个标准差，信号较强。")
        elif abs(spread_z) > 1:
            details.append(f"价差Z-score为{spread_z:.2f}，偏离均值1-2个标准差，信号中等。")

    return ArbitrageAnalysis(
        ratio_percentile=ratio_pct,
        spread_percentile=spread_pct,
        correlation_level=corr_level,
        ratio_zscore=ratio_z,
        spread_zscore=spread_z,
        suggestion=suggestion,
        detail=" ".join(details),
    )


# ── 显示名称映射 ────────────────────────────────────────────

_CONTRACT_TYPE_DISPLAY = {
    "ETF": "ETF",
    "期货主力连续": "主力连续",
    "A股股票": "A股",
    "美股": "美股",
    "港股": "港股",
}


def _build_display_name(contract: ContractInput, resolved_name: str) -> str:
    """构建合约显示名称。使用查询到的名称。"""
    suffix = _CONTRACT_TYPE_DISPLAY.get(contract.contract_type, contract.contract_type)
    if resolved_name and resolved_name != contract.code:
        return f"{resolved_name}({contract.code})"
    return f"{suffix}({contract.code})"


def _calc_monthly_return_series(df: pd.DataFrame) -> tuple[list[str], list[float]]:
    """计算月度收益率序列，返回 (months, returns)。"""
    df_copy = df.copy()
    df_copy["month_str"] = df_copy["date"].dt.to_period("M").astype(str)
    monthly = df_copy.groupby("month_str")["close"].agg(["first", "last"])
    monthly["return"] = (monthly["last"] / monthly["first"] - 1) * 100
    months = monthly.index.tolist()
    returns = [round(float(r), 4) for r in monthly["return"]]
    return months, returns


def run_full_analysis(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    contract_a: ContractInput,
    contract_b: ContractInput,
    name_a: str = "",
    name_b: str = "",
) -> AnalysisResponse:
    """
    执行全部分析维度，返回 AnalysisResponse。

    参数:
        df_a: 合约A的统一列名 DataFrame
        df_b: 合约B的统一列名 DataFrame
        contract_a: 合约A输入参数
        contract_b: 合约B输入参数

    返回:
        AnalysisResponse 包含所有分析结果和图表数据
    """
    weight_a = contract_a.weight
    weight_b = contract_b.weight

    # ── 各维度分析 ──────────────────────────────────────────
    basic_info_a = calc_basic_info(df_a, contract_a.contract_type)
    basic_info_b = calc_basic_info(df_b, contract_b.contract_type)

    annual_returns_a = calc_annual_returns(df_a)
    annual_returns_b = calc_annual_returns(df_b)

    volatility_a = calc_volatility(df_a)
    volatility_b = calc_volatility(df_b)

    drawdown_a = calc_max_drawdown(df_a)
    drawdown_b = calc_max_drawdown(df_b)

    correlation = calc_correlation(df_a, df_b)

    trend_a = calc_trend(df_a)
    trend_b = calc_trend(df_b)

    volume_trend_a = calc_volume_trend(df_a)
    volume_trend_b = calc_volume_trend(df_b)

    price_ratio_spread = calc_price_ratio_spread(df_a, df_b, weight_a, weight_b)

    arbitrage_analysis = calc_arbitrage_analysis(df_a, df_b, weight_a, weight_b, correlation)

    monthly_return_a = calc_monthly_returns(df_a)
    monthly_return_b = calc_monthly_returns(df_b)

    # ── 合并年度收益率 ──────────────────────────────────────
    all_years = sorted(set(annual_returns_a.keys()) | set(annual_returns_b.keys()))
    annual_returns = [
        AnnualReturn(
            year=year,
            return_a=annual_returns_a.get(year, 0.0),
            return_b=annual_returns_b.get(year, 0.0),
        )
        for year in all_years
    ]

    # ── 构建 TimeSeriesData ─────────────────────────────────

    # 合约A: 日期、价格、MA20、MA60
    dates_a = [str(d.date()) for d in df_a["date"]]
    prices_a = [float(p) for p in df_a["close"]]
    ma20_a_series = df_a["close"].rolling(20).mean()
    ma60_a_series = df_a["close"].rolling(60).mean()
    ma20_a = [None if pd.isna(v) else round(float(v), 4) for v in ma20_a_series]
    ma60_a = [None if pd.isna(v) else round(float(v), 4) for v in ma60_a_series]

    # 合约B: 日期、价格、MA20、MA60
    dates_b = [str(d.date()) for d in df_b["date"]]
    prices_b = [float(p) for p in df_b["close"]]
    ma20_b_series = df_b["close"].rolling(20).mean()
    ma60_b_series = df_b["close"].rolling(60).mean()
    ma20_b = [None if pd.isna(v) else round(float(v), 4) for v in ma20_b_series]
    ma60_b = [None if pd.isna(v) else round(float(v), 4) for v in ma60_b_series]

    # 重叠日期数据 (inner join)
    merged = pd.merge(
        df_a[["date", "close"]].rename(columns={"close": "close_a"}),
        df_b[["date", "close"]].rename(columns={"close": "close_b"}),
        on="date",
        how="inner",
    )
    overlap_dates = [str(d.date()) for d in merged["date"]]
    price_ratio = [
        round(float(a * weight_a / (b * weight_b)), 4)
        for a, b in zip(merged["close_a"], merged["close_b"])
    ]
    price_spread = [
        round(float(a * weight_a - b * weight_b), 4)
        for a, b in zip(merged["close_a"], merged["close_b"])
    ]
    ratio_mean = round(float(np.mean(price_ratio)), 4) if price_ratio else 0.0
    spread_mean = round(float(np.mean(price_spread)), 4) if price_spread else 0.0

    # 归一化价格 (基准=100，基于重叠日期的第一个交易日)
    if len(merged) > 0:
        base_a = float(merged["close_a"].iloc[0])
        base_b = float(merged["close_b"].iloc[0])
        norm_prices_a = [
            round(float(p / base_a * 100), 4) for p in merged["close_a"]
        ]
        norm_prices_b = [
            round(float(p / base_b * 100), 4) for p in merged["close_b"]
        ]
    else:
        norm_prices_a = []
        norm_prices_b = []

    # 60日滚动相关性
    if len(merged) > 1:
        merged["return_a"] = merged["close_a"].pct_change()
        merged["return_b"] = merged["close_b"].pct_change()
        rolling_corr_series = merged["return_a"].rolling(60).corr(merged["return_b"])
        rolling_corr = [
            None if pd.isna(v) else round(float(v), 4) for v in rolling_corr_series
        ]
        clean = rolling_corr_series.dropna()
        rolling_corr_mean = round(float(clean.mean()), 4) if len(clean) > 0 else 0.0
    else:
        rolling_corr = []
        rolling_corr_mean = 0.0

    # 月度收益序列
    months_a, monthly_returns_a_list = _calc_monthly_return_series(df_a)
    months_b, monthly_returns_b_list = _calc_monthly_return_series(df_b)

    # 合并月度数据（取并集，缺失填0）
    all_months = sorted(set(months_a) | set(months_b))
    dict_a = dict(zip(months_a, monthly_returns_a_list))
    dict_b = dict(zip(months_b, monthly_returns_b_list))
    months = all_months
    monthly_returns_a_merged = [dict_a.get(m, 0.0) for m in all_months]
    monthly_returns_b_merged = [dict_b.get(m, 0.0) for m in all_months]

    charts_data = TimeSeriesData(
        dates_a=dates_a,
        prices_a=prices_a,
        ma20_a=ma20_a,
        ma60_a=ma60_a,
        dates_b=dates_b,
        prices_b=prices_b,
        ma20_b=ma20_b,
        ma60_b=ma60_b,
        overlap_dates=overlap_dates,
        price_ratio=price_ratio,
        price_spread=price_spread,
        ratio_mean=ratio_mean,
        spread_mean=spread_mean,
        norm_prices_a=norm_prices_a,
        norm_prices_b=norm_prices_b,
        rolling_corr=rolling_corr,
        rolling_corr_mean=rolling_corr_mean,
        months=months,
        monthly_returns_a=monthly_returns_a_merged,
        monthly_returns_b=monthly_returns_b_merged,
    )

    # ── 显示名称 ────────────────────────────────────────────
    contract_a_name = _build_display_name(contract_a, name_a)
    contract_b_name = _build_display_name(contract_b, name_b)

    return AnalysisResponse(
        basic_info_a=basic_info_a,
        basic_info_b=basic_info_b,
        annual_returns=annual_returns,
        volatility_a=volatility_a,
        volatility_b=volatility_b,
        drawdown_a=drawdown_a,
        drawdown_b=drawdown_b,
        correlation=correlation,
        trend_a=trend_a,
        trend_b=trend_b,
        volume_trend_a=volume_trend_a,
        volume_trend_b=volume_trend_b,
        price_ratio_spread=price_ratio_spread,
        arbitrage_analysis=arbitrage_analysis,
        monthly_return_a=monthly_return_a,
        monthly_return_b=monthly_return_b,
        charts_data=charts_data,
        contract_a_name=contract_a_name,
        contract_b_name=contract_b_name,
    )
