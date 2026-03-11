import aiosqlite
from datetime import datetime


class Database:

    def __init__(self, db_path="database.db"):
        self.db_path = db_path

    async def init(self):

        async with aiosqlite.connect(self.db_path) as db:

            # =========================
            # ユーザー
            # =========================
            await db.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id TEXT,
                guild_id TEXT,
                balance INTEGER DEFAULT 0,
                tickets INTEGER DEFAULT 0,
                PRIMARY KEY(user_id,guild_id)
            )
            """)

            # =========================
            # BOT設定
            # =========================
            await db.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                guild_id TEXT PRIMARY KEY,
                admin_roles TEXT,
                bank_roles TEXT,
                hotel_role TEXT,
                sub_role TEXT,
                currency_unit TEXT
            )
            """)

            # =========================
           # ホテル設定
            # =========================
            await db.execute("""
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

            # =========================
            # ホテルルーム
            # =========================
            await db.execute("""
            CREATE TABLE IF NOT EXISTS hotel_rooms(
                guild_id TEXT,
                owner_id TEXT,
                vc_id TEXT,
                text_id TEXT,
                expire_at TEXT,
                PRIMARY KEY(owner_id,guild_id)
            )
            """)

            await db.commit()

    # =========================
    # ユーザー残高
    # =========================
    async def get_balance(self, user_id, guild_id):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute(
                "SELECT balance FROM users WHERE user_id=? AND guild_id=?",
                (user_id, guild_id)
            ) as cursor:

                row = await cursor.fetchone()

                if not row:
                    await db.execute(
                        "INSERT INTO users(user_id,guild_id,balance,tickets) VALUES(?,?,0,0)",
                        (user_id, guild_id)
                    )
                    await db.commit()
                    return 0

                return row[0]

    async def remove_balance(self, user_id, guild_id, amount):

        balance = await self.get_balance(user_id, guild_id)

        if balance < amount:
            return False

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND guild_id=?",
                (amount, user_id, guild_id)
            )

            await db.commit()

        return True

    # =========================
    # チケット
    # =========================
    async def get_tickets(self, user_id, guild_id):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute(
                "SELECT tickets FROM users WHERE user_id=? AND guild_id=?",
                (user_id, guild_id)
            ) as cursor:

                row = await cursor.fetchone()

                if not row:
                    await db.execute(
                        "INSERT INTO users(user_id,guild_id,balance,tickets) VALUES(?,?,0,0)",
                        (user_id, guild_id)
                    )
                    await db.commit()
                    return 0

                return row[0]

    async def add_tickets(self, user_id, guild_id, amount):

        await self.get_tickets(user_id, guild_id)

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                "UPDATE users SET tickets = tickets + ? WHERE user_id=? AND guild_id=?",
                (amount, user_id, guild_id)
            )

            await db.commit()

        return await self.get_tickets(user_id, guild_id)

    async def remove_tickets(self, user_id, guild_id, amount):

        tickets = await self.get_tickets(user_id, guild_id)

        new = max(tickets - amount, 0)

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                "UPDATE users SET tickets=? WHERE user_id=? AND guild_id=?",
                (new, user_id, guild_id)
            )

            await db.commit()

        return new

    # =========================
    # ホテル設定
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

        categories = ",".join(category_ids)

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute("""
            INSERT INTO hotel_settings
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(guild_id)
            DO UPDATE SET
            manager_role=?,
            log_channel=?,
            sub_role=?,
            ticket_price_1=?,
            ticket_price_10=?,
            ticket_price_30=?,
            category_ids=?
            """, (
                guild_id,
                manager_role,
                log_channel,
                sub_role,
                price1,
                price10,
                price30,
                categories,
                manager_role,
                log_channel,
                sub_role,
                price1,
                price10,
                price30,
                categories
            ))

            await db.commit()

    async def get_hotel_settings(self, guild_id):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute(
                "SELECT * FROM hotel_settings WHERE guild_id=?",
                (guild_id,)
            ) as cursor:

                row = await cursor.fetchone()

                if not row:
                    return None

                return {
                    "guild_id": row[0],
                    "manager_role": row[1],
                    "log_channel": row[2],
                    "sub_role": row[3],
                    "ticket_price_1": row[4],
                    "ticket_price_10": row[5],
                    "ticket_price_30": row[6],
                    "category_ids": row[7].split(",") if row[7] else []
                }

    # =========================
    # ルーム保存
    # =========================
    async def save_room(self, guild_id, owner_id, vc_id, text_id, expire_at):

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute("""
            INSERT INTO hotel_rooms
            VALUES(?,?,?,?,?)
            ON CONFLICT(owner_id,guild_id)
            DO UPDATE SET
            vc_id=?,
            text_id=?,
            expire_at=?
            """, (
                guild_id,
                owner_id,
                vc_id,
                text_id,
                expire_at,
                vc_id,
                text_id,
                expire_at
            ))

            await db.commit()

    async def get_room(self, channel_id):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute(
                "SELECT * FROM hotel_rooms WHERE text_id=? OR vc_id=?",
                (channel_id, channel_id)
            ) as cursor:

                row = await cursor.fetchone()

                if not row:
                    return None

                expire = row[4]

                return {
                    "guild_id": row[0],
                    "owner_id": row[1],
                    "vc_id": row[2],
                    "text_id": row[3],
                    "expire_at": datetime.fromisoformat(expire) if expire else None
                }

    async def get_room_by_owner(self, owner_id, guild_id):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute(
                "SELECT * FROM hotel_rooms WHERE owner_id=? AND guild_id=?",
                (owner_id, guild_id)
            ) as cursor:

                row = await cursor.fetchone()

                if not row:
                    return None

                expire = row[4]

                return {
                    "guild_id": row[0],
                    "owner_id": row[1],
                    "vc_id": row[2],
                    "text_id": row[3],
                    "expire_at": datetime.fromisoformat(expire) if expire else None
                }

    async def get_all_rooms(self):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute("SELECT * FROM hotel_rooms") as cursor:

                rows = await cursor.fetchall()

                rooms = []

                for row in rows:

                    expire = row[4]

                    rooms.append({
                        "guild_id": row[0],
                        "owner_id": row[1],
                        "vc_id": row[2],
                        "text_id": row[3],
                        "expire_at": datetime.fromisoformat(expire) if expire else None
                    })

                return rooms

    async def delete_room(self, owner_id, guild_id):

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                "DELETE FROM hotel_rooms WHERE owner_id=? AND guild_id=?",
                (owner_id, guild_id)
            )

            await db.commit()
    # =========================
    # 管理者設定
    # =========================
    async def get_settings(self, guild_id):

        async with aiosqlite.connect(self.db_path) as db:

            async with db.execute(
                "SELECT admin_roles, bank_roles, hotel_role, sub_role, currency_unit FROM settings WHERE guild_id=?",
               (guild_id,)
            ) as cursor:

                row = await cursor.fetchone()

                if not row:
                    return None

                return {
                    "admin_roles": row[0].split(",") if row[0] else [],
                    "bank_roles": row[1].split(",") if row[1] else [],
                    "hotel_role": row[2],
                    "sub_role": row[3],
                    "currency_unit": row[4]
                }

    # =========================
    # 初期設定
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

        admin = ",".join(admin_roles)
        bank = ",".join(bank_roles)

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute("""
            INSERT INTO settings
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(guild_id)
            DO UPDATE SET
            admin_roles=?,
            bank_roles=?,
            hotel_role=?,
            sub_role=?,
            currency_unit=?
            """, (
                guild_id,
                admin,
                bank,
                hotel_role,
                sub_role,
                currency_unit,
                admin,
                bank,
                hotel_role,
                sub_role,
                currency_unit
            ))

            await db.commit()

    # =========================
    # 残高追加
    # =========================
    async def add_balance(self, user_id, guild_id, amount):

        # ユーザー存在保証
        await self.get_balance(user_id, guild_id)

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=? AND guild_id=?",
                (amount, user_id, guild_id)
            )

            await db.commit()

        return await self.get_balance(user_id, guild_id)
