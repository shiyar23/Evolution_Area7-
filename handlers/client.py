"""
handlers/client.py — محادثة العميل
"""

import os
import logging
from telegram import Update
from telegram.ext import (
    ConversationHandler, CommandHandler,
    MessageHandler, filters, ContextTypes
)
from database import save_pending, get_pending, get_user, update_meta_api_id
from utils.metaapi_handler import connect_mt5_account
from config import get_tier_by_capital, get_tier_info, TIER_DESCRIPTIONS

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

ASK_TG_USERNAME, ASK_LOGIN, ASK_PASSWORD, ASK_SERVER, ASK_CAPITAL = range(5)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = await get_user(user.id)

    if existing and existing["is_approved"] and existing["is_connected"] and existing["is_active"]:
        tier_info = get_tier_info(existing["tier"])
        await update.message.reply_text(
            f"✅ حسابك مربوط وجاهز!\n\n"
            f"👤 المستخدم: @{existing['tg_username']}\n"
            f"📊 حساب MT5: {existing['mt5_login']}\n"
            f"🌐 السيرفر: {existing['mt5_server']}\n"
            f"💰 رأس المال: {existing['capital']}$\n"
            f"📂 القسم: {tier_info['name']}\n\n"
            "لإعادة ربط حساب جديد أرسل /relink"
        )
        return ConversationHandler.END

    pending = await get_pending(user.id)
    if pending:
        await update.message.reply_text(
            "⏳ طلبك قيد المراجعة\n\n"
            "سيتم إشعارك فور موافقة المسؤول.\n"
            "إذا أردت تعديل بياناتك أرسل /relink"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"👋 أهلاً {user.first_name}!\n\n"
        "للتسجيل في النظام، أرسل اسم المستخدم الخاص بك على تيليغرام\n"
        "مثال: ahmed_trader\n\n"
        "(بدون @)"
    )
    return ASK_TG_USERNAME


async def relink(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("🔄 تعديل البيانات\n\nأرسل اسم المستخدم على تيليغرام:")
    return ASK_TG_USERNAME


async def got_tg_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_username = update.message.text.strip().lstrip("@")
    if not tg_username or " " in tg_username:
        await update.message.reply_text("❌ اسم المستخدم غير صحيح، أرسله بدون @ وبدون مسافات:")
        return ASK_TG_USERNAME
    ctx.user_data["tg_username"] = tg_username
    await update.message.reply_text("📊 أرسل رقم حساب MT5 (Login):")
    return ASK_LOGIN


async def got_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    login = update.message.text.strip()
    if not login.isdigit():
        await update.message.reply_text("❌ رقم الحساب يجب أن يكون أرقاماً فقط:")
        return ASK_LOGIN
    ctx.user_data["login"] = login
    await update.message.reply_text("🔑 أرسل كلمة المرور:")
    return ASK_PASSWORD


async def got_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["password"] = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.message.reply_text(
        "🌐 أرسل اسم السيرفر\n"
        "مثال: FTMO-Server2 أو ICMarkets-Live"
    )
    return ASK_SERVER


async def got_server(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["server"] = update.message.text.strip()
    tiers_text = "\n".join([f"  • Tier {k}: {v}" for k, v in TIER_DESCRIPTIONS.items()])
    await update.message.reply_text(
        f"💰 أدخل رأس مالك بالدولار ($)\n\n"
        f"الأقسام:\n{tiers_text}\n\n"
        "أرسل الرقم فقط، مثال: 500"
    )
    return ASK_CAPITAL


async def got_capital(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().replace(",", "").replace("$", "")

    try:
        capital = float(text)
        if capital < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً صحيحاً، مثال: 500")
        return ASK_CAPITAL

    tier_num  = get_tier_by_capital(capital)
    tier_info = get_tier_info(tier_num)

    tg_username = ctx.user_data["tg_username"]
    login       = ctx.user_data["login"]
    password    = ctx.user_data["password"]
    server      = ctx.user_data["server"]

    await save_pending(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        tg_username=tg_username,
        login=login,
        password=password,
        server=server,
        capital=capital,
        tier=tier_num
    )

    await update.message.reply_text(
        f"✅ تم استلام طلبك!\n\n"
        f"👤 اسم المستخدم: @{tg_username}\n"
        f"📊 حساب MT5: {login}\n"
        f"🌐 السيرفر: {server}\n"
        f"💰 رأس المال: {capital}$\n"
        f"📂 القسم: {tier_info['name']}\n\n"
        "⏳ في انتظار موافقة المسؤول، سيتم إشعارك قريباً."
    )

    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔔 طلب تسجيل جديد!\n\n"
            f"👤 الاسم: {user.full_name}\n"
            f"📱 تيليغرام: @{tg_username}\n"
            f"🆔 User ID: {user.id}\n"
            f"📊 MT5 Login: {login}\n"
            f"🌐 السيرفر: {server}\n"
            f"💰 رأس المال: {capital}$\n"
            f"📂 القسم: {tier_info['name']}\n\n"
            "للموافقة أو الرفض استخدم /requests"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء. أرسل /start للبدء من جديد.")
    return ConversationHandler.END


def client_conv_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("relink", relink),
        ],
        states={
            ASK_TG_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_tg_username)],
            ASK_LOGIN:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_login)],
            ASK_PASSWORD:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_password)],
            ASK_SERVER:      [MessageHandler(filters.TEXT & ~filters.COMMAND, got_server)],
            ASK_CAPITAL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_capital)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )
