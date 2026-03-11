# 🤖 MT5 Telegram Trading Bot

بوت تيليغرام لإدارة صفقات MT5 مع نظام أقسام رأس المال.

---

## 🏗️ البنية

```
العميل  →  /start → Login + Password + Server + رأس المال
                  → تصنيف تلقائي في القسم المناسب
                  → ربط عبر MetaApi

الأدمن  →  /trade → اختيار الزوج + النوع + القسم + Lot لكل قسم + SL/TP
                  → تنفيذ على كل حسابات القسم المختار بالتوازي
```

---

## 📂 أقسام رأس المال

| القسم  | رأس المال    | Lot الافتراضي |
|--------|-------------|----------------|
| 🥉 Tier 1 | 0$ – 99$   | 0.01 |
| 🥈 Tier 2 | 100$ – 499$ | 0.02 |
| 🥇 Tier 3 | 500$ – 999$ | 0.05 |
| 💎 Tier 4 | 1,000$ – 1,499$ | 0.10 |
| 👑 Tier 5 | 1,500$ – 2,999$ | 0.15 |
| 🚀 Tier 6 | 3,000$+ | 0.30 |

> يمكن تعديل هذه القيم في `config.py`

---

## ⚙️ إعداد Railway

### 1. احصل على التوكنات
- **BOT_TOKEN**: من @BotFather في تيليغرام
- **META_API_TOKEN**: من [metaapi.cloud](https://metaapi.cloud) (مجاني)
- **ADMIN_ID**: من @userinfobot

### 2. ارفع على GitHub
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```

### 3. نشر على Railway
1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. اختر الريبو
3. أضف قاعدة البيانات: **+ New → Database → PostgreSQL**
4. أضف المتغيرات في **Variables**:
   ```
   BOT_TOKEN=...
   META_API_TOKEN=...
   ADMIN_ID=...
   ```
5. في Settings → تأكد Start Command: `python main.py`

---

## 📱 أوامر البوت

### للعميل
| الأمر | الوصف |
|-------|-------|
| `/start` | ربط حساب MT5 |
| `/relink` | إعادة ربط بحساب آخر |

### للأدمن
| الأمر | الوصف |
|-------|-------|
| `/trade` | فتح صفقة مع اختيار القسم و Lot |
| `/modify` | عرض الصفقات المفتوحة |
| `/close` | إغلاق صفقة |
| `/clients` | عرض العملاء مرتبين حسب القسم |
| `/kick <user_id>` | إيقاف عميل |

### تعديل صفقة (رسالة مباشرة)
```
تعديل <trade_id> <SL> <TP>
مثال: تعديل 3 1.0800 1.1100
```

---

## 🗂️ هيكل الملفات
```
mt5bot/
├── main.py
├── config.py              ← إعدادات الأقسام والـ Lots
├── requirements.txt
├── Procfile
├── .env.example
├── database/
│   ├── __init__.py
│   └── db.py
├── handlers/
│   ├── __init__.py
│   ├── client.py
│   └── admin.py
└── utils/
    ├── __init__.py
    └── metaapi_handler.py
```

---

## ⚠️ ملاحظات
- MetaApi Free Plan: **3 حسابات** — للمزيد يحتاج خطة مدفوعة
- كلمة مرور العميل تُحذف من الدردشة فوراً
- الصفقات تُنفَّذ بالتوازي (asyncio) على كل الحسابات دفعة واحدة
- لتعديل حدود الأقسام أو الـ Lots الافتراضية: عدّل `config.py`
