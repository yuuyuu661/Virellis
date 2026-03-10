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


            # =========================
            # ホテル設定
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS hotel_settings (
                guild_id TEXT PRIMARY KEY,
                manager_role TEXT,
                log_channel TEXT,
                sub_role TEXT,
                ticket_price_1 INTEGER,
                ticket_price_10 INTEGER,
                ticket_price_30 INTEGER,
                category_ids TEXT[]
            )
            """)

            # =========================
            # ホテルチケット
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS hotel_tickets (
                user_id TEXT,
                guild_id TEXT,
                tickets INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
            """)

            # =========================
            # ホテルルーム
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS hotel_rooms (
                channel_id TEXT PRIMARY KEY,
                guild_id TEXT,
                owner_id TEXT,
                expire_at TIMESTAMP
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

        row = await self._fetchrow("""
        SELECT balance
        FROM users
        WHERE user_id=$1 AND guild_id=$2
        """, user_id, guild_id)

        if not row:
            return None

        return row["balance"]

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
        WHERE user_id=$1
        AND guild_id=$2
        AND balance >= $3
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
        INSERT INTO settings(
            guild_id,
            admin_roles,
            bank_roles,
            hotel_role,
            sub_role,
            currency_unit
        )
        VALUES($1,$2,$3,$4,$5,$6)
        ON CONFLICT(guild_id)
        DO UPDATE SET
            admin_roles=$2,
            bank_roles=$3,
            hotel_role=$4,
            sub_role=$5,
            currency_unit=$6
        """, guild_id, admin_roles, bank_roles, hotel_role, sub_role, currency_unit)

    # =========================
    # 設定取得
    # =========================
    async def get_settings(self, guild_id):

        return await self._fetchrow("""
        SELECT *
        FROM settings
        WHERE guild_id=$1
        """, guild_id)


    # =========================
    # ホテル設定保存
    # =========================
    async def set_hotel_settings(
        self,
        guild_id,
        manager_role,
        log_channel,
        sub_role,
        ticket_price_1,
        ticket_price_10,
        ticket_price_30,
        category_ids
    ):
        await self._execute("""
        INSERT INTO hotel_settings (
            guild_id,
            manager_role,
            log_channel,
            sub_role,
            ticket_price_1,
            ticket_price_10,
            ticket_price_30,
            category_ids
        )
        VALUES($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT(guild_id)
        DO UPDATE SET
            manager_role=$2,
            log_channel=$3,
            sub_role=$4,
            ticket_price_1=$5,
            ticket_price_10=$6,
            ticket_price_30=$7,
            category_ids=$8
        """, guild_id, manager_role, log_channel, sub_role,
             ticket_price_1, ticket_price_10, ticket_price_30, category_ids)

    # =========================
    # ホテル設定取得
    # =========================
    async def get_hotel_settings(self, guild_id):
        return await self._fetchrow("""
        SELECT *
        FROM hotel_settings
        WHERE guild_id=$1
        """, guild_id)

    # =========================
    # チケット取得
    # =========================
    async def get_tickets(self, user_id, guild_id):
        row = await self._fetchrow("""
        SELECT tickets
        FROM hotel_tickets
        WHERE user_id=$1 AND guild_id=$2
        """, user_id, guild_id)

        if not row:
            await self._execute("""
            INSERT INTO hotel_tickets(user_id, guild_id, tickets)
            VALUES($1,$2,0)
            """, user_id, guild_id)
            return 0

        return row["tickets"]

    # =========================
    # チケット加算
    # =========================
    async def add_tickets(self, user_id, guild_id, amount):
        current = await self.get_tickets(user_id, guild_id)
        new_amount = current + amount

        await self._execute("""
        UPDATE hotel_tickets
        SET tickets=$1
        WHERE user_id=$2 AND guild_id=$3
        """, new_amount, user_id, guild_id)

        return new_amount

    # =========================
    # チケット減算
    # =========================
    async def remove_tickets(self, user_id, guild_id, amount):
        current = await self.get_tickets(user_id, guild_id)
        new_amount = max(0, current - amount)

        await self._execute("""
        UPDATE hotel_tickets
        SET tickets=$1
        WHERE user_id=$2 AND guild_id=$3
        """, new_amount, user_id, guild_id)

        return new_amount

    # =========================
    # ルーム保存
    # =========================
    async def save_room(self, channel_id, guild_id, owner_id, expire_at):
        await self._execute("""
        INSERT INTO hotel_rooms (channel_id, guild_id, owner_id, expire_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (channel_id)
        DO UPDATE SET expire_at=$4
        """, channel_id, guild_id, owner_id, expire_at)

    # =========================
    # ルーム削除
    # =========================
    async def delete_room(self, channel_id):
        await self._execute("""
        DELETE FROM hotel_rooms
        WHERE channel_id=$1
        """, channel_id)

    # =========================
    # ルーム取得
    # =========================
    async def get_room(self, channel_id):
        return await self._fetchrow("""
        SELECT *
        FROM hotel_rooms
        WHERE channel_id=$1
        """, channel_id)

    # =========================
    # 全ルーム取得
    # =========================
    async def get_all_rooms(self):
        return await self._fetch("""
        SELECT *
        FROM hotel_rooms
        """)
