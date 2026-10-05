"""Storage engine: Google Sheets when credentials exist, with automatic local CSV fallback."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import gspread
import pandas as pd
import streamlit as st

from config import CAIRO_TZ, secret

LOCAL_CSV_PATH = Path(__file__).parent / "data" / "egx_recommendations_history.csv"

COLUMNS = [
    "id", "timestamp_cairo", "ticker", "company_name_ar", "last_session_date", "data_stale",
    "price_at_rec", "recommendation", "horizon_days", "target_price", "stop_loss", "confidence",
    "sentiment", "summary", "rationale", "news_urls", "indicators_json", "model", "prompt_version",
    "flagged", "status", "eval_date", "exit_price", "return_pct", "egx30_return_pct", "alpha_pct"
]

_last_error: str | None = None


def get_connection_error() -> str | None:
    return _last_error


@st.cache_resource
def _get_client() -> gspread.client.Client | None:
    global _last_error
    try:
        creds = secret("gcp_service_account")
        if not creds:
            _last_error = "لم يتم العثور على قسم [gcp_service_account] في الأسرار."
            return None
        creds_dict = dict(creds)
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        client = gspread.service_account_from_dict(creds_dict)
        _last_error = None
        return client
    except Exception as e:
        _last_error = f"خطأ في بيانات الحساب (Service Account): {type(e).__name__} - {e}"
        return None


def get_sheet() -> gspread.worksheet.Worksheet | None:
    global _last_error
    client = _get_client()
    sheet_id = secret("GSHEET_ID")
    if not client:
        return None
    if not sheet_id:
        _last_error = "لم يتم العثور على معرّف الشيت GSHEET_ID في الأسرار."
        return None
    try:
        sh = client.open_by_key(str(sheet_id).strip())
        _last_error = None
        try:
            return sh.worksheet("recommendations")
        except gspread.exceptions.WorksheetNotFound:
            return sh.sheet1
    except Exception as e:
        _last_error = f"فشل فتح ملف الشيت (تأكد من مشاركة الشيت مع إيميل الخدمة كـ Editor): {type(e).__name__} - {e}"
        return None


def is_using_sheets() -> bool:
    return get_sheet() is not None


def setup_sheet():
    LOCAL_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOCAL_CSV_PATH.exists():
        pd.DataFrame(columns=COLUMNS).to_csv(LOCAL_CSV_PATH, index=False, encoding="utf-8-sig")

    sheet = get_sheet()
    if sheet:
        try:
            first_row = sheet.row_values(1)
            if not first_row:
                sheet.append_row(COLUMNS)
        except Exception:
            pass


def append_recommendation(
    rec_id: str,
    ticker: str,
    name_ar: str,
    last_session_date: str,
    is_stale: bool,
    price: float,
    llm_data: dict,
    news_items: list[dict],
    indicators: dict,
) -> tuple[bool, str]:
    """Returns (success: bool, target_destination: str)"""
    global _last_error
    ts = datetime.now(CAIRO_TZ).strftime("%Y-%m-%d %H:%M:%S")
    urls = "\n".join(it.get("url", "") for it in news_items)
    inds = json.dumps(indicators, ensure_ascii=False)
    meta = llm_data.get("_meta", {})

    row = {
        "id": rec_id,
        "timestamp_cairo": ts,
        "ticker": ticker,
        "company_name_ar": name_ar,
        "last_session_date": last_session_date,
        "data_stale": "نعم" if is_stale else "لا",
        "price_at_rec": price,
        "recommendation": llm_data.get("recommendation", ""),
        "horizon_days": llm_data.get("horizon_days", 20),
        "target_price": llm_data.get("target_price"),
        "stop_loss": llm_data.get("stop_loss"),
        "confidence": llm_data.get("confidence_score"),
        "sentiment": llm_data.get("news_sentiment", ""),
        "summary": llm_data.get("summary", ""),
        "rationale": "\n".join(llm_data.get("rationale", [])),
        "news_urls": urls,
        "indicators_json": inds,
        "model": meta.get("model", ""),
        "prompt_version": meta.get("prompt_version", ""),
        "flagged": "نعم" if not meta.get("valid_logic") else "لا",
        "status": "قيد المتابعة",
        "eval_date": "",
        "exit_price": "",
        "return_pct": "",
        "egx30_return_pct": "",
        "alpha_pct": "",
    }

    # 1. Try Google Sheets
    sheet = get_sheet()
    if sheet:
        try:
            row_vals = [row.get(c, "") for c in COLUMNS]
            sheet.append_row(row_vals)
            return True, "Google Sheets"
        except Exception as e:
            _last_error = f"فشل الكتابة في Google Sheets: {e}"

    # 2. Local CSV fallback
    try:
        LOCAL_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOCAL_CSV_PATH.exists() and LOCAL_CSV_PATH.stat().st_size > 0:
            df = pd.read_csv(LOCAL_CSV_PATH, encoding="utf-8-sig")
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        df.to_csv(LOCAL_CSV_PATH, index=False, encoding="utf-8-sig")
        return True, "ملف CSV محلي"
    except Exception as e:
        _last_error = f"فشل الحفظ المحلي: {e}"
        return False, "فشل"


def load_history() -> pd.DataFrame:
    sheet = get_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            df = pd.DataFrame(records)
            if not df.empty:
                df = df.astype(object)
                df["timestamp_cairo"] = pd.to_datetime(df["timestamp_cairo"], errors="coerce")
                return df.sort_values("timestamp_cairo", ascending=False).reset_index(drop=True)
        except Exception as e:
            print("Google Sheets read failed, falling back to CSV:", e)

    if LOCAL_CSV_PATH.exists() and LOCAL_CSV_PATH.stat().st_size > 0:
        try:
            df = pd.read_csv(LOCAL_CSV_PATH, encoding="utf-8-sig")
            if not df.empty:
                df = df.astype(object)
                if "timestamp_cairo" in df.columns:
                    df["timestamp_cairo"] = pd.to_datetime(df["timestamp_cairo"], errors="coerce")
                return df.sort_values("timestamp_cairo", ascending=False).reset_index(drop=True)
            return df
        except Exception as e:
            print("Failed to read local CSV:", e)

    return pd.DataFrame(columns=COLUMNS).astype(object)


def save_history(df: pd.DataFrame) -> bool:
    """Save an updated DataFrame back to storage (after evaluation)."""
    sheet = get_sheet()
    if sheet:
        try:
            df_export = df.copy()
            for c in COLUMNS:
                if c not in df_export.columns:
                    df_export[c] = ""
            if "timestamp_cairo" in df_export.columns:
                df_export["timestamp_cairo"] = df_export["timestamp_cairo"].astype(str)
            df_export = df_export.fillna("")
            sheet.clear()
            sheet.append_row(COLUMNS)
            if not df_export.empty:
                sheet.append_rows(df_export[COLUMNS].astype(str).values.tolist())
            return True
        except Exception as e:
            print("Failed to update Google Sheets:", e)

    try:
        df_to_save = df.copy()
        for c in COLUMNS:
            if c not in df_to_save.columns:
                df_to_save[c] = ""
        if "timestamp_cairo" in df_to_save.columns:
            df_to_save["timestamp_cairo"] = df_to_save["timestamp_cairo"].astype(str)
        df_to_save[COLUMNS].to_csv(LOCAL_CSV_PATH, index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        print("Failed to save local CSV:", e)
        return False


def check_duplicate_today(ticker: str) -> bool:
    df = load_history()
    if df.empty or "timestamp_cairo" not in df.columns:
        return False
    today = datetime.now(CAIRO_TZ).date()
    dates = pd.to_datetime(df["timestamp_cairo"], errors="coerce").dt.date
    recent = df[(df["ticker"] == ticker) & (dates == today)]
    return not recent.empty
