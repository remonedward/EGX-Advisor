"""Gemini 3.8 Flash interaction: structured analysis with validation rules."""
from __future__ import annotations

import json

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config import (
    gemini_model,
    now_cairo,
    PROMPT_VERSION,
    RECOMMENDATIONS,
    secret,
    secret_bool,
    thinking_level,
)


class AnalysisOutput(BaseModel):
    recommendation: str = Field(
        description="The final recommendation. MUST be exactly one of: شراء قوي, شراء, احتفاظ, بيع, بيع قوي"
    )
    news_sentiment: str = Field(
        description="Overall sentiment of the news provided. MUST be one of: إيجابي, سلبي, محايد"
    )
    horizon_days: int = Field(
        description="Expected time horizon in trading sessions (integer between 5 and 60)."
    )
    target_price: float = Field(
        description="Projected target price in EGP."
    )
    stop_loss: float = Field(
        description="Stop-loss price in EGP."
    )
    confidence_score: int = Field(
        description="Confidence percentage (integer between 0 and 100)."
    )
    rationale: list[str] = Field(
        description="Bullet points explaining the technical and fundamental reasons. Every point MUST cite its source, e.g., '[IND:RSI]' or '[NEWS:3]'."
    )
    risks: list[str] = Field(
        description="Key risks to this recommendation."
    )
    summary: str = Field(
        description="A concise one-sentence summary of the recommendation."
    )


PROMPT_TEMPLATE = """أنت محلل فني وأساسي خبير في البورصة المصرية.
مهمتك تحليل البيانات الفنية والأخبار التالية لسهم {ticker} ({company_name_ar}) وتقديم توصية دقيقة ومنطقية.

--- البيانات المتاحة ---
البيانات الفنية الحالية (المصدر: {data_source}):
{technical_data}

المستويات المحسوبة (دعوم ومقاومات ووقف ATR):
{candidate_levels}

أحدث الأخبار:
{news_data}

--- القواعد الصارمة (MUST FOLLOW) ---
1. ممنوع اختراع أو تخمين أي بيانات. اعتمد حصراً على المعلومات المرفقة.
2. التوصية `recommendation` يجب أن تكون إحدى هذه القيم فقط: (شراء قوي، شراء، احتفاظ، بيع، بيع قوي).
3. تقييم الأخبار `news_sentiment`: (إيجابي، سلبي، محايد). إذا لم تكن هناك أخبار، اختر `محايد`.
4. المنطق الرياضي إلزامي:
   - في حالات "شراء" أو "شراء قوي": يجب أن يكون (وقف الخسارة < السعر الحالي < سعر الهدف).
   - في حالات "بيع" أو "بيع قوي": يجب أن يكون (سعر الهدف < السعر الحالي < وقف الخسارة).
   - في حالة "احتفاظ": يجب أن يكون السعر الحالي محصوراً بين وقف الخسارة والهدف.
5. اختيارات الأسعار: يُفضل بشدة اختيار الهدف ووقف الخسارة من "المستويات المحسوبة" المرفقة. إذا اخترت أرقاماً أخرى، يجب تبريرها بقوة في `rationale`.
6. التوثيق (Citations): كل نقطة في `rationale` يجب أن تنتهي بإشارة للمصدر بين قوسين مربعين:
   - للمؤشرات: [IND:RSI]، [IND:SMA50]، [IND:PRICE]، إلخ.
   - للأخبار: [NEWS:1] حيث 1 هو رقم الخبر.
7. المدة `horizon_days`: من 5 إلى 60 جلسة تداول.
8. الثقة `confidence_score`: من 0 إلى 100.

قم بإرجاع النتيجة بصيغة JSON متوافقة مع الـ Schema المرفقة فقط.
"""


def _validate_logic(res: dict, current_price: float) -> tuple[bool, list[str]]:
    """Ensure the LLM obeyed basic mathematical rules for the recommendation."""
    errors = []
    rec = res.get("recommendation", "")
    target = res.get("target_price")
    stop = res.get("stop_loss")

    if not isinstance(target, (int, float)) or not isinstance(stop, (int, float)):
        return False, ["Target and stop loss must be numeric."]

    if rec in {"شراء قوي", "شراء"}:
        if stop >= current_price:
            errors.append(f"Buy: Stop loss ({stop}) must be < current price ({current_price}).")
        if target <= current_price:
            errors.append(f"Buy: Target ({target}) must be > current price ({current_price}).")
    elif rec in {"بيع قوي", "بيع"}:
        if target >= current_price:
            errors.append(f"Sell: Target ({target}) must be < current price ({current_price}).")
        if stop <= current_price:
            errors.append(f"Sell: Stop loss ({stop}) must be > current price ({current_price}).")
    elif rec == "احتفاظ":
        if not (stop < current_price < target or target < current_price < stop):
            errors.append(f"Hold: Current price ({current_price}) should be between target and stop loss.")
    else:
        errors.append(f"Invalid recommendation enum: {rec}")

    return len(errors) == 0, errors


def generate_recommendation(
    ticker: str,
    name_ar: str,
    price: float,
    indicators: dict,
    levels: dict,
    news: list[dict],
    is_live_price: bool,
) -> dict:
    api_key = secret("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في الإعدادات.")

    client = genai.Client(api_key=api_key)
    model = gemini_model()
    t_level = thinking_level()
    use_search = secret_bool("USE_SEARCH_GROUNDING", False)

    tech_str = json.dumps(indicators, indent=2, ensure_ascii=False)
    levels_str = json.dumps(levels, indent=2, ensure_ascii=False)
    if news:
        news_str = "\n".join(f"{it['id']}. {it['title']} ({it['source']} - {it['published']})" for it in news)
    else:
        news_str = "لا توجد أخبار حديثة."

    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker,
        company_name_ar=name_ar,
        data_source="TradingView (لحظي)" if is_live_price else "Yahoo Finance (نهاية اليوم)",
        technical_data=tech_str,
        candidate_levels=levels_str,
        news_data=news_str,
    )

    import time

    tools = [{"google_search": {}}] if use_search else None
    t_val = getattr(types.ThinkingLevel, t_level.upper(), t_level)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AnalysisOutput,
        temperature=0.2,
        tools=tools,
        thinking_config=types.ThinkingConfig(thinking_level=t_val),
    )

    candidate_models = [model]
    if model != "gemini-3.5-flash":
        candidate_models.append("gemini-3.5-flash")

    last_error = None
    resp = None
    used_model = model

    for m in candidate_models:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(model=m, contents=prompt, config=config)
                used_model = m
                break
            except Exception as e:
                err_str = str(e)
                last_error = e
                # Transient 503 unavailable or 429 rate limit
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    time.sleep(2)
                    continue
                else:
                    break
        if resp is not None:
            break

    if resp is None or not resp.text:
        raise ValueError(f"تعذر الحصول على رد من النموذج: {last_error}")

    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError as e:
        raise ValueError(f"فشل في قراءة JSON من النموذج: {e}\n{resp.text[:100]}...")

    ok, errors = _validate_logic(data, price)
    data["_meta"] = {
        "model": used_model,
        "prompt_version": PROMPT_VERSION,
        "thinking": t_level,
        "valid_logic": ok,
        "logic_errors": errors,
        "grounding": "search" if use_search else "news_rss",
    }
    return data
