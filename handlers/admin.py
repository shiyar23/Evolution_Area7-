"""
handlers/admin.py — أوامر الأدمن
"""

import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from database import (
    get_all_users, get_users_by_tier, deactivate_user, get_user,
    get_all_pending, approve_user, reject_user,
    save_trade, save_tier_lot,
    save_user_order, get_open_trades,
    get_user_orders_for_trade, close_trade_db
)
from utils.metaapi_handler import (
    open_trade, modify_trade, close_position, get_account_balance
)
from config import TIERS, TIER_DESCRIPTIONS, get_tier_info

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ── مراحل فتح الصفقة ─────────────────────────────────────
(T_SYMBOL, T_ACTION, T_OPEN_PRICE, T_TARGET, T_LOTS, T_SL, T_TP, T_CONFIRM) = range(8)

ACTION_LABELS = {
    "buy":        "🟢 Buy",
    "sell":       "🔴 Sell",
    "buy_limit":  "🔵 Buy Limit",
    "sell_limit": "🟠 Sell Limit",
}


def is_limit(action): return action in ("buy_limit", "sell_limit")
def is_admin(uid):    return uid == ADMIN_ID


def _tier_keyboard():
    kb = []
    for num, t in TIERS.items():
        kb.append([InlineKeyboardButton(
            f"{t['name']}  ({TIER_DESCRIPTIONS[num]})",
            callback_data=f"tier_{num}"
        )])
    kb.append([InlineKeyboardButton("📢 كل الأقسام", callback_data="tier_all")])
    return InlineKeyboardMarkup(kb)


# ══════════════════════════════════════════════════════════
#  /requests — موافقة / رفض طلبات التسجيل
# ══════════════════════════════════════════════════════════

async def cmd_requests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    pendings = await get_all_pending()
    if not pendings:
        await update.message.reply_text("📭 لا توجد طلبات تسجيل جديدة.")
        return

    for p in pendings:
        tier_info = get_tier_info(p["tier"])
        kb = [[
            InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{p['user_id']}"),
            InlineKeyboardButton("❌ رفض",    callback_data=f"reject_{p['user_id']}"),
        ]]
        await update.message.reply_text(
            f"📋 طلب تسجيل\n\n"
            f"👤 الاسم: {p['full_name']}\n"
            f"📱 تيليغرام: @{p['tg_username']}\n"
            f"🆔 User ID: {p['user_id']}\n"
            f"📊 MT5 Login: {p['mt5_login']}\n"
            f"🌐 السيرفر: {p['mt5_server']}\n"
            f"💰 رأس المال: `{p['capital']}$`\n"
            f"📂 القسم: {tier_info['name']}",
                reply_markup=InlineKeyboardMarkup(kb)
        )


async def approval_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    parts   = q.data.split("_")
    action  = parts[0]          # approve | reject
    user_id = int(parts[1])

    if action == "approve":
        pending = await approve_user(user_id)
        if not pending:
            await q.edit_message_text("⚠️ الطلب غير موجود أو تمت معالجته مسبقاً.")
            return

        await q.edit_message_text(
            f"✅ تمت الموافقة على {pending['full_name']}\n"
            f"جاري ربط حساب MT5...",
                )

        # ربط MT5 في الخلفية بعد الموافقة
        from utils.metaapi_handler import connect_mt5_account
        from database import update_meta_api_id

        result = await connect_mt5_account(
            pending["mt5_login"],
            pending["mt5_password"],
            pending["mt5_server"]
        )

        tier_info = get_tier_info(pending["tier"])

        if result["success"]:
            await update_meta_api_id(user_id, result["account_id"])
            # إشعار العميل بالموافقة
            try:
                await ctx.bot.send_message(
                    user_id,
                    f"🎉 تمت الموافقة على طلبك!\n\n"
                    f"✅ تم ربط حساب MT5 الخاص بك بنجاح\n\n"
                    f"📊 رقم الحساب: {pending['mt5_login']}\n"
                    f"🌐 السيرفر: {pending['mt5_server']}\n"
                    f"💰 رأس المال: `{pending['capital']}$`\n"
                    f"📂 القسم: {tier_info['name']}\n\n"
                    "سيتم تنفيذ الصفقات على حسابك تلقائياً 🚀",
                                )
            except Exception:
                pass
            await q.edit_message_text(
                f"✅ {pending['full_name']} — تمت الموافقة وربط الحساب بنجاح",
                        )
        else:
            err = result.get("message", "خطأ غير معروف")
            try:
                await ctx.bot.send_message(
                    user_id,
                    f"✅ تمت الموافقة على طلبك، لكن حدث خطأ أثناء ربط MT5:\n{err}\n\n"
                    "تواصل مع الدعم."
                )
            except Exception:
                pass
            await q.edit_message_text(
                f"⚠️ موافقة على {pending['full_name']} — فشل ربط MT5: {err}",
                        )

    else:  # reject
        await reject_user(user_id)
        try:
            await ctx.bot.send_message(
                user_id,
                "❌ تم رفض طلب التسجيل الخاص بك.\n\n"
                "للاستفسار تواصل مع الدعم.",
                        )
        except Exception:
            pass
        await q.edit_message_text("❌ تم رفض الطلب وإشعار المستخدم.")


