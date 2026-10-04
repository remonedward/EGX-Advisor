"""TradingView public scanner client (unofficial endpoint).

Used for: the EGX symbol universe (with Arabic names), a ~15-min delayed live snapshot,
ready-made indicators for cross-checking, and the EGX30 index level.
Everything here is optional: callers must handle `None` / exceptions and fall back to Yahoo.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

SCAN_URL = "https://scanner.tradingview.com/egypt/scan"
SNAPSHOT_FILE = Path(__file__).parent / "data" / "egx_tickers.csv"
INDEX_SYMBOL = "EGX:EGX30"

SNAPSHOT_COLUMNS = [
    "close", "change", "change_abs", "open", "high", "low", "volume", "currency",
    "RSI", "SMA20", "SMA50", "SMA200", "ATR", "MACD.macd", "MACD.signal",
    "High.1M", "Low.1M", "price_52_week_high", "price_52_week_low",
    "Recommend.All", "Recommend.MA", "Recommend.Other",
    "Perf.W", "Perf.1M", "Perf.3M", "average_volume_30d_calc",
    "market_cap_basic", "price_earnings_ttm", "update_mode",
]


def _scan(payload: dict, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        SCAN_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_universe_raw() -> pd.DataFrame:
    """All EGX common stocks with English + Arabic names, sorted by market cap."""
    base = {
        "columns": ["name", "description", "sector", "industry", "market_cap_basic"],
        "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
        "range": [0, 1000],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
    }
    en = _scan(base)
    ar = _scan({**base, "columns": ["name", "description"], "options": {"lang": "ar"}})
    ar_names = {row["s"]: row["d"][1] for row in ar.get("data", [])}
    rows = []
    for row in en.get("data", []):
        symbol = row["s"]
        if not symbol.startswith("EGX:"):
            continue
        name, desc, sector, industry, mcap = row["d"]
        rows.append({
            "ticker": name,
            "name_en": desc or name,
            "name_ar": ar_names.get(symbol) or desc or name,
            "sector": sector or "",
            "industry": industry or "",
            "market_cap": mcap,
        })
    df = pd.DataFrame(rows).drop_duplicates("ticker")
    if df.empty:
        raise RuntimeError("TradingView returned an empty EGX universe")
    return df.reset_index(drop=True)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_universe() -> tuple[pd.DataFrame, str]:
    """Live universe from TradingView, falling back to the bundled CSV snapshot."""
    try:
        return fetch_universe_raw(), "TradingView (مباشر)"
    except Exception:
        df = pd.read_csv(SNAPSHOT_FILE, dtype={"ticker": str})
        return df, "نسخة محفوظة محلياً"


def _fetch_snapshot_raw(symbols: list[str]) -> dict[str, dict]:
    data = _scan({"symbols": {"tickers": symbols}, "columns": SNAPSHOT_COLUMNS})
    return {row["s"]: dict(zip(SNAPSHOT_COLUMNS, row["d"])) for row in data.get("data", [])}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_snapshot(ticker: str) -> tuple[dict | None, dict | None, str | None]:
    """Return (stock_snapshot, egx30_snapshot, error_message)."""
    try:
        snaps = _fetch_snapshot_raw([f"EGX:{ticker}", INDEX_SYMBOL])
        return snaps.get(f"EGX:{ticker}"), snaps.get(INDEX_SYMBOL), None
    except Exception as exc:  # network error, endpoint change, block...
        return None, None, f"{type(exc).__name__}: {exc}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_index_level() -> float | None:
    try:
        snap = _fetch_snapshot_raw([INDEX_SYMBOL]).get(INDEX_SYMBOL) or {}
        return snap.get("close")
    except Exception:
        return None
