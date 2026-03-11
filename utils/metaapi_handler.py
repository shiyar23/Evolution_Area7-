"""
utils/metaapi_handler.py — MetaApi Cloud v3
"""

import os
import logging
from metaapi_cloud_sdk import MetaApi

logger = logging.getLogger(__name__)
META_API_TOKEN = os.getenv("META_API_TOKEN", "")


async def connect_mt5_account(login: str, password: str, server: str) -> dict:
    if not META_API_TOKEN:
        return {"success": False, "account_id": None, "message": "META_API_TOKEN غير موجود في البيئة!"}

    logger.info(f"Connecting MT5: login={login}, server={server}, token_len={len(META_API_TOKEN)}")

    try:
        api = MetaApi(META_API_TOKEN)
        accounts = await api.metatrader_account_api.get_accounts()

        existing = next(
            (a for a in accounts if a.login == str(login) and a.server == server), None
        )

        if existing:
            logger.info(f"Account exists: {existing.id}")
            account = existing
            try:
                await account.deploy()
            except Exception as e:
                logger.warning(f"Deploy warning (OK): {e}")
        else:
            logger.info("Creating new account...")
            account = await api.metatrader_account_api.create_account({
                "name": f"Client_{login}",
                "type": "cloud",
                "login": str(login),
                "password": password,
                "server": server,
                "platform": "mt5",
                "magic": 77777,
            })
            logger.info(f"Account created: {account.id}")

        await account.wait_connected(timeout_in_seconds=120)
        logger.info(f"Account connected: {account.id}")
        return {"success": True, "account_id": account.id}

    except Exception as e:
        logger.error(f"connect_mt5_account FULL ERROR: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"success": False, "account_id": None, "message": f"{type(e).__name__}: {str(e)[:200]}"}


async def open_trade(account_id, symbol, action, lot,
                     sl=None, tp=None, open_price=None) -> dict:
    try:
        api = MetaApi(META_API_TOKEN)
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()

        kwargs = {}
        if sl: kwargs["stopLoss"] = sl
        if tp: kwargs["takeProfit"] = tp

        action_lower = action.lower()
        if action_lower == "buy":
            result = await connection.create_market_buy_order(symbol, lot, **kwargs)
        elif action_lower == "sell":
            result = await connection.create_market_sell_order(symbol, lot, **kwargs)
        elif action_lower == "buy_limit":
            result = await connection.create_limit_buy_order(symbol, lot, open_price, **kwargs)
        elif action_lower == "sell_limit":
            result = await connection.create_limit_sell_order(symbol, lot, open_price, **kwargs)
        else:
            return {"success": False, "order_id": None, "message": f"نوع غير معروف: {action}"}

        await connection.close()
        order_id = str(result.get("orderId") or result.get("positionId") or "N/A")
        return {"success": True, "order_id": order_id}

    except Exception as e:
        logger.error(f"open_trade error [{account_id}]: {type(e).__name__}: {e}")
        return {"success": False, "order_id": None, "message": f"{type(e).__name__}: {str(e)[:100]}"}


async def modify_trade(account_id, order_id, sl=None, tp=None) -> dict:
    try:
        api = MetaApi(META_API_TOKEN)
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()
        positions = connection.terminal_state.positions
        pos = next((p for p in positions if str(p.get("id")) == str(order_id)), None)
        if not pos:
            await connection.close()
            return {"success": False, "message": "الصفقة غير موجودة"}
        await connection.modify_position(
            order_id,
            stop_loss=sl if sl else pos.get("stopLoss"),
            take_profit=tp if tp else pos.get("takeProfit")
        )
        await connection.close()
        return {"success": True}
    except Exception as e:
        logger.error(f"modify error: {e}")
        return {"success": False, "message": str(e)[:100]}


async def close_position(account_id, order_id) -> dict:
    try:
        api = MetaApi(META_API_TOKEN)
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()
        await connection.close_position(order_id)
        await connection.close()
        return {"success": True}
    except Exception as e:
        logger.error(f"close error: {e}")
        return {"success": False, "message": str(e)[:100]}


async def get_account_balance(account_id) -> dict:
    try:
        api = MetaApi(META_API_TOKEN)
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()
        info = connection.terminal_state.account_information
        await connection.close()
        return {"success": True, "balance": info.get("balance"), "equity": info.get("equity")}
    except Exception as e:
        return {"success": False, "message": str(e)[:100]}
