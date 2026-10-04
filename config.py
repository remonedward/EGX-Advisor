"""Central configuration: secrets access, constants and time helpers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

CAIRO_TZ = ZoneInfo("Africa/Cairo")
PROMPT_VERSION = "v1"

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_THINKING_LEVEL = "high"  # gemini-3.8-flash supports low / medium / high (minimal -> error)

NEWS_LOOKBACK_DAYS = 14
NEWS_MAX_ITEMS = 8
HISTORY_PERIOD = "1y"
CHART_DAYS = 63  # ~3 months of trading sessions
STALE_TRADING_DAYS = 3  # warn if the last bar is this many EGX sessions old (or more)

RECOMMENDATIONS = ["شراء قوي", "شراء", "احتفاظ", "بيع", "بيع قوي"]
BUY_RECS = {"شراء قوي", "شراء"}
SELL_RECS = {"بيع قوي", "بيع"}
HOLD_RECS = {"احتفاظ"}
SENTIMENTS = ["إيجابي", "سلبي", "محايد"]


def secret(key: str, default=None):
    """Read a value from st.secrets without crashing when no secrets file exists (local dev)."""
    try:
        return st.secrets.get(key, default)
    except Exception:  # StreamlitSecretNotFoundError / FileNotFoundError
        return default


def secret_bool(key: str, default: bool = False) -> bool:
    value = secret(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def gemini_model() -> str:
    return str(secret("GEMINI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL


def thinking_level() -> str:
    level = str(secret("GEMINI_THINKING_LEVEL", DEFAULT_THINKING_LEVEL)).strip().lower()
    return level if level in {"low", "medium", "high"} else DEFAULT_THINKING_LEVEL


def now_cairo() -> datetime:
    return datetime.now(CAIRO_TZ)
