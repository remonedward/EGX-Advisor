"""Historical test script: Evaluates the system on past dates to verify recommendation accuracy."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import pandas as pd

import evaluator
import market_data


def test_historical_accuracy(tickers: list[str], test_days_ago: int = 30):
    print("=" * 60)
    print(f"فحص دقة التوصيات التاريخية (قبل {test_days_ago} يوم تداول)")
    print("=" * 60)

    results = []

    for ticker in tickers:
        print(f"\nجاري فحص السهم: {ticker} ...")
        df = market_data.fetch_history_raw(ticker, period="1y")
        if df.empty or len(df) <= test_days_ago:
            print(f"  ❌ لا توجد بيانات كافية للسهم {ticker}")
            continue

        # Split data: history up to test date, and outcome bars after that date
        past_bars = df.iloc[:-test_days_ago]
        future_bars = df.iloc[-test_days_ago:]

        test_date = past_bars.index[-1].date()
        entry_price = past_bars["Close"].iloc[-1]

        # Calculate indicators as they were on that day
        ind = market_data.compute_indicators(past_bars)
        levels = market_data.candidate_levels(ind, entry_price)

        # Baseline Strategy rule based on indicators (Trend + Momentum):
        # If SMA20 > SMA50 and RSI > 45 -> Buy toward Resistance with ATR stop
        # Else if SMA20 < SMA50 and RSI < 50 -> Sell toward Support
        # Else -> Hold
        sma20 = ind.get("sma20")
        sma50 = ind.get("sma50")
        rsi_val = ind.get("rsi14") or 50

        if sma20 and sma50 and sma20 > sma50 and rsi_val >= 45:
            rec = "شراء"
            target = levels["resistances_above_price"][0] if levels["resistances_above_price"] else levels["atr_target_long"]
            stop = levels["atr_stop_long"]
        elif sma20 and sma50 and sma20 < sma50 and rsi_val <= 45:
            rec = "بيع"
            target = levels["supports_below_price"][0] if levels["supports_below_price"] else levels["atr_target_short"]
            stop = levels["atr_stop_short"]
        else:
            rec = "احتفاظ"
            target = levels["resistances_above_price"][0] if levels["resistances_above_price"] else entry_price * 1.05
            stop = levels["supports_below_price"][0] if levels["supports_below_price"] else entry_price * 0.95

        if not target or not stop:
            continue

        status, ret, note = evaluator.evaluate_recommendation(rec, entry_price, target, stop, future_bars)

        res = {
            "السهم": ticker,
            "تاريخ التوصية": str(test_date),
            "سعر الدخول": f"{entry_price:.2f}",
            "التوصية": rec,
            "الهدف": f"{target:.2f}",
            "الوقف": f"{stop:.2f}",
            "النتيجة": status,
            "العائد %": f"{ret:+.2f}%" if ret is not None else "0%",
            "الملاحظة": note,
        }
        results.append(res)
        print(f"  -> التوصية: {rec} | الدخول: {entry_price:.2f} | الهدف: {target:.2f} | الوقف: {stop:.2f}")
        print(f"  -> النتيجة: {status} ({ret:+.2f}%) - {note}")

    if results:
        res_df = pd.DataFrame(results)
        print("\n" + "=" * 60)
        print("ملخص النتائج:")
        print("=" * 60)
        print(res_df[["السهم", "التوصية", "النتيجة", "العائد %", "الملاحظة"]].to_string(index=False))

        success_count = sum(1 for r in results if r["النتيجة"] == "SUCCESS")
        total = len(results)
        win_rate = (success_count / total * 100) if total else 0
        print(f"\nنسبة النجاح (Win Rate): {win_rate:.1f}% ({success_count}/{total})")


if __name__ == "__main__":
    test_tickers = ["COMI", "TMGH", "SWDY", "AMOC", "FWRY", "ETEL", "EKHO", "ORAS"]
    test_historical_accuracy(test_tickers, test_days_ago=25)
