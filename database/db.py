"""
database/db.py — PostgreSQL على Railway
"""

import asyncpg
import os
import logging

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         BIGINT PRIMARY KEY,
                username        TEXT,
                full_name       TEXT,
                tg_username     TEXT,
                mt5_login       TEXT,
                mt5_password    TEXT,
                mt5_server      TEXT,
                capital         FLOAT DEFAULT 0,
                tier            INT DEFAULT 1,
                meta_api_id     TEXT,
                is_approved     BOOLEAN DEFAULT FALSE,
                is_connected    BOOLEAN DEFAULT FALSE,
                is_active       BOOLEAN DEFAULT TRUE,
                joined_at       TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS pending_users (
                user_id       BIGINT PRIMARY KEY,
                username      TEXT,
                full_name     TEXT,
                tg_username   TEXT,
                mt5_login     TEXT,
                mt5_password  TEXT,
                mt5_server    TEXT,
                capital       FLOAT,
                tier          INT,
                requested_at  TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS trades (
                id          SERIAL PRIMARY KEY,
                symbol      TEXT NOT NULL,
                action      TEXT NOT NULL,
                open_price  FLOAT,
                sl          FLOAT,
                tp          FLOAT,
                target_tier INT,
                status      TEXT DEFAULT 'open',
                opened_at   TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS user_orders (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT REFERENCES users(user_id),
                trade_id    INT REFERENCES trades(id),
                order_id    TEXT,
                lot         FLOAT,
                status      TEXT DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS tier_lots (
                trade_id    INT REFERENCES trades(id),
                tier        INT,
                lot         FLOAT,
                PRIMARY KEY (trade_id, tier)
            );
        """)
    logger.info("✅ DB جاهز")


# ── Pending (طلبات الانتظار) ──────────────────────────────

async def save_pending(user_id, username, full_name, tg_username,
                       login, password, server, capital, tier):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO pending_users
              (user_id, username, full_name, tg_username,
               mt5_login, mt5_password, mt5_server, capital, tier)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (user_id) DO UPDATE
            SET username=$2, full_name=$3, tg_username=$4,
                mt5_login=$5, mt5_password=$6, mt5_server=$7,
                capital=$8, tier=$9, requested_at=NOW()
        """, user_id, username, full_name, tg_username,
             login, password, server, capital, tier)


async def get_pending(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM pending_users WHERE user_id=$1", user_id
        )


async def get_all_pending():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM pending_users ORDER BY requested_at"
        )


async def delete_pending(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM pending_users WHERE user_id=$1", user_id)


# ── Users ─────────────────────────────────────────────────

async def approve_user(user_id: int) -> dict | None:
    """ينقل المستخدم من pending إلى users ويعيد بياناته"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        pending = await conn.fetchrow(
            "SELECT * FROM pending_users WHERE user_id=$1", user_id
        )
        if not pending:
            return None
        await conn.execute("""
            INSERT INTO users
              (user_id, username, full_name, tg_username,
               mt5_login, mt5_password, mt5_server, capital, tier, is_approved)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,TRUE)
            ON CONFLICT (user_id) DO UPDATE
            SET username=$2, full_name=$3, tg_username=$4,
                mt5_login=$5, mt5_password=$6, mt5_server=$7,
                capital=$8, tier=$9, is_approved=TRUE, is_active=TRUE
        """, pending["user_id"], pending["username"], pending["full_name"],
             pending["tg_username"], pending["mt5_login"], pending["mt5_password"],
             pending["mt5_server"], pending["capital"], pending["tier"])
        await conn.execute("DELETE FROM pending_users WHERE user_id=$1", user_id)
        return dict(pending)


async def reject_user(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM pending_users WHERE user_id=$1", user_id)


async def update_meta_api_id(user_id, account_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET meta_api_id=$2, is_connected=TRUE WHERE user_id=$1
        """, user_id, account_id)


async def get_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def get_users_by_tier(tier: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM users
            WHERE tier=$1 AND is_connected=TRUE AND is_active=TRUE AND is_approved=TRUE
        """, tier)


async def get_all_active_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM users
            WHERE is_connected=TRUE AND is_active=TRUE AND is_approved=TRUE
        """)


async def get_all_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM users ORDER BY tier, joined_at")


async def deactivate_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_active=FALSE WHERE user_id=$1", user_id
        )


# ── Trades ────────────────────────────────────────────────

async def save_trade(symbol, action, open_price, sl, tp, target_tier) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO trades (symbol, action, open_price, sl, tp, target_tier)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
        """, symbol, action, open_price, sl, tp, target_tier)
        return row["id"]


async def save_tier_lot(trade_id, tier, lot):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tier_lots (trade_id, tier, lot) VALUES ($1,$2,$3)
            ON CONFLICT (trade_id, tier) DO UPDATE SET lot=$3
        """, trade_id, tier, lot)


async def get_tier_lot(trade_id, tier) -> float:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT lot FROM tier_lots WHERE trade_id=$1 AND tier=$2", trade_id, tier
        )
        return row["lot"] if row else 0.01


async def save_user_order(user_id, trade_id, order_id, lot):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_orders (user_id, trade_id, order_id, lot)
            VALUES ($1,$2,$3,$4)
        """, user_id, trade_id, order_id, lot)


async def get_open_trades():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM trades WHERE status='open' ORDER BY id DESC"
        )


async def get_user_orders_for_trade(trade_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT uo.*, u.meta_api_id, u.user_id, u.full_name, u.tier
            FROM user_orders uo
            JOIN users u ON uo.user_id = u.user_id
            WHERE uo.trade_id=$1 AND uo.status='open'
        """, trade_id)


async def close_trade_db(trade_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE trades SET status='closed' WHERE id=$1", trade_id)
        await conn.execute(
            "UPDATE user_orders SET status='closed' WHERE trade_id=$1", trade_id
        )
