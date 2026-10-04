"""Main Streamlit application entry point."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analyzer
import auth
import evaluator
import market_data
import news_fetcher
import storage
import tradingview
import ui_style
from config import CAIRO_TZ, now_cairo

st.set_page_config(
    page_title="مستشار البورصة المصرية",
    page_icon="📈",
    layout="wide",
)

ui_style.apply_rtl()

if not auth.check_password():
    st.stop()


# ---------------------------------------------------------------- Data load
universe_df, universe_src = tradingview.load_universe()
if universe_df.empty:
    st.error("فشل في تحميل قائمة الأسهم.")
    st.stop()


# ---------------------------------------------------------------- Setup
storage.setup_sheet()


def render_analyzer_tab():
    st.header("فحص وتحليل سهم")

    # Storage mode indicator
    if storage.is_using_sheets():
        st.success("🟢 وضع التخزين: متصل بـ Google Sheets مباشرة.", icon="✅")
    else:
        st.info("ℹ️ وضع التخزين: محلي (CSV). ستعمل كل الوظائف محلياً لحين إضافة بيانات Google Sheets.", icon="💾")

    # 1. Selection
    col1, col2 = st.columns([3, 1])
    with col1:
        options = universe_df["ticker"] + " - " + universe_df["name_ar"]
        selected_opt = st.selectbox("اختر السهم", options=options, index=None, placeholder="ابحث بالاسم أو الكود...")

    if not selected_opt:
        st.info("قم باختيار سهم للبدء في التحليل.")
        return

    ticker = selected_opt.split(" - ")[0]
    row = universe_df[universe_df["ticker"] == ticker].iloc[0]
    name_ar, name_en = row["name_ar"], row["name_en"]

    if storage.check_duplicate_today(ticker):
        st.warning(f"تم تحليل {ticker} بالفعل اليوم. هل ترغب في إعادة التحليل؟")

    if st.button("بدء التحليل", type="primary", use_container_width=True):
        with st.spinner("جارٍ جمع البيانات الفنية والأخبار وتحليل النموذج..."):
            _run_pipeline(ticker, name_ar, name_en)


def _run_pipeline(ticker: str, name_ar: str, name_en: str):
    # 1. Market Data
    tv_snap, idx_snap, tv_err = tradingview.fetch_snapshot(ticker)
    df = market_data.fetch_history(ticker)

    if df.empty:
        st.error(f"لم يتم العثور على بيانات تاريخية للسهم {ticker} على Yahoo Finance.")
        return

    ind = market_data.compute_indicators(df)
    missed_days, is_stale = market_data.freshness(df.index[-1].date(), now_cairo())

    live_price = tv_snap.get("close") if tv_snap else None
    price_to_use = live_price if live_price is not None else ind["last_close"]

    levels = market_data.candidate_levels(ind, price_to_use)

    # 2. News
    news_items, news_notes = news_fetcher.fetch_news(ticker, name_ar, name_en)

    # 3. LLM Analysis
    try:
        rec_data = analyzer.generate_recommendation(
            ticker, name_ar, price_to_use, ind, levels, news_items, is_live_price=(live_price is not None)
        )
    except Exception as e:
        st.error(f"خطأ أثناء توليد التوصية من Gemini: {e}")
        return

    # 4. Persistence
    rec_id = str(uuid.uuid4())[:8]
    saved = storage.append_recommendation(
        rec_id, ticker, name_ar, ind["last_session_date"], is_stale, price_to_use,
        rec_data, news_items, ind
    )

    # ---------------- UI Output
    st.markdown("---")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader(f"{name_ar} ({ticker})")
        st.caption(f"القطاع: {universe_df[universe_df['ticker']==ticker]['sector'].iloc[0]}")
    with c2:
        st.markdown(ui_style.badge_html(rec_data["recommendation"]), unsafe_allow_html=True)

    st.markdown(f"**الملخص:** {rec_data['summary']}")

    if is_stale:
        st.warning(f"⚠️ انتبه: آخر جلسة مسجلة على Yahoo هي {ind['last_session_date']} (مرت {missed_days} أيام تداول).")
    if tv_err:
        st.warning(tv_err)
    if not rec_data["_meta"]["valid_logic"]:
        st.error(f"⚠️ التوصية تحتوي على تعارض منطقي: {', '.join(rec_data['_meta']['logic_errors'])}")
    if not saved:
        st.error("فشل حفظ التوصية في سجل التخزين.")
    else:
        st.success("تم تسجيل التوصية بنجاح لمتابعة أدائها لاحقاً.")

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("السعر المعتمد", f"{price_to_use:.2f} EGP", f"المصدر: {'TradingView (لحظي)' if live_price else 'Yahoo'}")
    c2.metric("السعر المستهدف", f"{rec_data['target_price']} EGP")
    c3.metric("وقف الخسارة", f"{rec_data['stop_loss']} EGP")
    c4.metric("نسبة الثقة", f"{rec_data['confidence_score']}%")

    # Details
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📌 الأسباب والمبررات الفنية")
        for r in rec_data["rationale"]:
            st.markdown(f"- {r}")
    with c2:
        st.markdown("### ⚠️ المخاطر المحتملة")
        for r in rec_data["risks"]:
            st.markdown(f"- {r}")

    # Chart
    st.markdown("### 📊 الرسم البياني (آخر 3 أشهر)")
    df_chart = market_data.add_chart_columns(df.tail(60))
    fig = go.Figure(data=[go.Candlestick(
        x=df_chart.index,
        open=df_chart['Open'], high=df_chart['High'],
        low=df_chart['Low'], close=df_chart['Close'],
        name="السعر"
    )])
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['SMA20'], line=dict(color='blue', width=1), name='SMA20'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['SMA50'], line=dict(color='orange', width=1), name='SMA50'))
    fig.add_hline(y=rec_data['target_price'], line_dash="dash", line_color="green", annotation_text="الهدف")
    fig.add_hline(y=rec_data['stop_loss'], line_dash="dash", line_color="red", annotation_text="الوقف")
    fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Expanders
    with st.expander("📰 الأخبار المعتمدة في التقييم"):
        for note in news_notes:
            st.caption(note)
        for it in news_items:
            st.markdown(f"**{it['id']}. [{it['title']}]({it['url']})**  \n*{it['source']} - {it['published']}*")

    with st.expander("🔍 التحقق المتبادل بين Yahoo و TradingView"):
        checks, c_notes = market_data.cross_check(ind, tv_snap)
        for n in c_notes:
            st.caption(n)
        if checks:
            st.dataframe(checks, use_container_width=True)


def render_history_tab():
    st.header("سجل التوصيات والمتابعة وتقييم النجاح")
    df = storage.load_history()

    if df.empty:
        st.info("لا توجد توصيات مسجلة حتى الآن. قم بتحليل سهم من التبويب الأول لتسجيل أول توصية.")
        return

    # Button to evaluate existing recommendations against actual price history
    col_btn, col_down = st.columns([2, 1])
    with col_btn:
        if st.button("🔄 تحديث تقييم التوصيات الآن", type="secondary"):
            with st.spinner("جارٍ فحص أسعار الأسهم بعد تاريخ كل توصية وتقييم النتائج..."):
                updated_count = _evaluate_all_history(df)
                st.success(f"تم فحص وتحديث التقييم لـ {updated_count} توصية.")
                df = storage.load_history()

    with col_down:
        csv_data = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 تحميل السجل كملف CSV",
            data=csv_data,
            file_name="egx_recommendations_history.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Performance Stats
    total_recs = len(df)
    evaluated = df[df["status"].isin(["ناجحة", "فاشلة", "SUCCESS", "FAILED"])]
    success_recs = df[df["status"].isin(["ناجحة", "SUCCESS"])]
    pending_recs = df[~df["status"].isin(["ناجحة", "فاشلة", "SUCCESS", "FAILED"])]

    win_rate = (len(success_recs) / len(evaluated) * 100) if len(evaluated) > 0 else 0.0

    returns = pd.to_numeric(evaluated["return_pct"], errors="coerce").dropna()
    avg_return = returns.mean() if not returns.empty else 0.0

    st.markdown("### 📈 إحصائيات دقة التطبيق")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("إجمالي التوصيات", total_recs)
    m2.metric("نسبة النجاح (Win Rate)", f"{win_rate:.1f}%", f"{len(success_recs)} من {len(evaluated)} منتهية")
    m3.metric("متوسط العائد للمنتهية", f"{avg_return:+.1f}%")
    m4.metric("توصيات قيد المتابعة", len(pending_recs))

    st.markdown("---")

    # Table display
    display_cols = [
        "timestamp_cairo", "ticker", "company_name_ar", "recommendation",
        "price_at_rec", "target_price", "stop_loss", "confidence",
        "status", "return_pct"
    ]
    avail_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(
        df[avail_cols].rename(columns={
            "timestamp_cairo": "تاريخ التوصية",
            "ticker": "الكود",
            "company_name_ar": "الشركة",
            "recommendation": "التوصية",
            "price_at_rec": "سعر الدخول",
            "target_price": "الهدف",
            "stop_loss": "الوقف",
            "confidence": "الثقة %",
            "status": "حالة التوصية",
            "return_pct": "العائد المحقق %"
        }),
        use_container_width=True,
        hide_index=True
    )


def _evaluate_all_history(df: pd.DataFrame) -> int:
    count = 0
    today_str = datetime.now(CAIRO_TZ).strftime("%Y-%m-%d")

    for idx, row in df.iterrows():
        ticker = row.get("ticker")
        rec_type = row.get("recommendation")
        p_entry = row.get("price_at_rec")
        target = row.get("target_price")
        stop = row.get("stop_loss")
        rec_time = row.get("timestamp_cairo")

        if not ticker or pd.isna(p_entry) or pd.isna(target) or pd.isna(stop):
            continue

        try:
            p_entry = float(p_entry)
            target = float(target)
            stop = float(stop)
        except (ValueError, TypeError):
            continue

        # Fetch subsequent bars
        hist = market_data.fetch_history_raw(ticker, period="1y")
        if hist.empty:
            continue

        # Filter bars strictly after recommendation date
        rec_date = pd.to_datetime(rec_time).date() if pd.notna(rec_time) else None
        if rec_date:
            hist_after = hist[hist.index.date > rec_date]
        else:
            hist_after = hist.tail(10)

        status, ret, note = evaluator.evaluate_recommendation(rec_type, p_entry, target, stop, hist_after)

        ar_status = "ناجحة" if status == "SUCCESS" else ("فاشلة" if status == "FAILED" else "قيد المتابعة")

        df.at[idx, "status"] = ar_status
        df.at[idx, "eval_date"] = today_str
        if ret is not None:
            df.at[idx, "return_pct"] = round(ret, 2)
        count += 1

    storage.save_history(df)
    return count


tab1, tab2 = st.tabs(["فحص وتحليل سهم", "سجل التوصيات والمتابعة"])
with tab1:
    render_analyzer_tab()
with tab2:
    render_history_tab()

st.markdown("---")
st.caption("التوصيات مولدة آلياً لأغراض تعليمية واختبارية وليست نصيحة استثمارية. يرجى مراجعة البيانات قبل اتخاذ أي قرار مالي.")
