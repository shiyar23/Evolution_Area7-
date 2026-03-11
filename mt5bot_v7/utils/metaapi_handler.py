"""
utils/metaapi_handler.py — MetaApi Cloud v3
"""

import os
import logging
from metaapi_cloud_sdk import MetaApi

logger = logging.getLogger(__name__)
META_API_TOKEN = os.getenv("META_API_TOKEN")


async def _get_connection(account):
    """جلب اتصال متوافق مع الإصدار الجديد"""
    # جرب الطرق المختلفة حسب الإصدار
    if hasattr(account, 'get_streaming_connection'):
        conn = account.get_streaming_connection()
    elif hasattr(account, 'getRPCConnection'):
        conn = account.getRPCConnection()
    elif hasattr(account, 'get_rpc_connection'):
        conn = account.get_rpc_connection()
    else:
        # الطريقة الجديدة في v3
        conn = account.get_streaming_connection()
    return conn


async def connect_mt5_account(login: str, password: str, server: str) -> dict:
    api = MetaApi(META_API_TOKEN)
    try:
        accounts = await api.metatrader_account_api.get_accounts()
        existing = next(
            (a for a in accounts if a.login == str(login) and a.server == server), None
        )
        if existing:
            account = existing
            await account.deploy()
        else:
            account = await api.metatrader_account_api.create_account({
                "name": f"Client_{login}",
                "type": "cloud",
                "login": str(login),
                "password": password,
                "server": server,
                "platform": "mt5",
                "magic": 77777,
            })

        await account.wait_connected(timeout_in_seconds=60)
        return {"success": True, "account_id": account.id}

    except Exception as e:
        err = str(e).lower()
        if "invalid" in err or "credentials" in err or "password" in err:
            msg = "بيانات الدخول غير صحيحة"
        elif "server" in err:
            msg = "اسم السيرفر غير صحيح"
        elif "timeout" in err:
            msg = "انتهت مهلة الاتصال"
        else:
            msg = str(e)[:100]
        logger.error(f"connect_error: {e}")
        return {"success": False, "account_id": None, "message": msg}


async def open_trade(account_id, symbol, action, lot,
                     sl=None, tp=None, open_price=None) -> dict:
    api = MetaApi(META_API_TOKEN)
    try:
        account = await api.metatrader_account_api.get_account(account_id)

        # الطريقة الجديدة في MetaApi v3
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()

        terminal = connection.terminal_state

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
        logger.error(f"open_trade error [{account_id}]: {e}")
        return {"success": False, "order_id": None, "message": str(e)[:100]}


async def modify_trade(account_id, order_id, sl=None, tp=None) -> dict:
    api = MetaApi(META_API_TOKEN)
    try:
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
        logger.error(f"modify error [{account_id}]: {e}")
        return {"success": False, "message": str(e)[:100]}


async def close_position(account_id, order_id) -> dict:
    api = MetaApi(META_API_TOKEN)
    try:
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()
        await connection.close_position(order_id)
        await connection.close()
        return {"success": True}
    except Exception as e:
        logger.error(f"close error [{account_id}]: {e}")
        return {"success": False, "message": str(e)[:100]}


async def get_account_balance(account_id) -> dict:
    api = MetaApi(META_API_TOKEN)
    try:
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()
        info = connection.terminal_state.account_information
        await connection.close()
        return {"success": True, "balance": info.get("balance"), "equity": info.get("equity")}
    except Exception as e:
        return {"success": False, "message": str(e)[:100]}
