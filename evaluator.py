"""Evaluation logic for past recommendations: strictly direction-aware, EGX30 comparison."""
from __future__ import annotations

import math

import pandas as pd


def safe_div(a: float, b: float) -> float | None:
    if not b or math.isnan(a) or math.isnan(b):
        return None
    return a / b


def evaluate_recommendation(
    rec_type: str,
    price_at_rec: float,
    target: float,
    stop: float,
    history_df: pd.DataFrame,
) -> tuple[str, float | None, str]:
    """
    Evaluates a recommendation against subsequent price bars.
    history_df must contain the bars strictly *after* the recommendation was made.
    Returns: (status, return_pct, note)
    Status: "SUCCESS", "FAILED", "PENDING"
    """
    if history_df.empty:
        return "PENDING", 0.0, "لم يمر وقت كافٍ"

    if rec_type in {"شراء قوي", "شراء"}:
        for _, row in history_df.iterrows():
            if row["Low"] <= stop and row["High"] >= target:
                return "FAILED", -100.0, "تم ضرب الهدف والوقف في نفس اليوم (فشل لغياب الأمان)"
            if row["High"] >= target:
                ret = safe_div(target - price_at_rec, price_at_rec) * 100
                return "SUCCESS", ret, "وصل للهدف"
            if row["Low"] <= stop:
                ret = safe_div(stop - price_at_rec, price_at_rec) * 100
                return "FAILED", ret, "ضرب الوقف"
        last = history_df["Close"].iloc[-1]
        ret = safe_div(last - price_at_rec, price_at_rec) * 100
        return "PENDING", ret, "انتهت المدة ولم يصل لأي منهما"

    if rec_type in {"بيع قوي", "بيع"}:
        for _, row in history_df.iterrows():
            if row["High"] >= stop and row["Low"] <= target:
                return "FAILED", -100.0, "تحرك في الاتجاهين"
            if row["Low"] <= target:
                ret = safe_div(price_at_rec - target, price_at_rec) * 100
                return "SUCCESS", ret, "نزل للهدف"
            if row["High"] >= stop:
                ret = safe_div(price_at_rec - stop, price_at_rec) * 100
                return "FAILED", ret, "ضرب الوقف صعوداً"
        last = history_df["Close"].iloc[-1]
        ret = safe_div(price_at_rec - last, price_at_rec) * 100
        return "PENDING", ret, "انتهت المدة"

    # Hold
    breached = False
    for _, row in history_df.iterrows():
        if not (stop < row["High"] and row["Low"] < target):
            breached = True
            break
    last = history_df["Close"].iloc[-1]
    ret = safe_div(last - price_at_rec, price_at_rec) * 100
    if breached:
        return "FAILED", ret, "خرج من نطاق الاحتفاظ"
    return "SUCCESS", ret, "استقر داخل النطاق"
