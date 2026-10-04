# مستشار البورصة المصرية (EGX Stock Advisor)

تطبيق ويب لتحليل أسهم البورصة المصرية باستخدام الذكاء الاصطناعي (Gemini 3.8 Flash). يقوم التطبيق بجمع بيانات السوق الفنية وأحدث الأخبار، ثم إصدار توصيات منظمة وحفظها في Google Sheets لتقييم أدائها لاحقاً.

## الميزات
*   **جلب لحظي لبيانات السوق:** دمج بين تاريخ Yahoo Finance والأسعار اللحظية من TradingView (للحصول على دقة أعلى).
*   **أخبار مفلترة:** جلب أحدث الأخبار من Google News RSS باللغتين العربية والإنجليزية بفلترة ذكية ومطابقة دقيقة لاسم السهم.
*   **تحليل ذكي (Structured Logic):** توجيه نموذج Gemini بمستويات محددة (دعوم، مقاومات، ATR) وإلزامه بقواعد رياضية صارمة (مثل عدم السماح بوقف خسارة أعلى من السعر الحالي في حالة الشراء).
*   **التوثيق المرجعي:** إجبار النموذج على ذكر مصدر كل نقطة في قراره (مؤشر فني أو خبر محدد).
*   **سجل التوصيات:** حفظ التوصيات في Google Sheets لمراجعتها.

## خطوات الإعداد والنشر (على Streamlit Cloud)

### 1. إعداد Google Sheets
التطبيق يحفظ سجل التوصيات في Google Sheets حتى لا تضيع البيانات عند إعادة تشغيل سيرفر Streamlit.
1.  اذهب إلى [Google Cloud Console](https://console.cloud.google.com/).
2.  أنشئ مشروعاً جديداً.
3.  اذهب إلى **APIs & Services > Library** وقم بتفعيل **Google Sheets API** و **Google Drive API**.
4.  اذهب إلى **Credentials**، ثم **Create Credentials > Service Account**.
5.  بعد إنشاء الحساب، ادخل إليه، اذهب إلى تبويب **Keys**، اختر **Add Key > Create new key** بصيغة **JSON**. سيتم تحميل الملف لجهازك.
6.  افتح [Google Sheets](https://docs.google.com/spreadsheets)، وأنشئ ملفاً جديداً.
7.  اضغط على زر **Share (مشاركة)** وأضف الإيميل الخاص بالـ Service Account (الموجود في ملف JSON تحت `client_email`) وامنحه صلاحية **Editor (محرر)**.
8.  انسخ معرّف الملف (ID) من الرابط (الجزء الطويل بين `/d/` و `/edit`).

### 2. تجهيز ملف `secrets.toml`
يجب أن تضع بياناتك السرية في إعدادات Streamlit ولا ترفعها أبداً على GitHub.
انظر إلى الملف المرفق `secrets.toml.example` لترى الصيغة المطلوبة.

المتغيرات المطلوبة:
*   `APP_PASSWORD`: كلمة سر لحماية تطبيقك من الاستخدام العام.
*   `GEMINI_API_KEY`: مفتاحك من Google AI Studio.
*   `GSHEET_ID`: معرّف ملف Google Sheets الذي نسخته.
*   `[gcp_service_account]`: محتويات ملف الـ JSON الذي حملته من Google Cloud كما هي.

### 3. الرفع على GitHub
1.  أنشئ مستودعاً **Private (خاص)** على حسابك في GitHub.
2.  ارفع جميع ملفات المشروع إليه (ملف `.gitignore` المرفق سيمنع رفع الأسرار ومجلد `venv`).

### 4. النشر على Streamlit Cloud
1.  ادخل إلى [share.streamlit.io](https://share.streamlit.io/) واربط حسابك بـ GitHub.
2.  اضغط على **New App** واختر المستودع الخاص بك.
3.  قبل الضغط على Deploy، اضغط على **Advanced Settings**.
4.  في صندوق الأسرار (Secrets)، انسخ والصق محتوى ملف `secrets.toml` الخاص بك بالكامل.
5.  اضغط Save ثم **Deploy**.

## استخدام البحث عبر الإنترنت في Gemini
بشكل افتراضي، التطبيق يستخدم الأخبار التي جلبها من RSS فقط. إذا كان حسابك في Gemini **مدفوعاً**، يمكنك تفعيل ميزة "البحث في جوجل" (Grounding with Google Search) عبر تغيير `USE_SEARCH_GROUNDING = true` في الأسرار.
*ملاحظة: هذه الميزة غير متاحة في الباقات المجانية وستتسبب في خطأ إذا تم تفعيلها بدون رصيد.*

## التشغيل محلياً (Local Development)
إذا أردت تجربة التطبيق على جهازك:
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
# ضع الأسرار في .streamlit/secrets.toml
streamlit run app.py
```
