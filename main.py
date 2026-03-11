import logging
import os
import warnings
warnings.filterwarnings("ignore")

from telegram.ext import (
    Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from database import init_db
from handlers.client import client_conv_handler
from handlers.admin import (
    cmd_modify, cmd_close, cmd_clients, cmd_kick, cmd_requests,
    ADMIN_TRADE_CONV, MODIFY_HANDLER, CLOSE_CALLBACK, APPROVAL_CALLBACK
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(app):
    await init_db()
    logger.info("✅ DB ready")


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN غير موجود في متغيرات البيئة!")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(client_conv_handler())
    app.add_handler(ADMIN_TRADE_CONV)
    app.add_handler(CommandHandler("requests", cmd_requests))
    app.add_handler(CommandHandler("modify",   cmd_modify))
    app.add_handler(CommandHandler("close",    cmd_close))
    app.add_handler(CommandHandler("clients",  cmd_clients))
    app.add_handler(CommandHandler("kick",     cmd_kick))
    app.add_handler(APPROVAL_CALLBACK)
    app.add_handler(MODIFY_HANDLER)
    app.add_handler(CLOSE_CALLBACK)

    logger.info("🚀 البوت يعمل...")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
