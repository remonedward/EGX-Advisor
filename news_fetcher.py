"""Google News RSS fetching with recency + relevance filtering and de-duplication."""
from __future__ import annotations

import calendar
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
import streamlit as st

from config import CAIRO_TZ, NEWS_LOOKBACK_DAYS, NEWS_MAX_ITEMS

_AR_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_EN_LEGAL = re.compile(
    r"\b(s\.?\s?a\.?\s?e\.?|sae|company|co|corp|corporation|holding|holdings|group|plc|inc|ltd|limited)\b\.?",
    re.IGNORECASE,
)


def normalize_ar(text: str) -> str:
    text = _AR_DIACRITICS.sub("", text or "")
    text = re.sub("[أإآٱ]", "ا", text)
    text = text.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_en_name(name: str) -> str:
    """'Commercial International Bank - Egypt (CIB) S.A.E.' -> 'Commercial International Bank'."""
    name = re.sub(r"\(.*?\)", " ", name or "")
    name = re.split(r"\s[-–]\s", name)[0]
    name = _EN_LEGAL.sub(" ", name)
    name = re.sub(r"[,&]", " ", name)
    return re.sub(r"\s+", " ", name).strip(" .")


def _abbreviations(name_en: str) -> list[str]:
    """Explicit short names: '(CIB)' and all-caps words such as 'MOPCO'."""
    found = re.findall(r"\(([A-Za-z]{2,8})\)", name_en or "")
    found += re.findall(r"\b([A-Z]{3,8})\b", re.sub(r"\(.*?\)", " ", name_en or ""))
    return [a for a in dict.fromkeys(found) if a.upper() not in {"SAE", "PLC", "LTD", "INC"}]


def relevance_keys(ticker: str, name_ar: str, name_en: str) -> tuple[list[str], list[str]]:
    ar_keys = [normalize_ar(name_ar)] if name_ar else []
    en_clean = clean_en_name(name_en)
    en_keys = [en_clean.lower()] if len(en_clean) >= 5 else []
    # abbreviations + ticker are matched case-sensitively (avoid 'EAST' matching 'Middle East')
    cased = _abbreviations(name_en) + [ticker.upper()]
    return ar_keys, en_keys + [f"CASED:{c}" for c in cased]


def _is_relevant(title: str, ar_keys: list[str], en_keys: list[str]) -> bool:
    title = title or ""
    t_ar = normalize_ar(title)
    if any(k and k in t_ar for k in ar_keys):
        return True
    for k in en_keys:
        if k.startswith("CASED:"):
            if re.search(rf"\b{re.escape(k[6:])}\b", title):
                return True
        elif re.search(rf"\b{re.escape(k)}\b", title.lower()):
            return True
    return False


def _split_title(raw: str, source: str) -> str:
    if source and raw.endswith(f" - {source}"):
        return raw[: -len(source) - 3].strip()
    return raw.rsplit(" - ", 1)[0].strip() if " - " in raw else raw.strip()


def _query(q: str, lang: str) -> list:
    params = {"q": f"{q} when:{NEWS_LOOKBACK_DAYS}d"}
    if lang == "ar":
        params.update(hl="ar", gl="EG", ceid="EG:ar")
    else:
        params.update(hl="en-US", gl="US", ceid="US:en")
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    return feedparser.parse(url).entries


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news(ticker: str, name_ar: str, name_en: str) -> tuple[list[dict], list[str]]:
    """Return (news_items, notes). Items: title, source, published (Cairo str), url, lang."""
    ar_keys, en_keys = relevance_keys(ticker, name_ar, name_en)
    en_clean = clean_en_name(name_en) or ticker
    queries = [(f'"{name_ar}"', "ar"), (f'"{en_clean}" Egypt', "en")]
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_LOOKBACK_DAYS)

    items, seen, notes, dropped = [], set(), [], 0
    for q, lang in queries:
        try:
            entries = _query(q, lang)
        except Exception as exc:
            notes.append(f"فشل جلب الأخبار ({lang}): {exc}")
            continue
        for e in entries:
            if not e.get("published_parsed"):
                continue
            published = datetime.fromtimestamp(calendar.timegm(e.published_parsed), tz=timezone.utc)
            if published < cutoff:
                continue
            source = (e.get("source") or {}).get("title", "")
            title = _split_title(e.get("title", ""), source)
            if not _is_relevant(title, ar_keys, en_keys):
                dropped += 1
                continue
            key = normalize_ar(title)[:80]
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "title": title,
                "source": source,
                "published_dt": published,
                "published": published.astimezone(CAIRO_TZ).strftime("%Y-%m-%d %H:%M"),
                "url": e.get("link", ""),
                "lang": lang,
            })
    items.sort(key=lambda x: x["published_dt"], reverse=True)
    items = items[:NEWS_MAX_ITEMS]
    for i, it in enumerate(items, start=1):
        it["id"] = i
        it.pop("published_dt", None)
    if dropped:
        notes.append(f"تم استبعاد {dropped} خبر لا يذكر الشركة صراحةً في العنوان.")
    if not items:
        notes.append(f"لا توجد أخبار تخص الشركة خلال آخر {NEWS_LOOKBACK_DAYS} يوم.")
    return items, notes