# ══════════════════════════════════════════════════════════
#  /trade — فتح صفقة جديدة
# ══════════════════════════════════════════════════════════

async def trade_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "📈 فتح صفقة جديدة\n\nأرسل اسم الزوج (Symbol):\nمثال: `EURUSD` أو `XAUUSD`"
    )
    return T_SYMBOL


async def got_symbol(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["symbol"] = update.message.text.strip().upper()
    kb = [
        [
            InlineKeyboardButton("🟢 Buy",        callback_data="act_buy"),
            InlineKeyboardButton("🔴 Sell",       callback_data="act_sell"),
        ],
        [
            InlineKeyboardButton("🔵 Buy Limit",  callback_data="act_buy_limit"),
            InlineKeyboardButton("🟠 Sell Limit", callback_data="act_sell_limit"),
        ],
    ]
    await update.message.reply_text(
        f"✅ الزوج: {ctx.user_data['symbol']}\n\nاختر نوع الصفقة:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return T_ACTION


async def got_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data.replace("act_", "")
    ctx.user_data["action"] = action
    label  = ACTION_LABELS[action]

    if is_limit(action):
        await q.edit_message_text(
            f"{label} ✓\n\n💲 أرسل سعر الدخول (Open Price):\nمثال: `1.0850`",
                )
        return T_OPEN_PRICE
    else:
        ctx.user_data["open_price"] = None
        await q.edit_message_text(
            f"{label} ✓\n\nاختر القسم المستهدف:",
            reply_markup=_tier_keyboard()
        )
        return T_TARGET


async def got_open_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        if price <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل سعراً صحيحاً مثل: `1.0850`")
        return T_OPEN_PRICE

    ctx.user_data["open_price"] = price
    await update.message.reply_text(
        f"💲 سعر الدخول: {price} ✓\n\nاختر القسم المستهدف:",
        reply_markup=_tier_keyboard()
    )
    return T_TARGET


async def got_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "tier_all":
        ctx.user_data["target_tier"]   = None
        ctx.user_data["tiers_to_fill"] = list(TIERS.keys())
    else:
        tier_num = int(q.data.split("_")[1])
        ctx.user_data["target_tier"]   = tier_num
        ctx.user_data["tiers_to_fill"] = [tier_num]

    ctx.user_data["tier_lots"]      = {}
    ctx.user_data["tiers_remaining"] = ctx.user_data["tiers_to_fill"].copy()

    await q.edit_message_text(_next_lot_prompt(ctx))
    return T_LOTS


def _next_lot_prompt(ctx) -> str:
    remaining = ctx.user_data["tiers_remaining"]
    tier_num  = remaining[0]
    tier_info = get_tier_info(tier_num)
    return (
        f"📦 {tier_info['name']} ({TIER_DESCRIPTIONS[tier_num]})\n\n"
        f"أرسل حجم الـ Lot:\n_(الافتراضي: {tier_info['default_lot']})_"
    )


async def got_lot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        lot = float(update.message.text.strip())
        if lot <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً موجباً مثل: `0.1`")
        return T_LOTS

    remaining = ctx.user_data["tiers_remaining"]
    current   = remaining.pop(0)
    ctx.user_data["tier_lots"][current] = lot

    if remaining:
        await update.message.reply_text(_next_lot_prompt(ctx))
        return T_LOTS

    await update.message.reply_text("🛑 أرسل Stop Loss (أو `0` للتخطي):")
    return T_SL


async def got_sl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        sl = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أو 0 للتخطي")
        return T_SL
    ctx.user_data["sl"] = sl if sl > 0 else None
    await update.message.reply_text("🎯 أرسل Take Profit (أو `0` للتخطي):")
    return T_TP


async def got_tp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        tp = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أو 0 للتخطي")
        return T_TP
    ctx.user_data["tp"] = tp if tp > 0 else None

    d           = ctx.user_data
    target      = d["target_tier"]
    action      = d["action"]
    target_lbl  = get_tier_info(target)["name"] if target else "📢 كل الأقسام"
    sl_txt      = f"{d['sl']}" if d["sl"] else "—"
    tp_txt      = f"{d['tp']}" if d["tp"] else "—"
    price_txt   = f"{d['open_price']}" if d.get("open_price") else "—"
    lots_lines  = "\n".join([
        f"  {get_tier_info(t)['name']}: `{l} lot`"
        for t, l in d["tier_lots"].items()
    ])

    count = 0
    for t in d["tiers_to_fill"]:
        count += len(await get_users_by_tier(t))

    kb = [[
        InlineKeyboardButton("✅ تأكيد وتنفيذ", callback_data="confirm_trade"),
        InlineKeyboardButton("❌ إلغاء",         callback_data="cancel_trade"),
    ]]
    await update.message.reply_text(
        f"📋 ملخص الصفقة\n\n"
        f"🔹 الزوج: {d['symbol']}\n"
        f"🔹 النوع: {ACTION_LABELS[action]}\n"
        + (f"🔹 سعر الدخول: {price_txt}\n" if is_limit(action) else "") +
        f"🔹 القسم: {target_lbl}\n"
        f"🔹 SL: {sl_txt}\n"
        f"🔹 TP: {tp_txt}\n\n"
        f"📦 Lot لكل قسم:\n{lots_lines}\n\n"
        f"👥 عدد الحسابات: {count}\n\nتأكيد؟",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return T_CONFIRM


async def trade_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if "cancel" in q.data:
        await q.edit_message_text("❌ تم إلغاء الصفقة.")
        ctx.user_data.clear()
        return ConversationHandler.END

    await q.edit_message_text("⏳ جاري تنفيذ الصفقة...")
    d = ctx.user_data

    trade_id = await save_trade(
        d["symbol"], d["action"], d.get("open_price"),
        d["sl"], d["tp"], d["target_tier"]
    )
    for tier_num, lot in d["tier_lots"].items():
        await save_tier_lot(trade_id, tier_num, lot)

    ok = fail = 0
    lines = []

    async def execute(user, lot):
        nonlocal ok, fail
        res = await open_trade(
            user["meta_api_id"], d["symbol"], d["action"], lot,
            d["sl"], d["tp"], d.get("open_price")
        )
        name = user["full_name"] or f"User {user['user_id']}"
        if res["success"]:
            await save_user_order(user["user_id"], trade_id, res["order_id"], lot)
            ok += 1
            lines.append(f"✅ {name}")
        else:
            fail += 1
            lines.append(f"❌ {name}: {res.get('message','خطأ')}")

    tasks = []
    for tier_num in d["tiers_to_fill"]:
        lot   = d["tier_lots"][tier_num]
        users = await get_users_by_tier(tier_num)
        for u in users:
            tasks.append(execute(u, lot))

    await asyncio.gather(tasks)

    result_text = "\n".join(lines) if lines else "لا يوجد حسابات نشطة"
    await q.edit_message_text(
        f"📊 نتيجة التنفيذ\n\n"
        f"✅ نجح: {ok} | ❌ فشل: {fail}\n\n"
        f"{result_text}\n\n🆔 Trade ID: {trade_id}"
    )
    ctx.user_data.clear()
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════
#  /modify  /close  /clients  /kick
# ══════════════════════════════════════════════════════════

async def cmd_modify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    trades = await get_open_trades()
    if not trades:
        await update.message.reply_text("⚠️ لا توجد صفقات مفتوحة.")
        return
    text = "📝 الصفقات المفتوحة:\n\n"
    for t in trades:
        tier_lbl = get_tier_info(t["target_tier"])["name"] if t["target_tier"] else "الكل"
        text += f"🆔 {t['id']} | {t['symbol']} {ACTION_LABELS.get(t['action'], t['action'])} | {tier_lbl}\n"
    text += "\n✏️ أرسل:\n`تعديل <trade_id> <SL> <TP>`"
    await update.message.reply_text(text)


async def handle_modify_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    parts = update.message.text.strip().split()
    if len(parts) != 4:
        await update.message.reply_text("❌ الصيغة: `تعديل <id> <SL> <TP>`")
        return
    try:
        trade_id = int(parts[1]); new_sl = float(parts[2]); new_tp = float(parts[3])
    except ValueError:
        await update.message.reply_text("❌ أرقام غير صحيحة"); return

    orders = await get_user_orders_for_trade(trade_id)
    if not orders:
        await update.message.reply_text("❌ لا توجد أوردرات لهذه الصفقة"); return

    msg = await update.message.reply_text("⏳ جاري التعديل...")
    ok = fail = 0

    async def mod(o):
        nonlocal ok, fail
        r = await modify_trade(o["meta_api_id"], o["order_id"], new_sl, new_tp)
        if r["success"]: ok += 1
        else: fail += 1

    await asyncio.gather([mod(o) for o in orders])
    await msg.edit_text(f"✅ تم التعديل | نجح: {ok} | فشل: {fail}")


async def cmd_close(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    trades = await get_open_trades()
    if not trades:
        await update.message.reply_text("⚠️ لا توجد صفقات مفتوحة."); return
    kb = []
    for t in trades:
        tier_lbl = get_tier_info(t["target_tier"])["name"] if t["target_tier"] else "الكل"
        kb.append([InlineKeyboardButton(
            f"🔴 #{t['id']} | {t['symbol']} {ACTION_LABELS.get(t['action'], t['action'])} | {tier_lbl}",
            callback_data=f"close_{t['id']}"
        )])
    await update.message.reply_text("اختر الصفقة للإغلاق:", reply_markup=InlineKeyboardMarkup(kb))


async def close_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    trade_id = int(q.data.split("_")[1])
    orders   = await get_user_orders_for_trade(trade_id)
    await q.edit_message_text(f"⏳ إغلاق صفقة #{trade_id}...")
    ok = fail = 0

    async def cls(o):
        nonlocal ok, fail
        r = await close_position(o["meta_api_id"], o["order_id"])
        if r["success"]: ok += 1
        else: fail += 1

    await asyncio.gather([cls(o) for o in orders])
    await close_trade_db(trade_id)
    await q.edit_message_text(
        f"🔴 تم إغلاق الصفقة #{trade_id}\n\n✅ نجح: {ok} | ❌ فشل: {fail}"
    )


async def cmd_clients(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    users = await get_all_users()
    if not users:
        await update.message.reply_text("📭 لا يوجد عملاء مسجلون بعد."); return

    by_tier = {i: [] for i in range(1, 7)}
    for u in users:
        by_tier[u["tier"]].append(u)

    text = f"👥 العملاء ({len(users)})*\n"
    for tier_num, tier_users in by_tier.items():
        if not tier_users: continue
        tier_info = get_tier_info(tier_num)
        text += f"\n{tier_info['name']} ({TIER_DESCRIPTIONS[tier_num]}) — {len(tier_users)}\n"
        for u in tier_users:
            status = "✅" if u["is_connected"] and u["is_active"] else "❌"
            tg = f"@{u['tg_username']}" if u.get("tg_username") else "—"
            text += f"  {status} {u['full_name']} | {tg} | `{u['mt5_login']}` | ID:{u['user_id']}\n"

    await update.message.reply_text(text)


async def cmd_kick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not ctx.args:
        await update.message.reply_text("الاستخدام: `/kick <user_id>`"); return
    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ أرسل user_id رقمياً"); return

    await deactivate_user(target_id)
    await update.message.reply_text(f"✅ تم إيقاف {target_id}")
    try:
        await ctx.bot.send_message(target_id, "⚠️ تم إيقاف حسابك. تواصل مع الدعم.")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
#  Handlers للتصدير
# ══════════════════════════════════════════════════════════

ADMIN_TRADE_CONV = ConversationHandler(
    entry_points=[CommandHandler("trade", trade_start)],
    states={
        T_SYMBOL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_symbol)],
        T_ACTION:     [CallbackQueryHandler(got_action,    pattern="^act_")],
        T_OPEN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_open_price)],
        T_TARGET:     [CallbackQueryHandler(got_target,    pattern="^tier_")],
        T_LOTS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lot)],
        T_SL:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_sl)],
        T_TP:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_tp)],
        T_CONFIRM:    [CallbackQueryHandler(trade_confirm, pattern="^(confirm|cancel)_trade$")],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    allow_reentry=True,
    per_message=False,
)

MODIFY_HANDLER   = MessageHandler(filters.TEXT & filters.Regex(r"^تعديل\s+\d+"), handle_modify_text)
CLOSE_CALLBACK   = CallbackQueryHandler(close_callback,   pattern=r"^close_\d+$")
APPROVAL_CALLBACK = CallbackQueryHandler(approval_callback, pattern=r"^(approve|reject)_\d+$")
