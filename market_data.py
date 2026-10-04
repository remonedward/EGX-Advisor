"""Yahoo Finance history + deterministic technical indicators, freshness and cross-checks."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from config import CAIRO_TZ, HISTORY_PERIOD, STALE_TRADING_DAYS

EGX_TRADING_WEEKDAYS = {6, 0, 1, 2, 3}  # Sun..Thu (Python: Mon=0 ... Sun=6)


def yahoo_symbol(ticker: str) -> str:
    return f"{ticker.upper()}.CA"


def normalize_ticker(raw: str) -> str:
    t = (raw or "").strip().upper()
    if t.startswith("EGX:"):
        t = t[4:]
    if t.endswith(".CA"):
        t = t[:-3]
    return t


def fetch_history_raw(ticker: str, period: str = HISTORY_PERIOD) -> pd.DataFrame:
    df = yf.Ticker(yahoo_symbol(ticker)).history(period=period, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert(CAIRO_TZ).tz_localize(None)
    df.index = idx.normalize()
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["Close"])
    return df


@st.cache_data(ttl=900, show_spinner=False)
def fetch_history(ticker: str, period: str = HISTORY_PERIOD) -> pd.DataFrame:
    return fetch_history_raw(ticker, period)


# ---------------------------------------------------------------- indicators
def _wilder(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), n)
    loss = _wilder(-delta.clip(upper=0), n)
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["Close"].shift()
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _wilder(tr, n)


def add_chart_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["SMA20"] = out["Close"].rolling(20).mean()
    out["SMA50"] = out["Close"].rolling(50).mean()
    return out


def _f(x) -> float | None:
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, 4)


def compute_indicators(df: pd.DataFrame) -> dict:
    close = df["Close"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    last, prev = close.iloc[-1], (close.iloc[-2] if len(close) > 1 else close.iloc[-1])

    def window(n: int):
        w = df.tail(n)
        return _f(w["High"].max()), _f(w["Low"].min())

    h20, l20 = window(20)
    h60, l60 = window(60)
    h252, l252 = window(252)
    return {
        "last_session_date": df.index[-1].date().isoformat(),
        "sessions_available": int(len(df)),
        "last_close": _f(last),
        "prev_close": _f(prev),
        "change_abs": _f(last - prev),
        "change_pct": _f((last - prev) / prev * 100 if prev else None),
        "volume": int(df["Volume"].iloc[-1]) if not pd.isna(df["Volume"].iloc[-1]) else None,
        "avg_volume_20": _f(df["Volume"].tail(20).mean()),
        "sma20": _f(close.rolling(20).mean().iloc[-1]) if len(df) >= 20 else None,
        "sma50": _f(close.rolling(50).mean().iloc[-1]) if len(df) >= 50 else None,
        "sma200": _f(close.rolling(200).mean().iloc[-1]) if len(df) >= 200 else None,
        "rsi14": _f(rsi(close).iloc[-1]),
        "macd": _f(macd.iloc[-1]),
        "macd_signal": _f(signal.iloc[-1]),
        "macd_hist": _f(macd.iloc[-1] - signal.iloc[-1]),
        "atr14": _f(atr(df).iloc[-1]),
        "high_20": h20, "low_20": l20,
        "high_60": h60, "low_60": l60,
        "high_252": h252, "low_252": l252,
        "perf_1m_pct": _f((last / close.iloc[-21] - 1) * 100) if len(df) > 21 else None,
        "perf_3m_pct": _f((last / close.iloc[-63] - 1) * 100) if len(df) > 63 else None,
    }


def candidate_levels(ind: dict, price: float) -> dict:
    """Deterministic candidate price levels the LLM must choose from / justify against."""
    a = ind.get("atr14") or 0
    supports = sorted({v for v in (ind.get("low_20"), ind.get("low_60"), ind.get("low_252"),
                                   ind.get("sma50"), ind.get("sma200")) if v and v < price}, reverse=True)
    resistances = sorted({v for v in (ind.get("high_20"), ind.get("high_60"), ind.get("high_252"),
                                      ind.get("sma50"), ind.get("sma200")) if v and v > price})
    return {
        "supports_below_price": [round(v, 2) for v in supports],
        "resistances_above_price": [round(v, 2) for v in resistances],
        "atr_stop_long": round(price - 2 * a, 2) if a else None,
        "atr_target_long": round(price + 3 * a, 2) if a else None,
        "atr_stop_short": round(price + 2 * a, 2) if a else None,
        "atr_target_short": round(price - 3 * a, 2) if a else None,
    }


# ------------------------------------------------------------ freshness
def trading_days_between(start_exclusive: date, end_inclusive: date) -> int:
    days, d = 0, start_exclusive + timedelta(days=1)
    while d <= end_inclusive:
        if d.weekday() in EGX_TRADING_WEEKDAYS:
            days += 1
        d += timedelta(days=1)
    return days


def freshness(last_session: date, now: datetime) -> tuple[int, bool]:
    """Sessions missed since the last bar. Today's session counts only after the close (~15:00 Cairo).
    Holidays are not modelled, hence the tolerant threshold."""
    end = now.date() if now.hour >= 15 else now.date() - timedelta(days=1)
    missed = trading_days_between(last_session, end) if end > last_session else 0
    return missed, missed >= STALE_TRADING_DAYS


# ------------------------------------------------------------ cross-check
def cross_check(ind: dict, tv: dict | None) -> tuple[list[dict], list[str]]:
    """Compare Yahoo-derived indicators against TradingView. Returns (table_rows, warnings).
    Small gaps are expected because TradingView includes today's (partial) session."""
    if not tv:
        return [], ["تعذر الوصول إلى TradingView — لم يتم التحقق المتبادل من البيانات."]
    pairs = [
        ("SMA20", ind.get("sma20"), tv.get("SMA20"), "pct", 3.0),
        ("SMA50", ind.get("sma50"), tv.get("SMA50"), "pct", 3.0),
        ("SMA200", ind.get("sma200"), tv.get("SMA200"), "pct", 3.0),
        ("RSI14", ind.get("rsi14"), tv.get("RSI"), "abs", 8.0),
        ("ATR14", ind.get("atr14"), tv.get("ATR"), "pct", 25.0),
    ]
    tv_close, tv_chg = tv.get("close"), tv.get("change_abs")
    tv_prev = (tv_close - tv_chg) if tv_close is not None and tv_chg is not None else None
    pairs.insert(0, ("إغلاق سابق/أخير", ind.get("last_close"), tv_prev, "pct", 1.5))

    rows, warnings = [], []
    for name, y, t, mode, tol in pairs:
        if y is None or t is None:
            continue
        diff = abs(y - t) if mode == "abs" else abs(y - t) / abs(t) * 100 if t else 0
        ok = diff <= tol
        rows.append({"المؤشر": name, "Yahoo": round(y, 2), "TradingView": round(t, 2),
                     "الفرق": f"{diff:.2f}{'' if mode == 'abs' else '%'}", "متطابق": "✅" if ok else "⚠️"})
        if not ok:
            warnings.append(f"فرق ملحوظ في {name} بين Yahoo ({y:.2f}) و TradingView ({t:.2f}).")
    return rows, warnings
