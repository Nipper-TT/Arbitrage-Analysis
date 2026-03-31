"""AKShare 数据获取封装"""

import os
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

import time

from backend.models import DataFetchError

# ── 缓存目录 ────────────────────────────────────────────────

_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

_CACHE_MAX_AGE_HOURS = 4  # 缓存有效期（小时）


def _cache_path(code: str, contract_type: str, years: int) -> str:
    safe_code = code.replace(".", "_")
    safe_type = contract_type.replace(" ", "_")
    return os.path.join(_CACHE_DIR, f"{safe_type}_{safe_code}_{years}y.parquet")


def _read_cache(code: str, contract_type: str, years: int) -> pd.DataFrame | None:
    path = _cache_path(code, contract_type, years)
    if not os.path.exists(path):
        return None
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    if age_hours > _CACHE_MAX_AGE_HOURS:
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _write_cache(df: pd.DataFrame, code: str, contract_type: str, years: int) -> None:
    try:
        df.to_parquet(_cache_path(code, contract_type, years), index=False)
    except Exception:
        pass

# ── 列名映射 ────────────────────────────────────────────────

_ETF_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}

_FUTURES_COLUMN_MAP = {
    "日期": "date",
    "开盘价": "open",
    "收盘价": "close",
    "最高价": "high",
    "最低价": "low",
    "成交量": "volume",
    "持仓量": "open_interest",
}

# ── 新浪备用接口列名映射（stock_zh_a_daily 返回英文列名，但需要统一格式）──
_SINA_COLUMN_MAP = {
    "date": "date",
    "open": "open",
    "close": "close",
    "high": "high",
    "low": "low",
    "volume": "volume",
    "amount": "amount",
}

# ── 统一列集合 ──────────────────────────────────────────────

_UNIFIED_COLUMNS = [
    "date", "open", "close", "high", "low",
    "volume", "amount", "open_interest",
]


def _ensure_unified_columns(df: pd.DataFrame) -> pd.DataFrame:
    """确保 DataFrame 包含所有统一列，缺失列填充 NaN。"""
    for col in _UNIFIED_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[_UNIFIED_COLUMNS]


