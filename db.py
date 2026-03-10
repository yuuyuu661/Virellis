import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()


class Database:

    def __init__(self):
        self.pool = None

    # =========================
    # DB接続
    # =========================
    async def connect(self):

        if self.pool:
            return

        self.pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL"),
            min_size=1,
            max_size=10
        )

        print("✅ Database connected")

    # =========================
    # DB初期化
    # =========================
    async def init_db(self):

        await self.connect()

        async with self.pool.acquire() as conn:

            # =========================
            # ユーザー残高
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT,
                guild_id TEXT,
                balance BIGINT DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
            """)

            # =========================
            # 設定
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id TEXT PRIMARY KEY,
                admin_roles TEXT[],
                bank_roles TEXT[],
                hotel_role TEXT,
                sub_role TEXT,
                currency_unit TEXT DEFAULT 'pt'
            )
            """)

        print("✅ Tables ready")

    # =========================
    # 内部ヘルパー
    # =========================
    async def _fetchrow(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetch(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    # =========================
    # ユーザー取得
    # =========================
    async def get_user(self, user_id, guild_id):

        row = await self._fetchrow("""
        SELECT *
        FROM users
        WHERE user_id=$1 AND guild_id=$2
        """, user_id, guild_id)

        if not row:

            await self._execute("""
            INSERT INTO users(user_id,guild_id,balance)
            VALUES($1,$2,0)
            """, user_id, guild_id)

            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "balance": 0
            }

        return row

    # =========================
    # 残高取得
    # =========================
    async def get_balance(self, user_id, guild_id):

        user = await self.get_user(user_id, guild_id)
        return user["balance"]

    # =========================
    # 残高設定
    # =========================
    async def set_balance(self, user_id, guild_id, amount):

        await self._execute("""
        INSERT INTO users(user_id,guild_id,balance)
        VALUES($1,$2,$3)
        ON CONFLICT(user_id,guild_id)
        DO UPDATE SET balance=$3
        """, user_id, guild_id, amount)

    # =========================
    # 残高加算
    # =========================
    async def add_balance(self, user_id, guild_id, amount):

        await self._execute("""
        INSERT INTO users(user_id,guild_id,balance)
        VALUES($1,$2,$3)
        ON CONFLICT(user_id,guild_id)
        DO UPDATE SET balance = users.balance + $3
        """, user_id, guild_id, amount)

    # =========================
    # 残高減算
    # =========================
    async def remove_balance(self, user_id, guild_id, amount):

        await self._execute("""
        UPDATE users
        SET balance = balance - $3
        WHERE user_id=$1 AND guild_id=$2
        """, user_id, guild_id, amount)

    # =========================
    # 残高ランキング
    # =========================
    async def get_ranking(self, guild_id):

        rows = await self._fetch("""
        SELECT user_id,balance
        FROM users
        WHERE guild_id=$1
        ORDER BY balance DESC
        """, guild_id)

        return rows

    # =========================
    # 設定保存
    # =========================
    async def set_settings(
        self,
        guild_id,
        admin_roles,
        bank_roles,
        hotel_role,
        sub_role,
        currency_unit
    ):

        await self._execute("""
        INSERT INTO settings(guild_id,admin_roles,bank_roles,hotel_role,sub_role)
        VALUES($1,$2,$3,$4,$5)
        ON CONFLICT(guild_id)
        DO UPDATE SET
        admin_roles=$2,
        bank_roles=$3,
        hotel_role=$4,
        sub_role=$5
        """, guild_id, admin_roles, bank_roles, hotel_role, sub_role)

    # =========================
    # 設定取得
    # =========================
    async def get_settings(self, guild_id):

        return await self._fetchrow("""
        SELECT *
        FROM settings
        WHERE guild_id=$1
        """, guild_id)
