import asyncpg
import os
from datetime import datetime

class Database:

    def __init__(self):
        self.pool = None
        self.db_url = os.getenv("DATABASE_URL")

        if not self.db_url:
            raise ValueError("DATABASE_URL が設定されていません")

    # =========================
    # 初期化
    # =========================
    async def init(self):

        print("DB connecting...")

        self.pool = await asyncpg.create_pool(
            self.db_url,
            min_size=1,
            max_size=5,
            command_timeout=10
        )

        print("DB connected")

        async with self.pool.acquire() as conn:

            # =========================
            # users
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id TEXT,
                guild_id TEXT,
                balance BIGINT DEFAULT 0,
                tickets INTEGER DEFAULT 0,
                PRIMARY KEY(user_id,guild_id)
            )
            """)

            # =========================
            # settings
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                guild_id TEXT PRIMARY KEY,
                admin_roles TEXT,
                bank_roles TEXT,
                hotel_role TEXT,
                sub_role TEXT,
                currency_unit TEXT
            )
            """)
            await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='settings'
                    AND column_name='admin_roles'
                    AND udt_name LIKE '\\_%'
                ) THEN
                    ALTER TABLE settings
                    ALTER COLUMN admin_roles TYPE TEXT USING admin_roles::TEXT;
                END IF;
            END $$;
            """)

            await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='settings'
                    AND column_name='bank_roles'
                    AND udt_name LIKE '\\_%'
                ) THEN
                    ALTER TABLE settings
                    ALTER COLUMN bank_roles TYPE TEXT USING bank_roles::TEXT;
                END IF;
            END $$;
            """)

            # =========================
            # hotel_settings
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS hotel_settings(
                guild_id TEXT PRIMARY KEY,
                manager_role TEXT,
                log_channel TEXT,
                sub_role TEXT,
                ticket_price_1 INTEGER,
                ticket_price_10 INTEGER,
                ticket_price_30 INTEGER,
                category_ids TEXT
            )
            """)

            # 🔥 migration（ARRAY → TEXT）
            try:
                col_type = await conn.fetchval("""
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_name='hotel_settings'
                    AND column_name='category_ids'
                """)

                if col_type == "ARRAY":
                    await conn.execute("""
                        ALTER TABLE hotel_settings
                        ALTER COLUMN category_ids TYPE TEXT
                        USING array_to_string(category_ids, ',')
                    """)
                    print("[DB MIGRATION] hotel_settings.category_ids ARRAY → TEXT 完了")

            except Exception as e:
                print("[DB MIGRATION ERROR]", e)

            # =========================
            # hotel_rooms
            # =========================
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS hotel_rooms(
                guild_id TEXT,
                owner_id TEXT,
                vc_id TEXT,
                text_id TEXT,
                expire_at TIMESTAMP,
                PRIMARY KEY(owner_id,guild_id)
            )
            """)

    # =========================
    # balance
    # =========================
    async def get_balance(self, user_id, guild_id):

        async with self.pool.acquire() as conn:

            await conn.execute("""
                INSERT INTO users(user_id,guild_id)
                VALUES($1,$2)
                ON CONFLICT(user_id,guild_id) DO NOTHING
            """, user_id, guild_id)

            row = await conn.fetchrow("""
                SELECT balance FROM users
                WHERE user_id=$1 AND guild_id=$2
            """, user_id, guild_id)

            return row["balance"]

    async def add_balance(self, user_id, guild_id, amount):

        await self.get_balance(user_id, guild_id)

        async with self.pool.acquire() as conn:

            await conn.execute("""
                UPDATE users
                SET balance = balance + $1
                WHERE user_id=$2 AND guild_id=$3
            """, amount, user_id, guild_id)

        return await self.get_balance(user_id, guild_id)

    async def remove_balance(self, user_id, guild_id, amount):

        bal = await self.get_balance(user_id, guild_id)

        if bal < amount:
            return False

        async with self.pool.acquire() as conn:

            await conn.execute("""
                UPDATE users
                SET balance = balance - $1
                WHERE user_id=$2 AND guild_id=$3
            """, amount, user_id, guild_id)

        return True

    # =========================
    # tickets
    # =========================
    async def get_tickets(self, user_id, guild_id):

        async with self.pool.acquire() as conn:

            await conn.execute("""
                INSERT INTO users(user_id,guild_id)
                VALUES($1,$2)
                ON CONFLICT(user_id,guild_id) DO NOTHING
            """, user_id, guild_id)

            row = await conn.fetchrow("""
                SELECT tickets FROM users
                WHERE user_id=$1 AND guild_id=$2
            """, user_id, guild_id)

            return row["tickets"]

    async def add_tickets(self, user_id, guild_id, amount):

        await self.get_tickets(user_id, guild_id)

        async with self.pool.acquire() as conn:

            await conn.execute("""
                UPDATE users
                SET tickets = tickets + $1
                WHERE user_id=$2 AND guild_id=$3
            """, amount, user_id, guild_id)

        return await self.get_tickets(user_id, guild_id)

    async def remove_tickets(self, user_id, guild_id, amount):

        t = await self.get_tickets(user_id, guild_id)
        new = max(t - amount, 0)

        async with self.pool.acquire() as conn:

            await conn.execute("""
                UPDATE users
                SET tickets=$1
                WHERE user_id=$2 AND guild_id=$3
            """, new, user_id, guild_id)

        return new

    # =========================
    # hotel_settings
    # =========================
    async def set_hotel_settings(
        self,
        guild_id,
        manager_role,
        log_channel,
        sub_role,
        price1,
        price10,
        price30,
        category_ids
    ):

        cats = ",".join(category_ids)

        async with self.pool.acquire() as conn:

            await conn.execute("""
            INSERT INTO hotel_settings
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
            """,
            guild_id,
            manager_role,
            log_channel,
            sub_role,
            price1,
            price10,
            price30,
            cats
            )

    async def get_hotel_settings(self, guild_id):

        async with self.pool.acquire() as conn:

            row = await conn.fetchrow("""
                SELECT * FROM hotel_settings
                WHERE guild_id=$1
            """, guild_id)

            if not row:
                return None

            data = dict(row)
            data["category_ids"] = data["category_ids"].split(",") if data["category_ids"] else []

            return data

    # =========================
    # rooms
    # =========================
    async def save_room(self, guild_id, owner_id, vc_id, text_id, expire_at):

        async with self.pool.acquire() as conn:

            await conn.execute("""
            INSERT INTO hotel_rooms
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(owner_id,guild_id)
            DO UPDATE SET
                vc_id=$3,
                text_id=$4,
                expire_at=$5
            """,
            guild_id,
            owner_id,
            vc_id,
            text_id,
            expire_at
            )

    async def get_room(self, channel_id):

        async with self.pool.acquire() as conn:

            row = await conn.fetchrow("""
                SELECT * FROM hotel_rooms
                WHERE text_id=$1 OR vc_id=$1
            """, channel_id)

            if not row:
                return None

            return dict(row)

    async def update_room_expire(self, vc_id, expire):

        async with self.pool.acquire() as conn:

            await conn.execute("""
                UPDATE hotel_rooms
                SET expire_at=$2
                WHERE vc_id=$1
            """, vc_id, expire)

    async def delete_room(self, owner_id, guild_id):

        async with self.pool.acquire() as conn:

            await conn.execute("""
                DELETE FROM hotel_rooms
                WHERE owner_id=$1 AND guild_id=$2
            """, owner_id, guild_id)

    async def get_all_rooms(self):

        async with self.pool.acquire() as conn:

            rows = await conn.fetch("SELECT * FROM hotel_rooms")

            return [dict(r) for r in rows]

    async def get_room_by_owner(self, owner_id, guild_id):

        async with self.pool.acquire() as conn:

            row = await conn.fetchrow("""
                SELECT * FROM hotel_rooms
                WHERE owner_id=$1 AND guild_id=$2
            """, owner_id, guild_id)

            if not row:
                return None

            return dict(row)

    # =========================
    # settings
    # =========================
    async def get_settings(self, guild_id):

        async with self.pool.acquire() as conn:

            row = await conn.fetchrow("""
                SELECT admin_roles, bank_roles, hotel_role, sub_role, currency_unit
                FROM settings
                WHERE guild_id=$1
            """, guild_id)

            if not row:
                return None

            return {
                "admin_roles": row["admin_roles"].split(",") if row["admin_roles"] else [],
                "bank_roles": row["bank_roles"].split(",") if row["bank_roles"] else [],
                "hotel_role": row["hotel_role"],
                "sub_role": row["sub_role"],
                "currency_unit": row["currency_unit"] or ""
            }

    async def set_settings(
        self,
        guild_id,
        admin_roles,
        bank_roles,
        hotel_role,
        sub_role,
        currency_unit
    ):
        admin_roles = list(admin_roles)
        bank_roles = list(bank_roles)

        admin = ",".join(map(str, admin_roles))
        bank = ",".join(map(str, bank_roles))


        async with self.pool.acquire() as conn:

            await conn.execute("""
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
            """,
            guild_id,
            admin,
            bank,
            hotel_role,
            sub_role,
            currency_unit
            )