def _fetch_sina_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """
    新浪财经备用接口 (stock_zh_a_daily)。
    symbol 格式: sh600519 / sz000001 / sh510300
    返回统一列名 DataFrame，失败返回 None。
    """
    # 根据代码推断交易所前缀
    if code.startswith(("6", "5")):
        symbol = f"sh{code}"
    elif code.startswith(("0", "1", "3")):
        symbol = f"sz{code}"
    else:
        return None
    try:
        df = ak.stock_zh_a_daily(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        if df is not None and not df.empty:
            # 新浪接口列名已是英文，直接选取需要的列
            df = df.rename(columns=_SINA_COLUMN_MAP)
            return df
    except Exception:
        pass
    return None


def _filter_recent_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    """过滤近 N 年数据。"""
    cutoff = datetime.now() - timedelta(days=years * 365)
    df["date"] = pd.to_datetime(df["date"])
    return df[df["date"] >= cutoff].reset_index(drop=True)


# ── ETF 数据获取 ────────────────────────────────────────────

def _fetch_etf(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取 ETF 日线数据。
    优先 stock_zh_a_hist → 回退 fund_etf_hist_em → 最终备用 stock_zh_a_daily(新浪)。
    """
    # 尝试1: 东方财富 stock_zh_a_hist
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(3)
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if df is not None and not df.empty:
                return df.rename(columns=_ETF_COLUMN_MAP)
        except Exception:
            pass

    # 尝试2: 东方财富 fund_etf_hist_em
    for attempt in range(2):
        try:
            if attempt > 0:
                time.sleep(3)
            df = ak.fund_etf_hist_em(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if df is not None and not df.empty:
                return df.rename(columns=_ETF_COLUMN_MAP)
        except Exception:
            pass

    # 尝试3: 新浪备用
    df = _fetch_sina_daily(code, start_date, end_date)
    if df is not None and not df.empty:
        return df

    raise DataFetchError(code, "ETF 所有接口均失败（东方财富+新浪）")


# ── 期货数据获取 ────────────────────────────────────────────

def _fetch_futures(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取期货主力连续日线数据。"""
    try:
        df = ak.futures_main_sina(
            symbol=code,
            start_date=start_date,
            end_date=end_date,
        )
        if df is not None and not df.empty:
            return df.rename(columns=_FUTURES_COLUMN_MAP)
    except Exception as exc:
        raise DataFetchError(code, f"期货接口调用失败: {exc}") from exc

    raise DataFetchError(code, "期货接口返回空数据")


# ── A股股票数据获取 ─────────────────────────────────────────

def _fetch_a_stock(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取A股股票日线数据。东方财富 → 新浪备用。"""
    # 尝试1: 东方财富
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(3)
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if df is not None and not df.empty:
                return df.rename(columns=_ETF_COLUMN_MAP)
        except Exception:
            pass

    # 尝试2: 新浪备用
    df = _fetch_sina_daily(code, start_date, end_date)
    if df is not None and not df.empty:
        return df

    raise DataFetchError(code, "A股所有接口均失败（东方财富+新浪）")


# ── 美股数据获取 ────────────────────────────────────────────

def _fetch_us_stock(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取美股日线数据，带重试。"""
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(3)
            df = ak.stock_us_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if df is not None and not df.empty:
                return df.rename(columns=_ETF_COLUMN_MAP)
        except Exception as exc:
            if attempt == 2:
                raise DataFetchError(code, f"美股接口调用失败: {exc}") from exc
    raise DataFetchError(code, "美股接口返回空数据")


# ── 港股数据获取 ────────────────────────────────────────────

def _fetch_hk_stock(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取港股日线数据，带重试。"""
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(3)
            df = ak.stock_hk_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if df is not None and not df.empty:
                return df.rename(columns=_ETF_COLUMN_MAP)
        except Exception as exc:
            if attempt == 2:
                raise DataFetchError(code, f"港股接口调用失败: {exc}") from exc
    raise DataFetchError(code, "港股接口返回空数据")


# ── 公共入口 ────────────────────────────────────────────────

def fetch_contract_name(code: str, contract_type: str) -> str:
    """根据合约代码和类型查询合约名称。查询失败时返回代码本身。"""
    try:
        if contract_type in ("ETF", "A股股票"):
            df = ak.stock_info_a_code_name()
            row = df[df["code"] == code]
            if not row.empty:
                return str(row.iloc[0]["name"])
        elif contract_type == "期货主力连续":
            df = ak.futures_display_main_sina()
            row = df[df["symbol"] == code]
            if not row.empty:
                return str(row.iloc[0]["name"]).replace("连续", "")
        elif contract_type == "美股":
            df = ak.stock_us_spot_em()
            # 美股代码格式如 105.AAPL，匹配"代码"列
            row = df[df["代码"] == code]
            if not row.empty:
                return str(row.iloc[0]["名称"])
        elif contract_type == "港股":
            df = ak.stock_hk_spot_em()
            # 港股代码如 09988，匹配"代码"列
            row = df[df["代码"] == code]
            if not row.empty:
                return str(row.iloc[0]["名称"])
    except Exception:
        pass
    return code


async def fetch_contract_data(
    code: str,
    contract_type: str,
    years: int = 3,
) -> pd.DataFrame:
    """
    根据合约类型获取日线数据，返回统一列名的 DataFrame。
    优先读取本地缓存（4小时有效），缓存未命中时调用接口并写入缓存。

    列: [date, open, close, high, low, volume, amount, open_interest]
    按日期升序排列，仅保留近 *years* 年数据。
    """
    # ── 尝试读缓存 ──────────────────────────────────────────
    cached = _read_cache(code, contract_type, years)
    if cached is not None and not cached.empty:
        cached["date"] = pd.to_datetime(cached["date"])
        return cached

    # ── 调用接口 ────────────────────────────────────────────
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")

    if contract_type == "ETF":
        df = _fetch_etf(code, start_date, end_date)
    elif contract_type == "期货主力连续":
        df = _fetch_futures(code, start_date, end_date)
    elif contract_type == "A股股票":
        df = _fetch_a_stock(code, start_date, end_date)
    elif contract_type == "美股":
        df = _fetch_us_stock(code, start_date, end_date)
    elif contract_type == "港股":
        df = _fetch_hk_stock(code, start_date, end_date)
    else:
        raise DataFetchError(code, f"不支持的合约类型: {contract_type}")

    # 统一列 & 过滤
    df = _ensure_unified_columns(df)
    df = _filter_recent_years(df, years)

    if df.empty:
        raise DataFetchError(code, "过滤后数据为空")

    # 按日期升序排列
    df = df.sort_values("date").reset_index(drop=True)

    # ── 写入缓存 ────────────────────────────────────────────
    _write_cache(df, code, contract_type, years)

    return df
