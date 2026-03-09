import os
import asyncpg
from dotenv import load_dotenv
import asyncio
import time
import random
from datetime import datetime, timezone, timedelta, date
import uuid
import json

JST = timezone(timedelta(hours=9))

load_dotenv()

RACE_TIMES = ["09:00", "12:00", "15:00", "18:00", "21:00"]
DISTANCES = ["短距離", "マイル", "中距離", "長距離"]
SURFACES = ["芝", "ダート"]
CONDITIONS = ["良", "稍重", "重", "不良"]
ENTRY_OPEN_MINUTES = 60  # レース開始60分前に締切

PASSIVE_SKILLS = {

    # ------------------------
    # 単体強化（小）
    # ------------------------
    "speed_s": {
        "label": "スピード小アップ",
        "emoji": "🏃",
        "type": "stat",
        "target": "speed",
        "multiplier": 1.10,
        "description": "スピードが少し上がる。"
    },
    "stamina_s": {
        "label": "スタミナ小アップ",
        "emoji": "🫀",
        "type": "stat",
        "target": "stamina",
        "multiplier": 1.10,
        "description": "スタミナが少し上がる。"
    },
    "power_s": {
        "label": "パワー小アップ",
        "emoji": "💥",
        "type": "stat",
        "target": "power",
        "multiplier": 1.10,
        "description": "パワーが少し上がる。"
    },

    # ------------------------
    # 単体強化（大）
    # ------------------------
    "speed_l": {
        "label": "スピード大アップ",
        "emoji": "🚀",
        "type": "stat",
        "target": "speed",
        "multiplier": 1.20,
        "description": "スピードが大幅に上がる。"
    },
    "stamina_l": {
        "label": "スタミナ大アップ",
        "emoji": "❤️‍🔥",
        "type": "stat",
        "target": "stamina",
        "multiplier": 1.20,
        "description": "スタミナが大幅に上がる。"
    },
    "power_l": {
        "label": "パワー大アップ",
        "emoji": "💣",
        "type": "stat",
        "target": "power",
        "multiplier": 1.20,
        "description": "パワーが大幅に上がる。"
    },

    # ------------------------
    # 全体系
    # ------------------------
    "jack_of_all": {
        "label": "器用貧乏",
        "emoji": "🌈",
        "type": "all",
        "multiplier": 1.05,
        "description": "すべてのステータスが少し上がる。"
    },

    # ------------------------
    # トレードオフ系
    # ------------------------
    "muscle_head": {
        "label": "脳筋",
        "emoji": "💪",
        "type": "trade",
        "effects": {
            "power": 1.25,
            "speed": 0.90
        },
        "description": "パワーが大幅に上がる代わりにスピードが少し下がる。"
    },

    "speed_star": {
        "label": "スピードスター",
        "emoji": "⚡",
        "type": "trade",
        "effects": {
            "speed": 1.25,
            "stamina": 0.90
        },
        "description": "スピードが大幅に上がる代わりにスタミナが少し下がる。"
    },

    "steady_runner": {
        "label": "マイペース",
        "emoji": "🐢",
        "type": "trade",
        "effects": {
            "stamina": 1.25,
            "power": 0.90
        },
        "description": "スタミナが大幅に上がる代わりにパワーが少し下がる。"
    },

    # ------------------------
    # 条件系
    # ------------------------


    "gambler": {
        "label": "勝負師",
        "emoji": "🔥",
        "type": "guts",
        "bonus": 5,
        "description": "少し根性が発動しやすくなる。"
    },

    "turf_specialist": {
        "label": "芝得意",
        "emoji": "🌱",
        "type": "surface",
        "surface": "芝",
        "multiplier": 1.10,
        "description": "バ場が芝のとき、すべてのステータスが少し上がる。"
    },

    "dirt_specialist": {
        "label": "ダート得意",
        "emoji": "🏜️",
        "type": "surface",
        "surface": "ダート",
        "multiplier": 1.10,
        "description": "バ場がダートのとき、すべてのステータスが少し上がる。"
    },

    "same_kind_boost": {
        "label": "同族嫌悪",
        "emoji": "👥",
        "type": "same_adult",
        "multiplier": 1.15,
        "description": "同じ種類のおあしすっちが出場しているとき、全ステータスが大幅に上がる。"
    },

    # ------------------------
    # 距離適性
    # ------------------------
    "short_special": {
        "label": "短距離得意",
        "emoji": "🏎️",
        "type": "distance",
        "distance": "短距離",
        "multiplier": 1.15,
        "description": "短距離レースで全ステータスが上がる。"
    },

    "mile_special": {
        "label": "マイル得意",
        "emoji": "🏇",
        "type": "distance",
        "distance": "マイル",
        "multiplier": 1.15,
        "description": "マイルレースで全ステータスが上がる。"
    },

    "middle_special": {
        "label": "中距離得意",
        "emoji": "🏃‍♂️",
        "type": "distance",
        "distance": "中距離",
        "multiplier": 1.15,
        "description": "中距離レースで全ステータスが上がる。"
    },

    "long_special": {
        "label": "長距離得意",
        "emoji": "🌌",
        "type": "distance",
        "distance": "長距離",
        "multiplier": 1.15,
        "description": "長距離レースで全ステータスが上がる。"
    },
}


class Database:
    def __init__(self):
        self.pool = None
        self.dsn = os.getenv("DATABASE_URL")
        self._lock = asyncio.Lock()
        # バッジJSON
        self.badge_file = os.path.join(
            os.path.dirname(__file__),
            "data",
            "user_badges.json"
        )
        os.makedirs(os.path.dirname(self.badge_file), exist_ok=True)
        if not os.path.exists(self.badge_file):
            with open(self.badge_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    # ←←← ここに追加する！！！
    # =========================
    # バッジ用：内部ヘルパー
    # =========================
    def _load_badges(self) -> dict:
        with open(self.badge_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_badges(self, data: dict):
        with open(self.badge_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def apply_passive_effect(stats: dict, pet: dict, context: dict) -> dict:
        passive_key = pet.get("passive_skill")
        passive = PASSIVE_SKILLS.get(passive_key)

        if not passive:
            return stats

        speed = stats["speed"]
        stamina = stats["stamina"]
        power = stats["power"]

        ptype = passive["type"]

        if ptype == "stat":
            target = passive["target"]
            stats[target] *= passive["multiplier"]

        elif ptype == "all":
            m = passive["multiplier"]
            speed *= m
            stamina *= m
            power *= m

        elif ptype == "trade":
            for k, v in passive["effects"].items():
                stats[k] *= v

        elif ptype == "gate_number":
            if context.get("gate") == passive["gate"]:
                m = passive["multiplier"]
                speed *= m
                stamina *= m
                power *= m

        elif ptype == "surface":
            if context.get("surface") == passive["surface"]:
                m = passive["multiplier"]
                speed *= m
                stamina *= m
                power *= m

        elif ptype == "distance":
            if context.get("distance") == passive["distance"]:
                m = passive["multiplier"]
                speed *= m
                stamina *= m
                power *= m

        elif ptype == "same_adult":
            if context.get("same_adult_exists"):
                m = passive["multiplier"]
                speed *= m
                stamina *= m
                power *= m

        elif ptype == "odds_rank":
            rank = context.get("odds_rank", 1)
            m = 1 + rank * 0.02
            speed *= m
            stamina *= m
            power *= m

        stats["speed"] = int(speed)
        stats["stamina"] = int(stamina)
        stats["power"] = int(power)

        return stats    

    def simulate_race(self, entries, race):
        DISTANCE_BALANCE = {
            "短距離": {"speed": 1.4, "power": 0.8, "stamina": 0.5},
            "マイル": {"speed": 1.2, "power": 1.2, "stamina": 0.8},
            "中距離": {"speed": 0.9, "power": 1.3, "stamina": 1.3},
            "長距離": {"speed": 0.6, "power": 1.0, "stamina": 1.6},
        }

        distance = race["distance"]
        surface = race["surface"]

        balance = DISTANCE_BALANCE.get(distance)
        if not balance:
            raise ValueError(f"不明な距離: {distance}")

        results = []

        for e in entries:

            # =========================
            # 🔎 同族判定
            # =========================
            same_adult_exists = any(
                other["adult_key"] == e["adult_key"] and other["pet_id"] != e["pet_id"]
                for other in entries
            )

            # =========================
            # 🔥 パッシブ適用
            # =========================
            stats = {
                "speed": e["speed"],
                "stamina": e["stamina"],
                "power": e["power"]
            }

            context = {
                "gate": e.get("gate"),
                "surface": surface,
                "distance": distance,
                "same_adult_exists": same_adult_exists
            }

            stats = self.apply_passive_effect(stats, e, context)
            # =========================
            # 🔥 根性発動判定
            # =========================
            happiness = e.get("happiness", 0)

            base_guts_rate = (happiness / 100) * 0.10

            if e.get("passive_skill") == "gambler":
                base_guts_rate += 0.05

            guts_triggered = random.random() < base_guts_rate

            # ① まず基礎スピードを作る
            base_speed = stats["speed"]

            # ② 根性補正
            if guts_triggered:
                base_speed *= 1.10

            # ③ 距離補正込み能力計算
            speed = base_speed * balance["speed"] + stats["power"] * balance["power"]

            speed = stats["speed"] * balance["speed"] + stats["power"] * balance["power"]
            stamina = stats["stamina"]



            stamina_loss = 50 * balance["stamina"]
            stamina_after = stamina - stamina_loss

            if stamina_after <= 0:
                speed *= 0.6

            rand_factor = random.uniform(0.95, 1.05)

            final_score = speed * rand_factor

            results.append({
                "pet_id": e["pet_id"],
                "user_id": e["user_id"],   
                "score": final_score,
                "guts": guts_triggered
            })

        results.sort(key=lambda x: x["score"], reverse=True)

        for i, r in enumerate(results):
            r["rank"] = i + 1

        return results

    # ------------------------------------------------------
    #   DB接続
    # ------------------------------------------------------
    async def connect(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=1,
                max_size=10
            )

    async def _ensure_pool(self):
        if self.pool is None:
            await self.connect()


    # ------------------------------------------------------
    #   初期化（テーブル自動作成）
    # ------------------------------------------------------
    async def init_db(self):
        await self.connect()

        # Users テーブル（ギルド別通貨管理）
        await self._execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
        """)

        # 給料ロールテーブル
        await self._execute("""
            CREATE TABLE IF NOT EXISTS role_salaries (
                role_id TEXT PRIMARY KEY,
                salary INTEGER NOT NULL
            );
        """)

        # Settings テーブル（1行固定）
        await self._execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                admin_roles TEXT[],         -- 通貨管理ロールID配列
                currency_unit TEXT,         -- 通貨単位
                log_pay TEXT,               -- 通貨ログ
                log_manage TEXT,            -- 管理ログ
                log_interview TEXT,         -- 面接ログ
                log_salary TEXT,            -- 給料ログ
                log_hotel TEXT,             -- ホテルログ
                log_backup TEXT             -- バックアップ用チャンネル
            );
        """)

        # サブスク設定テーブル
        await self._execute("""
            CREATE TABLE IF NOT EXISTS subscription_settings (
                guild_id TEXT PRIMARY KEY,
                standard_role TEXT,
                standard_price INTEGER,
                regular_role TEXT,
                regular_price INTEGER,
                premium_role TEXT,
                premium_price INTEGER,
                log_channel TEXT
            );
        """)

        # 面接設定テーブル
        await self._execute("""
            CREATE TABLE IF NOT EXISTS interview_settings (
                guild_id TEXT PRIMARY KEY,
                interviewer_role TEXT,
                wait_role TEXT,
                done_role TEXT,
                reward_amount INTEGER,
                log_channel TEXT
            );
        """)
        # -----------------------------------------
        # 既存 settings テーブルのカラム補完
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'settings';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        ADD_COLUMNS = {
            "log_pay": "TEXT",
            "log_manage": "TEXT",
            "log_interview": "TEXT",
            "log_salary": "TEXT",
            "log_hotel": "TEXT",
            "log_backup": "TEXT",
            "oasistchi_race_reset_date": "DATE",
        }

        for col, col_type in ADD_COLUMNS.items():
            if col not in existing_cols:
                print(f"🛠 settings テーブルに {col} カラムを追加します…")
                await self._execute(
                    f"ALTER TABLE settings ADD COLUMN {col} {col_type};"
                )

        # ホテル設定テーブル
        await self._execute("""
            CREATE TABLE IF NOT EXISTS hotel_settings (
                guild_id TEXT PRIMARY KEY,
                manager_role TEXT,
                log_channel TEXT,
                sub_role TEXT,
                ticket_price_1 INTEGER,
                ticket_price_10 INTEGER,
                ticket_price_30 INTEGER
            );
        """)

        # ホテルチケット所持テーブル
        await self._execute("""
            CREATE TABLE IF NOT EXISTS hotel_tickets (
                user_id TEXT,
                guild_id TEXT,
                tickets INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
        """)

        # ホテルルーム管理テーブル
        await self._execute("""
            CREATE TABLE IF NOT EXISTS hotel_rooms (
                channel_id TEXT PRIMARY KEY,
                guild_id TEXT,
                owner_id TEXT,
                expire_at TIMESTAMP
            );
        """)
        # ==================================================
        # おあしすっち（OASISTCHI）テーブル
        # ==================================================

        # ユーザーごとの育成枠
        await self._execute("""
            CREATE TABLE IF NOT EXISTS oasistchi_users (
                user_id TEXT PRIMARY KEY,
                slots INTEGER NOT NULL DEFAULT 1
            );
        """)

        # おあしすっち本体
        await self._execute("""
            CREATE TABLE IF NOT EXISTS oasistchi_pets (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,

                stage TEXT NOT NULL,              -- egg / adult
                egg_type TEXT,
                adult_key TEXT,
                name TEXT,

                growth REAL DEFAULT 0,
                hunger INTEGER DEFAULT 100,
                happiness INTEGER DEFAULT 50,
                poop BOOLEAN DEFAULT FALSE,

               notified_hatch BOOLEAN DEFAULT FALSE,

                last_pet REAL DEFAULT 0,
                last_interaction REAL DEFAULT 0,
                last_tick REAL DEFAULT 0,
                last_hunger_tick REAL DEFAULT 0,
                last_unhappy_tick REAL DEFAULT 0,

                notify_pet BOOLEAN DEFAULT FALSE,
                notify_care BOOLEAN DEFAULT FALSE,
                notify_food BOOLEAN DEFAULT FALSE,

                training_count INTEGER DEFAULT 0
            );
        """)
        # =========================
        # レース設定（ギルド別）
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_settings (
            guild_id TEXT PRIMARY KEY,
            result_channel_id TEXT
        );
        """)

        # ==================================================
        # おあしすっち：図鑑 / 通知（永続化）
        # ==================================================

        # 図鑑（成体履歴）
        await self._execute("""
            CREATE TABLE IF NOT EXISTS oasistchi_dex (
                user_id TEXT NOT NULL,
                adult_key TEXT NOT NULL,
                obtained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, adult_key)
            );
        """)

        # 通知設定
        await self._execute("""
            CREATE TABLE IF NOT EXISTS oasistchi_notify (
                user_id TEXT PRIMARY KEY,
                notify_poop BOOLEAN NOT NULL DEFAULT TRUE,
                notify_food BOOLEAN NOT NULL DEFAULT TRUE,
                notify_pet_ready BOOLEAN NOT NULL DEFAULT TRUE
            );
        """)

        # 既存DBにカラム補完（すでにテーブルがある場合）
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_notify';
        """)
        existing_cols = {row["column_name"] for row in col_check}

        NOTIFY_COLUMNS = {
            "notify_poop": "BOOLEAN NOT NULL DEFAULT TRUE",
            "notify_food": "BOOLEAN NOT NULL DEFAULT TRUE",
            "notify_pet_ready": "BOOLEAN NOT NULL DEFAULT TRUE",
        }
        for col, col_type in NOTIFY_COLUMNS.items():
            if col not in existing_cols:
                await self._execute(f"ALTER TABLE oasistchi_notify ADD COLUMN {col} {col_type};")

        # -----------------------------------------
        # settings テーブルに race_result_channel_id を追加
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'settings'
        """)

        existing_cols = {row["column_name"] for row in col_check}

        if "race_result_channel_id" not in existing_cols:
            print("🛠 settings テーブルに race_result_channel_id を追加します")
            await self._execute("""
                ALTER TABLE settings
                ADD COLUMN race_result_channel_id TEXT
            """)
            print("✅ race_result_channel_id 追加完了")

        # =========================
        # レース関連テーブル
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_schedules (
            id SERIAL PRIMARY KEY,
            race_no INTEGER NOT NULL,
            race_time TIME NOT NULL,
            entry_open_minutes INTEGER NOT NULL,
            max_entries INTEGER NOT NULL DEFAULT 8,
            entry_fee INTEGER NOT NULL DEFAULT 50000,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_entries (
            id SERIAL PRIMARY KEY,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            pet_id INTEGER NOT NULL,
            paid BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (race_date, schedule_id, pet_id)
        );
        """)

        # =========================
        # 馬券関連テーブル（パリミュチュエル方式）
        # =========================

        # 個別馬券
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_bets (
            id SERIAL PRIMARY KEY,
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            pet_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # 🔧 race_bets に race_id カラム補完
        cols = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_bets';
        """)
        existing_cols = {c["column_name"] for c in cols}

        if "race_id" not in existing_cols:
            print("🛠 race_bets に race_id カラムを追加します…")
            await self._execute("""
                ALTER TABLE race_bets
                ADD COLUMN race_id TEXT;
            """)
            print("✅ race_id 追加完了")




        # レースごとの総プール
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_pools (
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            total_pool INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, race_date, schedule_id)
        );
        """)
        # =========================
        # レース結果テーブル
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_results (
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            pet_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            final_score DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (guild_id, race_date, schedule_id, pet_id)
        );
        """)
        # 🔥 ペット別プール（重要）
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_pet_pools (
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            pet_id INTEGER NOT NULL,
            total_amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, race_date, schedule_id, pet_id)
        );
        """)

        # =========================
        # 3連単：サーバー単位キャリー
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_trifecta_carry (
            guild_id TEXT PRIMARY KEY,
            carry_over BIGINT NOT NULL DEFAULT 0
        );
        """)


        # =========================
        # 3連単：総プール（キャリー対応）3.1
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_trifecta_pools (
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            total_pool INTEGER NOT NULL DEFAULT 0,
            carry_in INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, race_date, schedule_id)
        );
        """)

        # =========================
        # 3連単：組み合わせ別プール3.1
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_trifecta_combo_pools (
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            first_pet_id INTEGER NOT NULL,
            second_pet_id INTEGER NOT NULL,
            third_pet_id INTEGER NOT NULL,
            total_amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (
                guild_id,
                race_date,
                schedule_id,
                first_pet_id,
                second_pet_id,
                third_pet_id
            )
        );
        """)

        # 3連単：ユーザー別ベット3.1
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS race_trifecta_bets (
            id SERIAL PRIMARY KEY,
            guild_id TEXT NOT NULL,
            race_date DATE NOT NULL,
            schedule_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            first_pet_id INTEGER NOT NULL,
            second_pet_id INTEGER NOT NULL,
            third_pet_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # =========================
        # ユーザーバッジ
        # =========================
        await self._execute("""
        CREATE TABLE IF NOT EXISTS user_badges (
            guild_id TEXT NOT NULL,
            user_id  TEXT NOT NULL,
            badge    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (guild_id, user_id, badge)
        );
        """)




        # -----------------------------------------
        # race_entries に status カラムがなければ追加
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_entries';
        """)
        existing_cols = {r["column_name"] for r in col_check}

        if "status" not in existing_cols:
            print("🛠 race_entries に status カラムを追加します…")
            await self._execute("""
                ALTER TABLE race_entries
                ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
            """)
            print("✅ status カラム追加完了")

        # --------------------------------------------------
        # おあしすっち：レース用カラム補完
        # --------------------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        # --------------------------------------------------
        # おあしすっち：特訓回数カラム補完（★今回の修正点）
        # --------------------------------------------------
        if "training_count" not in existing_cols:
            print("🛠 oasistchi_pets に training_count カラムを追加します…")
            await self._execute("""
                ALTER TABLE oasistchi_pets
                ADD COLUMN training_count INTEGER NOT NULL DEFAULT 0;
            """)

        ADD_COLUMNS = {
            "raced_today": "BOOLEAN DEFAULT FALSE",
            "race_candidate": "BOOLEAN DEFAULT FALSE",
        }

        for col, col_type in ADD_COLUMNS.items():
            if col not in existing_cols:
                print(f"🛠 oasistchi_pets に {col} カラムを追加します…")
                await self._execute(
                    f"ALTER TABLE oasistchi_pets ADD COLUMN {col} {col_type};"
                )

        # settings テーブルに guild_id がなければ追加
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'settings';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        if "guild_id" not in existing_cols:
            print("🛠 settings テーブルに guild_id カラムを追加します…")
            await self._execute("""
                ALTER TABLE settings
                ADD COLUMN guild_id TEXT;
            """)

        # --------------------------------------------------
        # おあしすっち：パッシブスキルカラム補完
        # --------------------------------------------------
        if "passive_skill" not in existing_cols:
            print("🛠 oasistchi_pets に passive_skill カラムを追加します…")
            await self._execute("""
                ALTER TABLE oasistchi_pets
                ADD COLUMN IF NOT EXISTS passive_skill TEXT;
            """)
            print("✅ passive_skill 追加完了")



        # --------------------------------------------------
        # おあしすっち：ステータス（特訓用）カラム補完
        # --------------------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        ADD_COLUMNS = {
            "base_speed": "INTEGER DEFAULT 0",
            "base_stamina": "INTEGER DEFAULT 0",
            "base_power": "INTEGER DEFAULT 0",
            "train_speed": "INTEGER DEFAULT 0",
            "train_stamina": "INTEGER DEFAULT 0",
            "train_power": "INTEGER DEFAULT 0",
        }

        for col, col_type in ADD_COLUMNS.items():
            if col not in existing_cols:
                await self._execute(
                    f"ALTER TABLE oasistchi_pets ADD COLUMN {col} {col_type};"
                )
        # --------------------------------------------------
        # おあしすっち：ステータス用カラム補完
        # --------------------------------------------------
        ADD_STATUS_COLUMNS = {
            "speed": "INTEGER DEFAULT 0",
            "stamina": "INTEGER DEFAULT 0",
            "power": "INTEGER DEFAULT 0",
        }

        for col, col_type in ADD_STATUS_COLUMNS.items():
            if col not in existing_cols:
                print(f"🛠 oasistchi_pets に {col} カラムを追加します…")
                await self._execute(
                    f"ALTER TABLE oasistchi_pets ADD COLUMN {col} {col_type};"
                )

        # --------------------------------------------------
        # おあしすっち：時間管理用カラム補完
        # --------------------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        TIME_COLUMNS = {
            "last_poop_tick": "REAL DEFAULT 0",
            "last_growth_tick": "REAL DEFAULT 0",
            "last_hunger_tick": "REAL DEFAULT 0",
            "last_unhappy_tick": "REAL DEFAULT 0",
        }

        for col, col_type in TIME_COLUMNS.items():
            if col not in existing_cols:
                print(f"🛠 oasistchi_pets に {col} カラムを追加します…")
                await self._execute(
                    f"ALTER TABLE oasistchi_pets ADD COLUMN {col} {col_type};"
                )

        # --------------------------------------------------
        # おあしすっち：通知予定時刻カラム（★再起動耐性）
        # --------------------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)
        existing_cols = {row["column_name"] for row in col_check}

        NOTIFY_TIME_COLUMNS = {
            "next_poop_check_at": "REAL DEFAULT 0",
            "poop_notified_at": "REAL DEFAULT 0",
            "pet_ready_at": "REAL DEFAULT 0",
            "pet_ready_notified_at": "REAL DEFAULT 0",
        }

        for col, col_type in NOTIFY_TIME_COLUMNS.items():
            if col not in existing_cols:
                print(f"🛠 oasistchi_pets に {col} カラムを追加します…")
                await self._execute(
                    f"ALTER TABLE oasistchi_pets ADD COLUMN {col} {col_type};"
                )
        # -----------------------------------------
        # oasistchi_pets カラム補完
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        if "fixed_adult_key" not in existing_cols:
            print("🛠 oasistchi_pets に fixed_adult_key カラムを追加します…")
            await self._execute("""
                ALTER TABLE oasistchi_pets
                ADD COLUMN fixed_adult_key TEXT;
            """)
            print("✅ fixed_adult_key カラム追加完了")

        # --------------------------------------------------
        # レース関連カラム補完2.2
        # --------------------------------------------------

        # race_schedules
        cols = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_schedules';
        """)
        race_schedule_cols = {r["column_name"] for r in cols}

        if "race_finished" not in race_schedule_cols:
            print("🛠 race_schedules に race_finished を追加します…")
            await self._execute("""
                ALTER TABLE race_schedules
                ADD COLUMN race_finished BOOLEAN DEFAULT FALSE;
            """)
            print("✅ race_finished 追加完了")

        # race_entries
        cols = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_entries';
        """)
        race_entry_cols = {r["column_name"] for r in cols}

        if "rank" not in race_entry_cols:
            print("🛠 race_entries に rank を追加します…")
            await self._execute("""
                ALTER TABLE race_entries
                ADD COLUMN rank INTEGER;
            """)
            print("✅ rank 追加完了")

        if "score" not in race_entry_cols:
            print("🛠 race_entries に score を追加します…")
            await self._execute("""
                ALTER TABLE race_entries
                ADD COLUMN score REAL;
            """)
            print("✅ score 追加完了")


        

        
        # -----------------------------------------
        # race_schedules に lottery_done が無ければ追加
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_schedules';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        if "lottery_done" not in existing_cols:
            print("🛠 race_schedules に lottery_done カラムを追加します…")
            await self._execute("""
                ALTER TABLE race_schedules
                ADD COLUMN lottery_done BOOLEAN DEFAULT FALSE;
            """)
            print("✅ lottery_done カラム追加完了")

        await self._execute("""
            UPDATE race_schedules
            SET lottery_done = FALSE
            WHERE lottery_done IS NULL;
        """)
        # -----------------------------------------
        # race_schedules に locked が無ければ追加
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_schedules';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        if "locked" not in existing_cols:
            print("🛠 race_schedules に locked カラムを追加します…")
            await self._execute("""
                ALTER TABLE race_schedules
                ADD COLUMN locked BOOLEAN DEFAULT FALSE;
            """)
            print("✅ locked カラム追加完了")

        # NULL対策（念のため）
        await self._execute("""
            UPDATE race_schedules
            SET locked = FALSE
            WHERE locked IS NULL;
        """)

        # -----------------------------------------
        # race_schedules に reward_paid が無ければ追加
        # -----------------------------------------
        if "reward_paid" not in existing_cols:
            print("🛠 race_schedules に reward_paid カラムを追加します…")
            await self._execute("""
                ALTER TABLE race_schedules
                ADD COLUMN reward_paid BOOLEAN DEFAULT FALSE;
            """)
            print("✅ reward_paid カラム追加完了")

        # NULL対策（念のため）
        await self._execute("""
            UPDATE race_schedules
            SET reward_paid = FALSE
            WHERE reward_paid IS NULL;
        """)


        # -----------------------------------------
        # race_schedules テーブルに レース用
        # -----------------------------------------
        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_schedules';
        """)

        existing_cols = {row["column_name"] for row in col_check}

        if "race_date" not in existing_cols:
            print("🛠 race_schedules テーブルに race_date カラムを追加します…")
            await self._execute("""
                ALTER TABLE race_schedules
                ADD COLUMN race_date DATE;
            """)

            # 既存データがあれば今日の日付を入れる
            await self._execute("""
                UPDATE race_schedules
                SET race_date = CURRENT_DATE
                WHERE race_date IS NULL;
            """)

            print("✅ race_date カラム追加完了")
        # --------------------------------------------------
        # おあしすっち：通知時刻の正規化（安全版）
        # --------------------------------------------------
        now = time.time()

        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)
        cols = {row["column_name"] for row in col_check}

        # 💩 うんち：次回チェック時刻が未設定の個体
        if "next_poop_check_at" in cols:
            await self._execute("""
                UPDATE oasistchi_pets
                SET next_poop_check_at = $1
                WHERE next_poop_check_at = 0;
            """, now + 3600)

        # 🤚 なでなで：last_pet があるのに予定時刻が無い個体
        if "pet_ready_at" in cols:
            await self._execute("""
                UPDATE oasistchi_pets
                SET pet_ready_at = last_pet + 10800
                WHERE last_pet > 0 AND pet_ready_at = 0;
            """)
        

        col_check = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'oasistchi_pets';
        """)
        existing_cols = {row["column_name"] for row in col_check}

        ALERT_COLUMNS = {
            "poop_alerted": "BOOLEAN NOT NULL DEFAULT FALSE",
            "hunger_alerted": "BOOLEAN NOT NULL DEFAULT FALSE",
            "pet_ready_alerted_for": "REAL NOT NULL DEFAULT 0",
        }
        for col, col_type in ALERT_COLUMNS.items():
            if col not in existing_cols:
                print(f"🛠 oasistchi_pets に {col} カラムを追加します…")
                await self._execute(f"ALTER TABLE oasistchi_pets ADD COLUMN {col} {col_type};")
        # 初期設定が無ければ作成
        exists = await self._execute("""
            INSERT INTO settings
                (id, admin_roles, currency_unit,
                 log_pay, log_manage, log_interview, log_salary, log_hotel, log_backup)
            VALUES
                (1, ARRAY[]::TEXT[], 'rrc',
                 NULL, NULL, NULL, NULL, NULL, NULL)
            ON CONFLICT (id) DO NOTHING;
        """)

        print("🔧 Settings 初期化行を作成しました")

        # db.py の init_db() 内、hotel_settings 作成の後あたりに追記
        col_check = await self._fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'hotel_settings';
        """)
        existing_cols = {row["column_name"] for row in col_check}

        if "category_ids" not in existing_cols:
            await self._execute("""
                ALTER TABLE hotel_settings ADD COLUMN category_ids TEXT[];
            """)
            await self._execute("""
                UPDATE hotel_settings SET category_ids = ARRAY[]::TEXT[] WHERE category_ids IS NULL;
            """)

        # ==================================================
        #テーブル初期化
        # ==================================================
        await self.init_jumbo_tables()
        await self.ensure_race_schedule_columns()
        await self.ensure_race_entry_columns()
        await self.ensure_race_results_columns()
        await self.ensure_race_schedule_time_text()
        await self.init_race_tables()


    # ------------------------------------------------------
    #   ユーザー残高（ギルド別管理）
    # ------------------------------------------------------
    async def get_user(self, user_id, guild_id):
        await self._ensure_pool()
        user_id = str(user_id)
        guild_id = str(guild_id)
        await self._execute("""
            INSERT INTO users (user_id, guild_id, balance)
            VALUES ($1, $2, 0)
            ON CONFLICT (user_id, guild_id) DO NOTHING
        """, user_id, guild_id)
        return await self._fetchrow(
            "SELECT * FROM users WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id
        )

    async def set_balance(self, user_id, guild_id, amount):
        await self._ensure_pool()
        async with self._lock:
            await self._execute(
                """
                INSERT INTO users (user_id, guild_id, balance)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET balance = $3
                """,
                user_id, guild_id, amount
            )


    async def add_balance(self, user_id, guild_id, amount):
        await self._ensure_pool()
        user_id = str(user_id)
        guild_id = str(guild_id)
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                INSERT INTO users (user_id, guild_id, balance)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET balance = users.balance + $3
                RETURNING balance
            """, user_id, guild_id, amount)

    async def remove_balance(self, user_id, guild_id, amount):
        await self._ensure_pool()
        user_id = str(user_id)
        guild_id = str(guild_id)
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                UPDATE users
                SET balance = GREATEST(0, balance - $3)
                WHERE user_id=$1 AND guild_id=$2
                RETURNING balance
            """, user_id, guild_id, amount) or 0


    async def get_all_balances(self, guild_id):
        await self._ensure_pool()
        return await self._fetch(
            "SELECT * FROM users WHERE guild_id=$1 ORDER BY balance DESC",
            guild_id
        )

    # ------------------------------------------------------
    #   給料ロール関連
    # ------------------------------------------------------
    async def set_salary(self, role_id, salary):
        await self._execute("""
            INSERT INTO role_salaries (role_id, salary)
            VALUES ($1, $2)
            ON CONFLICT (role_id)
            DO UPDATE SET salary=$2;
        """, role_id, salary)

    async def get_salaries(self):
        return await self._fetch("SELECT * FROM role_salaries")

    # ------------------------------------------------------
    #   Settings
    # ------------------------------------------------------
    async def get_settings(self):
        await self._ensure_pool()
        return await self._fetchrow(
            "SELECT * FROM settings WHERE id = 1"
        )

    async def update_settings(self, **kwargs):
        columns = []
        values = []
        idx = 1

        for key, value in kwargs.items():
            columns.append(f"{key} = ${idx}")
            values.append(value)
            idx += 1

        sql = f"UPDATE settings SET {', '.join(columns)} WHERE id = 1"
        await self._execute(sql, *values)

    # ------------------------------------------------------
    #   ホテルチケット管理
    # ------------------------------------------------------
    async def get_tickets(self, user_id, guild_id):
        row = await self._fetchrow(
            "SELECT tickets FROM hotel_tickets WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id
        )
        if not row:
            # 自動作成
            await self._execute(
                "INSERT INTO hotel_tickets (user_id, guild_id, tickets) VALUES ($1, $2, 0)",
                user_id, guild_id
            )
            return 0
        return row["tickets"]

    async def add_tickets(self, user_id, guild_id, amount):
        current = await self.get_tickets(user_id, guild_id)
        new_amount = current + amount
        await self._execute(
            "UPDATE hotel_tickets SET tickets=$1 WHERE user_id=$2 AND guild_id=$3",
            new_amount, user_id, guild_id
        )
        return new_amount

    async def remove_tickets(self, user_id, guild_id, amount):
        current = await self.get_tickets(user_id, guild_id)
        new_amount = max(0, current - amount)
        await self._execute(
            "UPDATE hotel_tickets SET tickets=$1 WHERE user_id=$2 AND guild_id=$3",
            new_amount, user_id, guild_id
        )
        return new_amount

    # ------------------------------------------------------
    #   ホテルルーム管理
    # ------------------------------------------------------
    async def save_room(self, channel_id, guild_id, owner_id, expire_at):
        await self._execute("""
            INSERT INTO hotel_rooms (channel_id, guild_id, owner_id, expire_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (channel_id)
            DO UPDATE SET expire_at=$4;
        """, channel_id, guild_id, owner_id, expire_at)

    async def delete_room(self, channel_id):
        await self._execute(
            "DELETE FROM hotel_rooms WHERE channel_id=$1",
            channel_id
        )

    async def get_room(self, channel_id):
        return await self._fetchrow(
            "SELECT * FROM hotel_rooms WHERE channel_id=$1",
            channel_id
        )
    # ------------------------------------------------------
    #   バックアップ用スナップショット
    #   users（残高）と hotel_tickets（チケット）をまとめてJSON化
    # ------------------------------------------------------
    async def export_user_snapshot(self) -> dict:
        """全ユーザーの残高・チケットをまとめて取得してJSON用dictで返す"""

        users_rows = await self._fetch(
            "SELECT user_id, guild_id, balance FROM users"
        )
        tickets_rows = await self._fetch(
            "SELECT user_id, guild_id, tickets FROM hotel_tickets"
        )

        users = []
        for r in users_rows:
            users.append(
                {
                    "user_id": str(r["user_id"]),
                    "guild_id": str(r["guild_id"]),
                    "balance": int(r["balance"]),
                }
            )

        tickets = []
        for r in tickets_rows:
            tickets.append(
                {
                    "user_id": str(r["user_id"]),
                    "guild_id": str(r["guild_id"]),
                    "tickets": int(r["tickets"]),
                }
            )

        return {
            "version": 1,
            "users": users,
            "tickets": tickets,
        }

    # ------------------------------------------------------
    #   スナップショットからの復元
    #   overwrite=True のときは全削除してから上書き
    # ------------------------------------------------------
    async def import_user_snapshot(self, snapshot: dict, overwrite: bool = False):
        """export_user_snapshot で出力したJSONから復元する"""

        if overwrite:
            # 全削除してから入れ直す
            await self._execute("TRUNCATE TABLE users")
            await self._execute("TRUNCATE TABLE hotel_tickets")

        # users の復元
        for row in snapshot.get("users", []):
            user_id = str(row["user_id"])
            guild_id = str(row["guild_id"])
            balance = int(row["balance"])

            exists = await self._fetchrow(
                "SELECT 1 FROM users WHERE user_id=$1 AND guild_id=$2",
                user_id, guild_id,
            )
            if exists:
                await self._execute(
                    "UPDATE users SET balance=$1 WHERE user_id=$2 AND guild_id=$3",
                    balance, user_id, guild_id,
                )
            else:
                await self._execute(
                    "INSERT INTO users (user_id, guild_id, balance) VALUES ($1, $2, $3)",
                    user_id, guild_id, balance,
                )

        # hotel_tickets の復元
        for row in snapshot.get("tickets", []):
            user_id = str(row["user_id"])
            guild_id = str(row["guild_id"])
            tickets = int(row["tickets"])

            exists = await self._fetchrow(
                "SELECT 1 FROM hotel_tickets WHERE user_id=$1 AND guild_id=$2",
                user_id, guild_id,
            )
            if exists:
                await self._execute(
                    "UPDATE hotel_tickets SET tickets=$1 WHERE user_id=$2 AND guild_id=$3",
                    tickets, user_id, guild_id,
                )
            else:
                await self._execute(
                    "INSERT INTO hotel_tickets (user_id, guild_id, tickets) "
                    "VALUES ($1, $2, $3)",
                    user_id, guild_id, tickets,
                )

# ======================================================
#   年末ジャンボ（JUMBO）機能
# ======================================================

    # --------------------------------------------------
    #   テーブル初期化（init_db から呼ばれる想定）
    # --------------------------------------------------
    async def init_jumbo_tables(self):
        await self._ensure_pool()

        # 開催設定
        await self._execute("""
            CREATE TABLE IF NOT EXISTS jumbo_config (
                guild_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                deadline TIMESTAMP NOT NULL,
                is_open BOOLEAN NOT NULL DEFAULT TRUE,
                winning_number VARCHAR(6),
                prize_paid BOOLEAN DEFAULT FALSE,
                panel_channel_id TEXT,
                panel_message_id TEXT
            );
        """)

        # 購入番号
        await self._execute("""
            CREATE TABLE IF NOT EXISTS jumbo_entries (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                number VARCHAR(6) NOT NULL,
                PRIMARY KEY (guild_id, number)
            );
        """)

        # 当選者
        await self._execute("""
            CREATE TABLE IF NOT EXISTS jumbo_winners (
                guild_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                number VARCHAR(6) NOT NULL,
                user_id TEXT NOT NULL,
                match_count INTEGER,
                prize BIGINT DEFAULT 0,
                PRIMARY KEY (guild_id, rank, number)
            );
        """)

    # --------------------------------------------------
    #   開催設定
    # --------------------------------------------------
    async def jumbo_set_config(self, guild_id, title, description, deadline):
        await self._ensure_pool()
        await self._execute("""
            INSERT INTO jumbo_config
                (guild_id, title, description, deadline, is_open)
            VALUES ($1, $2, $3, $4, TRUE)
            ON CONFLICT (guild_id)
            DO UPDATE SET
                title=$2,
                description=$3,
                deadline=$4,
                is_open=TRUE;
        """, guild_id, title, description, deadline)

    async def jumbo_get_config(self, guild_id):
        await self._ensure_pool()
        return await self._fetchrow(
            "SELECT * FROM jumbo_config WHERE guild_id=$1",
            guild_id
        )

    async def jumbo_close_config(self, guild_id):
        await self._ensure_pool()
        await self._execute("""
            UPDATE jumbo_config SET is_open=FALSE WHERE guild_id=$1
        """, guild_id)

    async def jumbo_reset_config(self, guild_id):
        await self._ensure_pool()
        await self._execute(
            "DELETE FROM jumbo_config WHERE guild_id=$1",
            guild_id
        )

    async def jumbo_set_panel_message(self, guild_id, channel_id, message_id):
        await self._ensure_pool()
        await self._execute("""
            UPDATE jumbo_config
            SET panel_channel_id=$2,
                panel_message_id=$3
            WHERE guild_id=$1
        """, guild_id, channel_id, message_id)

    # --------------------------------------------------
    #   購入番号
    # --------------------------------------------------
    async def jumbo_add_number(self, guild_id, user_id, number):
        await self._ensure_pool()
        try:
            await self._execute("""
                INSERT INTO jumbo_entries (guild_id, user_id, number)
                VALUES ($1, $2, $3)
            """, guild_id, user_id, number)
            return True
        except asyncpg.exceptions.UniqueViolationError:
            return False

    async def jumbo_get_user_numbers(self, guild_id, user_id):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT number FROM jumbo_entries
            WHERE guild_id=$1 AND user_id=$2
            ORDER BY number ASC
        """, guild_id, user_id)

    async def jumbo_get_all_entries(self, guild_id):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT guild_id, user_id, number
            FROM jumbo_entries
            WHERE guild_id=$1
        """, guild_id)

    async def jumbo_clear_entries(self, guild_id):
        await self._ensure_pool()
        await self._execute(
            "DELETE FROM jumbo_entries WHERE guild_id=$1",
            guild_id
        )

    async def jumbo_count_entries(self, guild_id):
        await self._ensure_pool()
        row = await self._fetchrow(
            "SELECT COUNT(*) AS cnt FROM jumbo_entries WHERE guild_id=$1",
            guild_id
        )
        return row["cnt"] if row else 0

    # --------------------------------------------------
    #   当選番号・当選者
    # --------------------------------------------------
    async def jumbo_set_winning_number(self, guild_id, winning_number):
        await self._ensure_pool()
        result = await self._execute("""
            UPDATE jumbo_config
            SET winning_number=$2,
                prize_paid=FALSE
            WHERE guild_id=$1
        """, guild_id, winning_number)

        if result == "UPDATE 0":
            raise RuntimeError("ジャンボが未開催です")

    async def jumbo_add_winner(
        self, guild_id, rank, number, user_id, match_count, prize
    ):
        await self._ensure_pool()
        await self._execute("""
            INSERT INTO jumbo_winners
                (guild_id, rank, number, user_id, match_count, prize)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
        """, guild_id, rank, number, user_id, match_count, prize)

    async def jumbo_get_winners(self, guild_id):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT * FROM jumbo_winners
            WHERE guild_id=$1
            ORDER BY rank ASC, number ASC
        """, guild_id)

    async def jumbo_clear_winners(self, guild_id):
        await self._ensure_pool()
        await self._execute(
            "DELETE FROM jumbo_winners WHERE guild_id=$1",
            guild_id
        )
    # --------------------------------------------------
    #   ジャンボ購入枚数
    # --------------------------------------------------
    async def jumbo_count_user_entries(self, guild_id, user_id):
        await self._ensure_pool()
        row = await self._fetchrow("""
            SELECT COUNT(*) AS cnt
            FROM jumbo_entries
            WHERE guild_id=$1 AND user_id=$2
        """, guild_id, user_id)
        return row["cnt"] if row else 0
    # ------------------------------------------------------
    #   ジャンボ：ユーザーの所持口数
    # ------------------------------------------------------
    async def jumbo_get_user_count(self, guild_id: str, user_id: str) -> int:
        await self._ensure_pool()
        row = await self._fetchrow(
            """
            SELECT COUNT(*) AS cnt
            FROM jumbo_entries
            WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id,
            user_id,
        )
        return row["cnt"] if row else 0

    # ================================
    # ジャンボ：給付済み等級取得
    # ================================
    async def jumbo_get_paid_ranks(self, guild_id: str) -> list[int]:
        row = await self._fetchrow(
            "SELECT paid_ranks FROM jumbo_config WHERE guild_id = $1",
            guild_id
        )
        return row["paid_ranks"] if row and row["paid_ranks"] else []


    # ================================
    # ジャンボ：給付済み等級更新
    # ================================
    async def jumbo_add_paid_rank(self, guild_id: str, rank: int):
        await self._execute("""
            UPDATE jumbo_config
            SET paid_ranks = (
                SELECT ARRAY(
                    SELECT DISTINCT unnest(coalesce(paid_ranks, '{}') || $2::INTEGER)
                )
            )
            WHERE guild_id = $1
        """, guild_id, rank)

    # -------------------------------
    # おあしすっち：ユーザー
    # -------------------------------
    async def get_oasistchi_user(self, user_id: str):
        await self._ensure_pool()
        row = await self._fetchrow(
            "SELECT * FROM oasistchi_users WHERE user_id=$1",
            user_id
        )
        if not row:
            await self._execute(
                "INSERT INTO oasistchi_users (user_id, slots) VALUES ($1, 1)",
                user_id
            )
            row = await self._fetchrow(
                "SELECT * FROM oasistchi_users WHERE user_id=$1",
                user_id
            )
        return row


    async def add_oasistchi_slot(self, user_id: str, amount: int = 1):
        await self.get_oasistchi_user(user_id)
        await self._execute(
            "UPDATE oasistchi_users SET slots = slots + $2 WHERE user_id=$1",
            user_id, amount
        )

    # -------------------------------
    # おあしすっち：取得
    # -------------------------------
    async def get_oasistchi_pets(self, user_id: str):
        await self._ensure_pool()
        return await self._fetch(
            "SELECT * FROM oasistchi_pets WHERE user_id=$1 ORDER BY id ASC",
            user_id
        )


    # -------------------------------
    # おあしすっち：追加（たまご購入）
    # -------------------------------
    async def add_oasistchi_egg(
        self,
        user_id: str,
        egg_type: str,
        *,
        fixed_adult_key: str | None = None
    ):
        now = time.time()
        await self._execute("""
            INSERT INTO oasistchi_pets (
                user_id,
                stage,
                egg_type,
                fixed_adult_key,
                growth,
                hunger,
                happiness,
                poop,
                last_interaction,
                last_growth_tick,
                last_poop_tick,
                next_poop_check_at
            ) VALUES (
                $1,
                'egg',
                $2,
                $3,
                0::REAL,
                100,
                50,
                FALSE,
                $4::REAL,
                $4::REAL,
                $4::REAL,
                ($4 + 3600)::REAL
            )
        """,
        user_id,
        egg_type,
        fixed_adult_key,
        now)

    # ==================================================
    # おあしすっち：たまご購入（完全安全版）
    # ==================================================
    async def purchase_oasistchi_egg_safe(
        self,
        user_id: str,
        guild_id: str,
        egg_type: str,
        price: int,
        *,
        fixed_adult_key: str | None = None
    ):
        await self._ensure_pool()

        async with self._lock:
            async with self.pool.acquire() as conn:
                async with conn.transaction():

                    # ① 残高取得（ロック）
                    row = await conn.fetchrow(
                        """
                        SELECT balance
                        FROM users
                        WHERE user_id=$1 AND guild_id=$2
                        FOR UPDATE
                        """,
                        user_id,
                        guild_id
                    )

                    if not row:
                        raise RuntimeError("ユーザーが存在しません")

                    if row["balance"] < price:
                        raise RuntimeError("残高不足")

                    # ② 残高減算
                    await conn.execute(
                        """
                        UPDATE users
                        SET balance = balance - $1
                        WHERE user_id=$2 AND guild_id=$3
                        """,
                        price, user_id, guild_id
                    )

                    # ③ たまご追加
                    now = time.time()
                    await conn.execute(
                        """
                        INSERT INTO oasistchi_pets (
                            user_id,
                            stage,
                            egg_type,
                            fixed_adult_key,
                            growth,
                            hunger,
                            happiness,
                            poop,
                            last_interaction,
                            last_growth_tick,
                            last_poop_tick,
                            next_poop_check_at
                        ) VALUES (
                            $1,
                            'egg',
                            $2,
                            $3,
                            0,
                            100,
                            50,
                            FALSE,
                            $4::REAL,
                            $4::REAL,
                            $4::REAL,
                            ($4::REAL + 3600)
                        )
                        """,
                        user_id,
                        egg_type,
                        fixed_adult_key,
                        now
                    )

    # ==================================================
    # おあしすっち：かぶりなし たまご（完全安全）
    # ==================================================
    async def purchase_unique_egg_safe(
        self,
        user_id: str,
        guild_id: str,
        price: int,
        adult_catalog: list[dict]
    ):
        """
        ・残高チェック
        ・残高減算
        ・未所持 adult 抽選
        ・卵追加
        を1トランザクションで行う
        """
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # -------------------------
                # 残高ロック
                # -------------------------
                row = await conn.fetchrow(
                    """
                    SELECT balance
                    FROM users
                    WHERE user_id=$1 AND guild_id=$2
                    FOR UPDATE
                    """,
                    user_id, guild_id
                )

                if not row or row["balance"] < price:
                    raise RuntimeError("残高が足りません")

                # -------------------------
                # 所持済み成体取得（ロック不要）
                # -------------------------
                owned_rows = await conn.fetch(
                "SELECT adult_key FROM oasistchi_dex WHERE user_id=$1",
                    user_id
                )
                owned = {r["adult_key"] for r in owned_rows}

                candidates = [
                    a for a in adult_catalog
                    if a["key"] not in owned
                ]

                if not candidates:
                    raise RuntimeError("すべてのおあしすっちを所持済みです")

                adult = random.choice(candidates)
                egg_type = random.choice(adult["groups"])
                now = time.time()

                # -------------------------
                # 残高減算
                # -------------------------
                await conn.execute(
                    """
                    UPDATE users
                    SET balance = balance - $1
                    WHERE user_id=$2 AND guild_id=$3
                    """,
                    price, user_id, guild_id
                )

                # -------------------------
                # 卵追加（固定成体）
                # -------------------------
                await conn.execute(
                    """
                    INSERT INTO oasistchi_pets (
                        user_id, stage, egg_type, fixed_adult_key,
                        growth, hunger, happiness, poop,
                        last_interaction,
                        last_growth_tick,
                        last_poop_tick,
                        next_poop_check_at
                    ) VALUES (
                        $1, 'egg', $2, $3,
                        0::REAL,
                        100,
                        50,
                        FALSE,
                        $4::REAL,
                        $4::REAL,
                        $4::REAL,
                        ($4 + 3600)::REAL
                    )
                    """,
                    user_id,
                    egg_type,
                    adult["key"],
                    now
                )

                return adult, egg_type



    # ==================================================
    # おあしすっち：育成枠購入（完全安全）
    # ==================================================
    async def purchase_oasistchi_slot_safe(
        self,
        user_id: str,
        guild_id: str,
        base_price: int,
        max_slots: int = 10
    ) -> int:
        """
        ・残高チェック
        ・現在の育成枠チェック
        ・価格計算（5枠以上で2倍）
        ・残高減算
        ・育成枠 +1
        を1トランザクションで行う

        return: 購入後の slots 数
        """
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # -------------------------
                # 残高ロック
                # -------------------------
                bal = await conn.fetchrow(
                    """
                    SELECT balance
                    FROM users
                    WHERE user_id=$1 AND guild_id=$2
                    FOR UPDATE
                    """,
                    user_id, guild_id
                )

                if not bal:
                    raise RuntimeError("残高情報が見つかりません")

                # -------------------------
                # 育成枠ロック
                # -------------------------
                row = await conn.fetchrow(
                    """
                    SELECT slots
                    FROM oasistchi_users
                    WHERE user_id=$1
                    FOR UPDATE
                    """,
                    user_id
                )

                # 初回ユーザー対策
                if not row:
                    await conn.execute(
                        "INSERT INTO oasistchi_users (user_id, slots) VALUES ($1, 1)",
                        user_id
                    )
                    slots = 1
                else:
                    slots = row["slots"]

                if slots >= max_slots:
                    raise RuntimeError("育成枠は最大まで拡張されています")

                # -------------------------
                # 価格計算
                # -------------------------
                price = base_price * 2 if slots >= 5 else base_price

                if bal["balance"] < price:
                    raise RuntimeError("残高が足りません")

                # -------------------------
                # 残高減算
                # -------------------------
                await conn.execute(
                    """
                    UPDATE users
                    SET balance = balance - $1
                    WHERE user_id=$2 AND guild_id=$3
                    """,
                    price, user_id, guild_id
                )

                # -------------------------
                # 育成枠 +1
                # -------------------------
                await conn.execute(
                    """
                    UPDATE oasistchi_users
                    SET slots = slots + 1
                    WHERE user_id=$1
                    """,
                    user_id
                )

                return slots + 1



    # -------------------------------
    # おあしすっち：更新
    # -------------------------------
    async def update_oasistchi_pet(self, pet_id: int, **fields):
        await self._ensure_pool()
        async with self._lock:

            cols = []
            vals = []
            idx = 1

            for k, v in fields.items():
                cols.append(f"{k} = ${idx}")
                vals.append(v)
                idx += 1

            sql = f"""
                UPDATE oasistchi_pets
                SET {', '.join(cols)}
                WHERE id = ${idx}
            """
            vals.append(pet_id)

            await self._execute(sql, *vals)

    # ----------------------------------------
    # おあしすっち：全ペット取得（poop_check用）
    # ----------------------------------------
    async def get_all_oasistchi_pets(self):
        await self._ensure_pool()
        return await self._fetch(
            "SELECT * FROM oasistchi_pets"
        )

    async def get_oasistchi_pet(self, pet_id: int):
        await self._ensure_pool()
        async with self._lock:
            return await self._fetchrow(
                "SELECT * FROM oasistchi_pets WHERE id=$1",
                pet_id
            )

    # -------------------------------
    # おあしすっち：図鑑（取得）
    # -------------------------------
    async def get_oasistchi_owned_adult_keys(self, user_id: str) -> set[str]:
        await self._ensure_pool()
        async with self._lock:
            rows = await self._fetch(
                "SELECT adult_key FROM oasistchi_dex WHERE user_id=$1",
                user_id
            )
            return {r["adult_key"] for r in rows}

    # -------------------------------
    # おあしすっち：図鑑（追加）
    # -------------------------------
    async def add_oasistchi_dex(self, user_id: str, adult_key: str):
        await self._ensure_pool()
        async with self._lock:
            await self._execute(
                """
                INSERT INTO oasistchi_dex (user_id, adult_key)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                user_id, adult_key
            )

    # -------------------------------
    # おあしすっち：通知設定（取得）
    # -------------------------------
    async def get_oasistchi_notify_all(self, user_id: str) -> bool:
        await self._ensure_pool()
        row = await self._fetchrow("SELECT 1 FROM oasistchi_notify WHERE user_id=$1", user_id)
        return row is not None

    # -------------------------------
    # おあしすっち：通知設定（更新）
    # -------------------------------
    async def set_oasistchi_notify_all(self, user_id: str, on: bool):
        await self._ensure_pool()

        if on:
            await self._execute("""
                INSERT INTO oasistchi_notify (user_id, notify_poop, notify_food, notify_pet_ready)
                VALUES ($1, TRUE, TRUE, TRUE)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    notify_poop=TRUE,
                    notify_food=TRUE,
                    notify_pet_ready=TRUE
            """, user_id)
        else:
            # 設定してない状態＝通知なし
            await self._execute("DELETE FROM oasistchi_notify WHERE user_id=$1", user_id)

    async def delete_oasistchi_pet(self, pet_id: int):
        await self._ensure_pool()
        async with self._lock:
            await self._execute(
                "DELETE FROM oasistchi_pets WHERE id=$1",
                pet_id
            )
    async def get_race_schedules(self, guild_id: str):
        return await self._fetch(
            """
            SELECT *
            FROM race_schedules
            WHERE guild_id = $1
            ORDER BY race_time
            """,
            str(guild_id)
        )


    async def get_race_entries_by_schedule(self, race_date, schedule_id, guild_id: str):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT * FROM race_entries
            WHERE race_date = $1
              AND schedule_id = $2
              AND guild_id = $3
            ORDER BY created_at
        """, race_date, schedule_id, str(guild_id))

    async def get_race_results(self, race_date, schedule_id):
        return await self._fetch(
            """
            SELECT * FROM race_results
            WHERE race_date = $1 AND schedule_id = $2
            ORDER BY rank
            """,
            race_date, schedule_id
        )

    async def mark_pet_race_candidate(self, pet_id: int, user_id: int):
      await self._execute(
            """
            UPDATE oasistchi_pets
            SET race_candidate = TRUE
            WHERE id = $1 AND user_id = $2
            """,
            pet_id,
            user_id
        )


    async def get_oasistchi_notify_settings(self, user_id: str) -> dict | None:
        await self._ensure_pool()
        row = await self._fetchrow(
            "SELECT notify_poop, notify_food, notify_pet_ready FROM oasistchi_notify WHERE user_id=$1",
            user_id
        )
        return dict(row) if row else None

    async def get_today_race_schedules(self, race_date: date, guild_id: str):
        return await self._fetch("""
            SELECT *
            FROM race_schedules
            WHERE race_date = $1
              AND guild_id = $2
            ORDER BY race_time
        """, race_date, guild_id)

    async def generate_today_races(self, guild_id: str, race_date: date):
        cols = await self._fetch("""
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'race_schedules'
            ORDER BY ordinal_position;
        """)
        print("[RACE DEBUG] race_schedules columns:")
        for c in cols:
            print(f"  {c['column_name']} | nullable={c['is_nullable']}")
        # 念のため同日分を削除（再生成耐性）
        await self._execute("""
            DELETE FROM race_schedules
            WHERE race_date = $1
              AND guild_id = $2;
        """, race_date, str(guild_id))

        for i, race_time in enumerate(RACE_TIMES, start=1):
            await self._execute("""
                INSERT INTO race_schedules (
                    guild_id,
                    race_no,
                    race_time,
                    entry_open_minutes,
                    max_entries,
                    entry_fee,
                    created_at,
                    race_date,
                    distance,
                    surface,
                    condition
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7, $8, $9, $10);
            """,
            str(guild_id),          # ← ★ これが必須
            i,                      # race_no
            race_time,
            ENTRY_OPEN_MINUTES,
            8,
            50000,
            race_date,
            random.choice(DISTANCES),
            random.choice(SURFACES),
            random.choice(CONDITIONS),
            )

    async def has_today_race_schedules(self, race_date: date, guild_id: str) -> bool:
        return await self._fetchval("""
            SELECT EXISTS(
                SELECT 1
                FROM race_schedules
                WHERE race_date = $1
                  AND guild_id = $2
            )
        """, race_date, guild_id)

    # -----------------------------------------
    # race_schedules テーブル カラム補完
    # -----------------------------------------
    async def ensure_race_schedule_columns(self):
        cols = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_schedules';
        """)
        existing = {c["column_name"] for c in cols}

        alter_sqls = []

        if "guild_id" not in existing:
            alter_sqls.append("ADD COLUMN guild_id TEXT")

        if "race_date" not in existing:
            alter_sqls.append("ADD COLUMN race_date DATE")

        if "distance" not in existing:
            alter_sqls.append("ADD COLUMN distance TEXT")

        if "surface" not in existing:
            alter_sqls.append("ADD COLUMN surface TEXT")

        if "condition" not in existing:
            alter_sqls.append("ADD COLUMN condition TEXT")

        if "race_finished" not in existing:
            alter_sqls.append("ADD COLUMN race_finished BOOLEAN DEFAULT FALSE")

        if "result_sent" not in existing:
            alter_sqls.append("ADD COLUMN result_sent BOOLEAN DEFAULT FALSE")

        if alter_sqls:
            sql = "ALTER TABLE race_schedules " + ", ".join(alter_sqls) + ";"
            print("🛠 race_schedules カラム補完:", sql)
            await self._execute(sql)

    # -----------------------------------------
    # race_entries テーブル カラム補完
    # -----------------------------------------
    async def ensure_race_entry_columns(self):
        cols = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_entries';
        """)
        existing = {c["column_name"] for c in cols}

        alter_sqls = []

        if "guild_id" not in existing:
            alter_sqls.append("ADD COLUMN guild_id TEXT")

        if "entry_fee" not in existing:
            alter_sqls.append("ADD COLUMN entry_fee INTEGER DEFAULT 50000")

        if alter_sqls:
            sql = "ALTER TABLE race_entries " + ", ".join(alter_sqls) + ";"
            print("🛠 race_entries カラム補完:", sql)
            await self._execute(sql)

    # -----------------------------------------
    # race_results テーブル カラム補完（救済版）
    # -----------------------------------------
    async def ensure_race_results_columns(self):
        cols = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'race_results';
        """)
        existing = {c["column_name"] for c in cols}

        # まず不足カラムを追加
        if "guild_id" not in existing:
            print("🛠 race_results に guild_id を追加します…")
            await self._execute("ALTER TABLE race_results ADD COLUMN guild_id TEXT;")

        if "race_date" not in existing:
            print("🛠 race_results に race_date を追加します…")
            await self._execute("ALTER TABLE race_results ADD COLUMN race_date DATE;")

        if "schedule_id" not in existing:
            print("🛠 race_results に schedule_id を追加します…")
            await self._execute("ALTER TABLE race_results ADD COLUMN schedule_id INTEGER;")

        if "pet_id" not in existing:
            print("🛠 race_results に pet_id を追加します…")
            await self._execute("ALTER TABLE race_results ADD COLUMN pet_id INTEGER;")

        if "rank" not in existing:
            print("🛠 race_results に rank を追加します…")
            await self._execute("ALTER TABLE race_results ADD COLUMN rank INTEGER;")

        if "final_score" not in existing:
            print("🛠 race_results に final_score を追加します…")
            await self._execute("ALTER TABLE race_results ADD COLUMN final_score DOUBLE PRECISION;")

        if "user_id" not in existing:
            print("🛠 race_results に user_id を追加します…")
            await self._execute(
                "ALTER TABLE race_results ADD COLUMN user_id TEXT;"
            )

        if "position" not in existing:
            print("🛠 race_results に position を追加します…")
            await self._execute(
                "ALTER TABLE race_results ADD COLUMN position INTEGER;"
            )

        if "reward" not in existing:
            print("🛠 race_results に reward を追加します…")
            await self._execute(
                "ALTER TABLE race_results ADD COLUMN reward INTEGER DEFAULT 0;"
            )

        # guild_id の既存データ補完（あっても害なし）
        try:
            await self._execute("""
                UPDATE race_results rr
                SET guild_id = rs.guild_id
                FROM race_schedules rs
                WHERE rr.schedule_id = rs.id
                  AND rr.race_date   = rs.race_date
                  AND (rr.guild_id IS NULL OR rr.guild_id = '');
            """)
        except Exception as e:
            print(f"[RACE MIGRATE WARNING] {e!r}")

        print("✅ race_results カラム補完完了")

            
    # -----------------------------------------
    # 型修正用の補完
    # -----------------------------------------
    async def ensure_race_schedule_time_text(self):
        col = await self._fetchrow("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'race_schedules'
              AND column_name = 'race_time';
        """)

        if col and col["data_type"] != "text":
            print("🛠 race_schedules.race_time を TEXT に変更します")
            await self._execute("""
                ALTER TABLE race_schedules
                ALTER COLUMN race_time TYPE TEXT
                USING race_time::text;
            """)
    # -----------------------------------------
    # レース関係関数
    # -----------------------------------------
    async def get_race_entries_pending(self, guild_id: str, race_date, schedule_id: int):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT *
            FROM race_entries
            WHERE guild_id = $1
              AND race_date = $2
              AND schedule_id = $3
              AND status = 'pending'
            ORDER BY created_at
        """, str(guild_id), race_date, schedule_id)
    # -----------------------------------------
    # 参加済みを取得
    # -----------------------------------------

    async def get_today_selected_pet_ids(self, race_date: date):
        rows = await self._fetch("""
            SELECT pet_id FROM race_entries
            WHERE race_date = $1
              AND status = 'selected'
        """, race_date)
        return {r["pet_id"] for r in rows}

    # -----------------------------------------
    # ステータス更新
    # -----------------------------------------

    async def update_race_entry_status(self, entry_id: int, status: str):
        await self._execute("""
            UPDATE race_entries
            SET status = $2
            WHERE id = $1
        """, entry_id, status)

    # -----------------------------------------
    # 返金
    # -----------------------------------------
    async def refund_entry(self, user_id: str, guild_id: str, amount: int):
        await self.add_balance(user_id, guild_id, amount)
    # -----------------------------------------
    # 同日・他レースエントリー無効化
    # -----------------------------------------

    async def cancel_other_entries(
        self,
        pet_id: int,
        race_date: date,
        exclude_schedule_id: int
    ):
        await self._execute("""
            UPDATE race_entries
            SET status = 'cancelled'
            WHERE pet_id = $1
              AND race_date = $2
              AND schedule_id != $3
              AND status = 'pending'
        """, pet_id, race_date, exclude_schedule_id)


    # =====================================================
    # レース：同一ユーザーの重複エントリーチェック
    # =====================================================
    async def has_user_entry_for_race(self, schedule_id: int, user_id: str) -> bool:
        row = await self._fetchrow("""
            SELECT 1
            FROM race_entries
            WHERE schedule_id = $1
              AND user_id = $2
            LIMIT 1;
        """, schedule_id, user_id)

        return row is not None


    # db.py に追加（has_user_entry_for_race の近くに置くのがわかりやすい）
    async def has_pet_entry_for_race(self, schedule_id: int, pet_id: int) -> bool:
        row = await self._fetchrow("""
            SELECT 1
            FROM race_entries
            WHERE schedule_id = $1
              AND pet_id = $2
              AND status IN ('pending', 'selected')   -- cancelled は無視
            LIMIT 1;
        """, schedule_id, pet_id)
        return row is not None




    # =====================================================
    # おあしすっち出走済みかチェック
    # =====================================================
    async def has_pet_selected_today(self, pet_id: int, race_date: date) -> bool:
        row = await self._fetchrow("""
            SELECT 1
            FROM race_entries
            WHERE pet_id = $1
              AND race_date = $2
              AND status = 'selected'
            LIMIT 1;
        """, pet_id, race_date)
        return row is not None
        
    # =====================================================
    # 同一ユーザーが同日出走したかチェック
    # =====================================================

    async def has_user_selected_today(self, user_id: str, race_date: date) -> bool:
        row = await self._fetchrow("""
            SELECT 1
            FROM race_entries
            WHERE user_id = $1
              AND race_date = $2
              AND status = 'selected'
            LIMIT 1;
        """, user_id, race_date)
        return row is not None

    # =====================================================
    # エントリー追加（確定時）
    # =====================================================

    async def insert_race_entry(
        self,
        schedule_id: int,
        guild_id: str,
        user_id: str,
        pet_id: int,
        race_date,          # date 型
        entry_fee: int,
        paid: bool,
    ):
        await self._execute("""
            INSERT INTO race_entries (
                race_date,
                schedule_id,
                guild_id,
                user_id,
                pet_id,
                entry_fee,
                paid,
                status,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', NOW());
        """,
        race_date,
        schedule_id,
        guild_id,
        user_id,
        pet_id,
        entry_fee,
        paid
        )
    # =====================================================
    # 返金対象をまとめて取得
    # =====================================================

    async def get_refund_entries(self, schedule_id: int):
        return await self._fetch("""
            SELECT user_id, guild_id, entry_fee
            FROM race_entries
            WHERE schedule_id = $1
              AND status = 'cancelled'
        """, schedule_id)



    # =====================================================
    # 抽選済みフラグ
    # =====================================================
    async def mark_race_lottery_done(self, race_id: int):
        await self._execute("""
            UPDATE race_schedules
            SET lottery_done = TRUE,
                locked = TRUE
            WHERE id = $1
        """, race_id)


    # =====================================================
    # かぶりなしたまご
    # =====================================================

    async def _ensure_column(self, table: str, column: str, coldef: str):
        rows = await self._fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = $1;
        """, table)

        existing = {r["column_name"] for r in rows}
        if column not in existing:
            print(f"🛠 {table} テーブルに {column} カラムを追加します…")
            await self._execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef};")
            print(f"✅ {column} カラム追加完了")


    # -------------------------------
    # おあしすっち：転生
    # -------------------------------
    async def rebirth_oasistchi(self, pet_id: int):
        base_speed = random.randint(30, 50)
        base_stamina = random.randint(30, 50)
        base_power = random.randint(30, 50)

        await self._execute("""
            UPDATE oasistchi_pets
            SET
                base_speed = $1,
                base_stamina = $2,
                base_power = $3,
                train_speed = 0,
                train_stamina = 0,
                train_power = 0,
                training_count = 0
            WHERE id = $4
              AND stage = 'adult'
        """,
        base_speed,
        base_stamina,
        base_power,
        pet_id)

    # -------------------------------
    # おあしすっち：特訓リセット
    # -------------------------------
    async def reset_training_oasistchi(self, pet_id: int):
        await self._execute("""
            UPDATE oasistchi_pets
            SET
                train_speed = 0,
                train_stamina = 0,
                train_power = 0,
                training_count = 0
            WHERE id = $1
              AND stage = 'adult'
        """, pet_id)


    # --------------------------------------------------
    # 出走確定エントリー取得
    # --------------------------------------------------
    async def get_selected_entries(self, guild_id: str, race_date: date, schedule_id: int):
        return await self._fetch("""
            SELECT *
            FROM race_entries
            WHERE guild_id = $1
              AND race_date = $2
              AND schedule_id = $3
              AND status = 'selected'
        """, guild_id, race_date, schedule_id)

    # --------------------------------------------------
    # レース結果保存
    # --------------------------------------------------
    async def update_race_entry_result(
        self,
        schedule_id: int,
        pet_id: int,
        rank: int,
        score: float
    ):
        await self._execute("""
            UPDATE race_entries
            SET rank = $1,
                score = $2
            WHERE schedule_id = $3
              AND pet_id = $4
        """, rank, score, schedule_id, pet_id)

    # --------------------------------------------------
    # レース完了
    # --------------------------------------------------
    async def mark_race_finished(self, race_id: int):
        await self._ensure_pool()
        await self._execute("""
            UPDATE race_schedules
            SET race_finished = TRUE
            WHERE id = $1
        """, race_id)

    # --------------------------------------------------
    # 未完了レース取得（日付）
    # --------------------------------------------------
    async def get_unfinished_races_by_date(self, race_date: date, guild_id: str):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT *
            FROM race_schedules
            WHERE race_date = $1
              AND guild_id = $2
              AND race_finished = FALSE
            ORDER BY race_time
        """, race_date, str(guild_id))

    # --------------------------------------------------
    # 未完了レース存在チェック
    # --------------------------------------------------
    async def has_unfinished_race(self, race_id: int) -> bool:
        await self._ensure_pool()
        row = await self._fetchrow("""
            SELECT 1
            FROM race_schedules
            WHERE id = $1
              AND race_finished = FALSE
        """, race_id)
        return row is not None

    async def get_race_entries_by_status(self, race_id: int, status: str):
        await self._ensure_pool()
        return await self._fetch("""
            SELECT *
            FROM race_entries
            WHERE schedule_id = $1
              AND status = $2
        """, race_id, status)


    # ======================================================
    #   レースWeb機能（おあしすっち）※衝突回避版
    # ======================================================
    async def init_race_tables(self):
        await self._ensure_pool()

        # ★ race_schedules / race_entries（抽選用）と衝突するので別名にする
        await self._execute("""
            CREATE TABLE IF NOT EXISTS web_races (
                race_id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                race_time TIMESTAMP NOT NULL,
                status TEXT NOT NULL,
                result_channel_id TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await self._execute("""
            CREATE TABLE IF NOT EXISTS web_race_entries (
                race_id TEXT NOT NULL,
                pet_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                pet_key TEXT NOT NULL,
                condition TEXT NOT NULL,
                speed INTEGER NOT NULL,
                power INTEGER NOT NULL,
                stamina INTEGER NOT NULL,
                odds REAL NOT NULL,
                PRIMARY KEY (race_id, pet_id)
            );
        """)

        await self._execute("""
            CREATE TABLE IF NOT EXISTS web_race_bets (
                race_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                pet_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
    # --------------------------------------------------
    # API用：出走馬（selected）を oasistchi_pets とJOINして返す
    # speed/power/stamina は「base + train」を優先して0を回避
    # --------------------------------------------------
    async def get_selected_pets_for_api(self, guild_id: str, race_date: date, schedule_id: int):
        await self._ensure_pool()

        rows = await self._fetch("""
            SELECT
                e.pet_id,
                p.name,
                p.adult_key,

                -- まず speed/stamina/power が入っていればそれを使う
                -- 0なら base + train を採用（実運用で0が返ってくるのを潰す）
                CASE
                    WHEN COALESCE(p.speed, 0) > 0 THEN p.speed
                    ELSE COALESCE(p.base_speed, 0) + COALESCE(p.train_speed, 0)
                END AS speed,

                CASE
                    WHEN COALESCE(p.power, 0) > 0 THEN p.power
                    ELSE COALESCE(p.base_power, 0) + COALESCE(p.train_power, 0)
                END AS power,

                CASE
                    WHEN COALESCE(p.stamina, 0) > 0 THEN p.stamina
                    ELSE COALESCE(p.base_stamina, 0) + COALESCE(p.train_stamina, 0)
                END AS stamina

            FROM race_entries e
            JOIN oasistchi_pets p
              ON p.id = e.pet_id
            WHERE e.guild_id   = $1
              AND e.race_date  = $2
              AND e.schedule_id = $3
              AND e.status = 'selected'
            ORDER BY e.created_at ASC
        """, str(guild_id), race_date, schedule_id)

        # dict化
        return [
            {
                "pet_id": int(r["pet_id"]),
                "name": r["name"] or "NoName",
                "adult_key": r["adult_key"] or "unknown",
                "speed": int(r["speed"] or 0),
                "power": int(r["power"] or 0),
                "stamina": int(r["stamina"] or 0),
            }
            for r in rows
        ]
    
    # ======================================================
    #   レース機能（おあしすっち）
    # ======================================================
    async def run_race_lottery(
        self,
        guild_id: str,
        race_date: date,
        schedule_id: int
    ):
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # 二重実行防止
                race = await conn.fetchrow("""
                    SELECT lottery_done
                    FROM race_schedules
                    WHERE id = $1
                    FOR UPDATE
                """, schedule_id)

                if not race or race["lottery_done"]:
                    return {"selected": [], "cancelled": []}

                # pending取得（同じconn）
                entries = await conn.fetch("""
                    SELECT *
                    FROM race_entries
                    WHERE guild_id = $1
                      AND race_date = $2
                      AND schedule_id = $3
                      AND status = 'pending'
                    ORDER BY created_at
                """, str(guild_id), race_date, schedule_id)


                if len(entries) < 2:
                    return {"selected": [], "cancelled": []}

                # =========================
                # 同ユーザー1頭制限
                # =========================

                user_map = {}

                for e in entries:
                    uid = e["user_id"]

                    if uid not in user_map:
                        user_map[uid] = []

                    user_map[uid].append(e)

                filtered = []

                for uid, pets in user_map.items():
                    filtered.append(random.choice(pets))  # ユーザー内ランダム

                # =========================
                # 抽選
                # =========================

                max_entries = min(8, len(filtered))
                selected = random.sample(filtered, max_entries)

                selected_ids = {e["id"] for e in selected}
                cancelled = []





                max_entries = min(8, len(entries))
                selected = random.sample(entries, max_entries)
                selected_ids = {e["id"] for e in selected}
                cancelled = []

                for e in entries:
                    if e["id"] in selected_ids:
                        await conn.execute("""
                            UPDATE race_entries
                            SET status = 'selected'
                            WHERE id = $1
                        """, e["id"])
                    else:
                        await conn.execute("""
                            UPDATE race_entries
                            SET status = 'cancelled'
                            WHERE id = $1
                        """, e["id"])
                        cancelled.append(e)

                await conn.execute("""
                    UPDATE race_schedules
                    SET lottery_done = TRUE,
                        locked = TRUE
                    WHERE id = $1
                """, schedule_id)

                return {
                    "selected": selected,
                    "cancelled": cancelled
                }

    # =========================
    # レース設定取得
    # =========================
    async def get_race_settings(self, guild_id: str):
        await self._ensure_pool()
        return await self._fetchrow(
            "SELECT * FROM race_settings WHERE guild_id=$1",
            str(guild_id)
        )

    # =========================
    # レース結果チャンネル設定
    # =========================
    async def set_race_result_channel(self, guild_id: str, channel_id: str):
        await self._ensure_pool()
        await self._execute("""
            INSERT INTO race_settings (guild_id, result_channel_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET result_channel_id=$2
        """, str(guild_id), str(channel_id))



    async def _fetch(self, query, *args, conn=None):
        await self._ensure_pool()
        if conn:
            return await conn.fetch(query, *args)
        async with self.pool.acquire() as c:
            return await c.fetch(query, *args)

    async def _fetchrow(self, query, *args, conn=None):
        await self._ensure_pool()
        if conn:
            return await conn.fetchrow(query, *args)
        async with self.pool.acquire() as c:
            return await c.fetchrow(query, *args)

    async def _fetchval(self, query, *args, conn=None):
        await self._ensure_pool()
        if conn:
            return await conn.fetchval(query, *args)
        async with self.pool.acquire() as c:
            return await c.fetchval(query, *args)

    async def _execute(self, query, *args, conn=None):
        await self._ensure_pool()
        if conn:
            return await conn.execute(query, *args)
        async with self.pool.acquire() as c:
            return await c.execute(query, *args)


    async def get_latest_open_race(self, guild_id):
        return await self._fetchrow("""
            SELECT *
            FROM race_schedules
            WHERE guild_id = $1
              AND lottery_done = TRUE
            ORDER BY race_date DESC, race_no DESC
            LIMIT 1
        """, guild_id)

    async def place_bet(self, guild_id, race_date, schedule_id, user_id, pet_id, amount):
        async with self._lock:

            # ① 馬券保存
            await self._execute("""
                INSERT INTO race_bets
                (guild_id, race_date, schedule_id, user_id, pet_id, amount)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, guild_id, race_date, schedule_id, user_id, pet_id, amount)

            # ② 全体プール更新
            await self._execute("""
                INSERT INTO race_pools
                (guild_id, race_date, schedule_id, total_pool)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, race_date, schedule_id)
                DO UPDATE SET total_pool = race_pools.total_pool + $4
            """, guild_id, race_date, schedule_id, amount)

            # ③ ペット別プール更新
            await self._execute("""
                INSERT INTO race_pet_pools
                (guild_id, race_date, schedule_id, pet_id, total_amount)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, race_date, schedule_id, pet_id)
                DO UPDATE SET total_amount = race_pet_pools.total_amount + $5
            """, guild_id, race_date, schedule_id, pet_id, amount)

    async def get_race_pool(self, guild_id, race_date, schedule_id):
        row = await self._fetchrow("""
            SELECT total_pool
            FROM race_pools
            WHERE guild_id = $1
              AND race_date = $2
              AND schedule_id = $3
        """, guild_id, race_date, schedule_id)

        return row["total_pool"] if row else 0

    async def get_pool_data(self, guild_id, race_date, schedule_id):
        total_row = await self._fetchrow("""
            SELECT total_pool
            FROM race_pools
            WHERE guild_id = $1
              AND race_date = $2
              AND schedule_id = $3
        """, guild_id, race_date, schedule_id)

        total_pool = total_row["total_pool"] if total_row else 0

        pet_rows = await self._fetch("""
            SELECT pet_id, total_amount
            FROM race_pet_pools
            WHERE guild_id = $1
              AND race_date = $2
              AND schedule_id = $3
        """, guild_id, race_date, schedule_id)

        pet_pools = {r["pet_id"]: r["total_amount"] for r in pet_rows}

        return total_pool, pet_pools

    async def finalize_race(self, guild_id, race_date, schedule_id, distance):

        guild_id = str(guild_id)
        schedule_id = int(schedule_id)

        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # =========================
                # 🔒 二重実行防止（reward_paidで制御）
                # =========================
                race = await conn.fetchrow("""
                    SELECT race_finished,
                           reward_paid,
                           distance,
                           surface,
                           condition
                    FROM race_schedules
                    WHERE id = $1
                    FOR UPDATE
                """, schedule_id)

                if not race or race["reward_paid"]:
                    return []

                # =========================
                # 🐎 出走確定馬取得
                # =========================
                raw_entries = await conn.fetch("""
                    SELECT *
                    FROM race_entries
                    WHERE guild_id = $1
                      AND race_date = $2
                      AND schedule_id = $3
                      AND status = 'selected'
                """, guild_id, race_date, schedule_id)

                if not raw_entries:
                    return []

                entries = []

                for e in raw_entries:

                    pet = await conn.fetchrow("""
                        SELECT
                            passive_skill,
                            adult_key,
                            base_speed,
                            train_speed,
                            base_power,
                            train_power,
                            base_stamina,
                            train_stamina
                        FROM oasistchi_pets
                        WHERE id = $1
                    """, e["pet_id"])


                    entries.append({
                        "user_id": e["user_id"],
                        "pet_id": e["pet_id"],
                        "passive_skill": pet["passive_skill"] if pet else None,
                        "adult_key": pet["adult_key"] if pet else None,
                        "speed": ((pet["base_speed"] or 0) + (pet["train_speed"] or 0)) if pet else 0,
                        "power": ((pet["base_power"] or 0) + (pet["train_power"] or 0)) if pet else 0,
                        "stamina": ((pet["base_stamina"] or 0) + (pet["train_stamina"] or 0)) if pet else 0,
                        "gate": e.get("gate")
                    })

                # simulate
                results = self.simulate_race(entries, race)

                # =========================
                # 🏆 結果保存 + 賞金処理
                # =========================
                for r in results:

                    rank = int(r["rank"])
                    score = int(r["score"])
                    pet_id = int(r["pet_id"])
                    schedule_id_int = schedule_id

                    # 報酬計算
                    if rank == 1:
                        reward = 50000
                    elif rank == 2:
                        reward = 30000
                    elif rank == 3:
                        reward = 10000
                    else:
                        reward = 0

                    # race_results 保存
                    await conn.execute("""
                        INSERT INTO race_results
                        (guild_id, race_date, schedule_id, pet_id, user_id, position, rank, final_score, reward)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        ON CONFLICT (race_date, schedule_id, pet_id)
                        DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            position = EXCLUDED.position,
                            rank = EXCLUDED.rank,
                            final_score = EXCLUDED.final_score,
                            reward = EXCLUDED.reward
                    """,
                        guild_id,
                        race_date,
                        schedule_id_int,
                        pet_id,
                        str(r["user_id"]),
                        rank,
                        rank,
                        score,
                        reward
                    )

                    # race_entries 更新
                    await conn.execute("""
                        UPDATE race_entries
                        SET rank = $1,
                            score = $2
                        WHERE schedule_id = $3
                          AND pet_id = $4
                    """,
                        rank,
                        score,
                        schedule_id_int,
                        pet_id
                    )

                    # 💰 オーナー賞金
                    if reward > 0:
                        await conn.execute("""
                            INSERT INTO users (user_id, guild_id, balance)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (user_id, guild_id)
                            DO UPDATE SET balance = users.balance + $3
                        """,
                            str(r["user_id"]),
                            guild_id,
                            reward
                        )
                        print(f"[OWNER PRIZE] rank={rank} user={r['user_id']} prize={reward}")

                # =========================
                # 🔐 賞金支払い完了フラグ
                # =========================
                await conn.execute("""
                    UPDATE race_schedules
                    SET reward_paid = TRUE
                    WHERE id = $1
                """, schedule_id)

                return results

    async def get_latest_active_race(self, guild_id: str):
        """
        open / locked / racing のいずれかの
        最新レースを取得する（観戦用）
        """
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT *
                FROM race_schedules
                WHERE guild_id = $1
                  AND phase IN ('open', 'locked', 'racing')
                ORDER BY race_date DESC, race_no DESC
                LIMIT 1
            """, guild_id)


    async def get_hotel_sub_role(self, guild_id: str):
        await self._ensure_pool()
        row = await self._fetchrow(
            "SELECT sub_role FROM hotel_settings WHERE guild_id=$1",
            str(guild_id)
        )
        return row["sub_role"] if row else None

    # ======================================================
    # 3連単プール表示3.1
    # ======================================================

    async def get_trifecta_pool(self, guild_id, race_date, schedule_id):
        guild_id = str(guild_id)
        race_date = str(race_date)
        schedule_id = int(schedule_id)

        row = await self._fetchrow("""
            SELECT total_pool, carry_in
            FROM race_trifecta_pools
            WHERE guild_id=$1 AND race_date=$2 AND schedule_id=$3
        """, guild_id, race_date, schedule_id)

        # =========================================
        # 🔥 レコードが存在しない場合は自動生成
        # =========================================
        if not row:

            BASE_POOL = 200000

            await self._execute("""
                INSERT INTO race_trifecta_pools
                (guild_id, race_date, schedule_id, total_pool, carry_in)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT DO NOTHING
            """, guild_id, race_date, schedule_id, BASE_POOL, 0)

            return {
                "total_pool": BASE_POOL,
                "carry_in": 0,
                "current_sales": 0
            }

        total = row["total_pool"]
        carry = row["carry_in"]

        # =========================================
        # 🔥 total/carryが両方0なら初期保証注入
        # =========================================
        if total == 0 and carry == 0:

            BASE_POOL = 200000

            await self._execute("""
                UPDATE race_trifecta_pools
                SET total_pool = $4
                WHERE guild_id=$1
                  AND race_date=$2
                  AND schedule_id=$3
                  AND total_pool = 0
                  AND carry_in = 0
            """, guild_id, race_date, schedule_id, BASE_POOL)

            total = BASE_POOL

        return {
            "total_pool": total,
            "carry_in": carry,
            "current_sales": total - carry
        }

    # ======================================================
    # 3連単オッズ取得（Web表示用）
    # ======================================================
    async def get_trifecta_odds(
        self,
        guild_id,
        race_date,
        schedule_id,
        first_pet_id,
        second_pet_id,
        third_pet_id
    ):
        guild_id = str(guild_id)
        race_date = str(race_date)

        # 総プール取得
        pool_row = await self._fetchrow("""
            SELECT total_pool
            FROM race_trifecta_pools
            WHERE guild_id=$1
              AND race_date=$2
              AND schedule_id=$3
        """, guild_id, race_date, schedule_id)

        total_pool = pool_row["total_pool"] if pool_row else 0

        # 該当組み合わせプール取得
        combo_row = await self._fetchrow("""
            SELECT total_amount
            FROM race_trifecta_combo_pools
            WHERE guild_id=$1
              AND race_date=$2
              AND schedule_id=$3
              AND first_pet_id=$4
              AND second_pet_id=$5
              AND third_pet_id=$6
        """,
            guild_id,
            race_date,
            schedule_id,
            first_pet_id,
            second_pet_id,
            third_pet_id
        )

        combo_amount = combo_row["total_amount"] if combo_row else 0

        if combo_amount == 0 or total_pool == 0:
            return 0

        odds = total_pool / combo_amount
        return round(odds, 2)

    # ======================================================
    # 3連単：ユーザー購入口数取得
    # ======================================================
    async def get_user_trifecta_units(
        self,
        guild_id,
        race_date,
        schedule_id,
        user_id,
        first_pet_id,
        second_pet_id,
        third_pet_id
    ):
        guild_id = str(guild_id)
        user_id = str(user_id)
        race_date = str(race_date)

        row = await self._fetchrow("""
            SELECT COALESCE(SUM(amount),0) AS total
            FROM race_trifecta_bets
            WHERE guild_id=$1
              AND race_date=$2
              AND schedule_id=$3
              AND user_id=$4
              AND first_pet_id=$5
              AND second_pet_id=$6
              AND third_pet_id=$7
        """,
            guild_id,
            race_date,
            schedule_id,
            user_id,
            first_pet_id,
            second_pet_id,
            third_pet_id
        )

        total_amount = row["total"] if row else 0

        # 1口10,000rrc
        units = total_amount // 10000

        return units

    # ======================================================
    # 3連単：購入処理3.1
    # ======================================================
    async def place_trifecta_bet(
        self,
        guild_id,
        race_date,
        schedule_id,
        user_id,
        first_pet_id,
        second_pet_id,
        third_pet_id,
        amount
    ):
        TRIFECTA_UNIT_PRICE = 10000
        TRIFECTA_MAX_UNITS = 10
        TRIFECTA_MAX_AMOUNT = TRIFECTA_UNIT_PRICE * TRIFECTA_MAX_UNITS  # 100,000

        guild_id = str(guild_id)
        user_id = str(user_id)
        schedule_id = int(schedule_id)
        amount = int(amount)
        race_date = str(race_date)

        # =========================
        # 0) 入力チェック（口数制限）
        # =========================
        if amount <= 0:
            raise RuntimeError("購入金額が不正です")

        if amount % TRIFECTA_UNIT_PRICE != 0:
            raise RuntimeError("3連単は1口10,000rrc単位です")

        if amount > TRIFECTA_MAX_AMOUNT:
            raise RuntimeError("3連単は最大10口（100,000rrc）までです")

        # 同じ馬を重複指定していないかチェック
        if len({first_pet_id, second_pet_id, third_pet_id}) != 3:
            raise RuntimeError("同じおあしすっちは指定できません")

        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # =========================
                # ① 残高ロック
                # =========================
                balance_row = await conn.fetchrow("""
                    SELECT balance
                    FROM users
                    WHERE user_id=$1 AND guild_id=$2
                    FOR UPDATE
                """, user_id, guild_id)

                if not balance_row:
                    raise RuntimeError("ユーザー未登録")

                if balance_row["balance"] < amount:
                    raise RuntimeError("残高不足")

                # =========================
                # ★ 1.5) 3連単の購入上限チェック（このレース合計）
                # =========================
                user_total = await conn.fetchval("""
                    SELECT COALESCE(SUM(amount), 0)
                    FROM race_trifecta_bets
                    WHERE guild_id=$1
                      AND race_date=$2
                      AND schedule_id=$3
                      AND user_id=$4
                """, guild_id, race_date, schedule_id, user_id)

                new_total = int(user_total) + amount
                if new_total > TRIFECTA_MAX_AMOUNT:
                    remaining = (TRIFECTA_MAX_AMOUNT - int(user_total)) // TRIFECTA_UNIT_PRICE
                    raise RuntimeError(f"3連単はこのレースで最大10口までです（残り {remaining}口）")

                # =========================
                # ② 残高減算
                # =========================
                await conn.execute("""
                    UPDATE users
                    SET balance = balance - $1
                    WHERE user_id=$2 AND guild_id=$3
                """, amount, user_id, guild_id)

                # =========================
                # ③ ユーザー別ベット保存
                # =========================
                await conn.execute("""
                    INSERT INTO race_trifecta_bets
                    (guild_id, race_date, schedule_id, user_id,
                     first_pet_id, second_pet_id, third_pet_id, amount)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                    guild_id,
                    race_date,
                    schedule_id,
                    user_id,
                    first_pet_id,
                    second_pet_id,
                    third_pet_id,
                    amount
                )

                # =========================
                # ④ 総プール更新
                # =========================
                pool_row = await conn.fetchrow("""
                    SELECT total_pool, carry_in
                    FROM race_trifecta_pools
                    WHERE guild_id=$1
                      AND race_date=$2
                      AND schedule_id=$3
                    FOR UPDATE
                """, guild_id, race_date, schedule_id)

                # carry をロックして取得（※ 行が無い可能性あるので後で0扱い）
                carry = await conn.fetchval("""
                    SELECT carry_over
                    FROM race_trifecta_carry
                    WHERE guild_id=$1
                    FOR UPDATE
                """, guild_id)
                carry = int(carry or 0)

                if not pool_row:
                    # プール行が無い → carry + amount で新規作成
                    await conn.execute("""
                        INSERT INTO race_trifecta_pools
                        (guild_id, race_date, schedule_id, total_pool, carry_in)
                        VALUES ($1,$2,$3,$4,$5)
                    """,
                        guild_id,
                        race_date,
                        schedule_id,
                        carry + amount,
                        carry
                    )
                else:
                    # プール行がある → まず carry があれば注入（carry_inも加算）
                    if carry > 0:
                        await conn.execute("""
                            UPDATE race_trifecta_pools
                            SET total_pool = total_pool + $1,
                                carry_in  = carry_in  + $1
                            WHERE guild_id=$2
                              AND race_date=$3
                              AND schedule_id=$4
                        """, carry, guild_id, race_date, schedule_id)

                    # 次に今回購入分を加算
                    await conn.execute("""
                        UPDATE race_trifecta_pools
                        SET total_pool = total_pool + $1
                        WHERE guild_id=$2
                          AND race_date=$3
                          AND schedule_id=$4
                    """, amount, guild_id, race_date, schedule_id)

                # carry を使ったらゼロクリア
                if carry > 0:
                    await conn.execute("""
                        UPDATE race_trifecta_carry
                        SET carry_over = 0
                        WHERE guild_id=$1
                    """, guild_id)

                # =========================
                # ⑤ 組み合わせ別プール更新
                # =========================
                await conn.execute("""
                    INSERT INTO race_trifecta_combo_pools
                    (guild_id, race_date, schedule_id,
                     first_pet_id, second_pet_id, third_pet_id,
                     total_amount)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                    ON CONFLICT (
                        guild_id,
                        race_date,
                        schedule_id,
                        first_pet_id,
                        second_pet_id,
                        third_pet_id
                    )
                    DO UPDATE SET total_amount =
                        race_trifecta_combo_pools.total_amount + $7
                """,
                    guild_id,
                    race_date,
                    schedule_id,
                    first_pet_id,
                    second_pet_id,
                    third_pet_id,
                    amount
                )

                remaining_units = (TRIFECTA_MAX_AMOUNT - new_total) // TRIFECTA_UNIT_PRICE

                return {
                    "status": "ok",
                    "spent": amount,
                    "user_total": new_total,
                    "remaining_units": remaining_units,
                    "balance_after": balance_row["balance"] - amount
                }

    # ======================================================
    # 3連単：精算処理（キャリー対応）
    # ======================================================
    async def settle_trifecta(
        self,
        guild_id,
        race_date,
        schedule_id,
        next_schedule_id=None  # キャリー先（同日次レース）
    ):
        guild_id = str(guild_id)
        race_date = str(race_date)
        schedule_id = int(schedule_id)

        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            async with conn.transaction():

                # =========================
                # ① 1〜3着取得
                # =========================
                top3 = await conn.fetch("""
                    SELECT pet_id
                    FROM race_results
                    WHERE guild_id=$1
                      AND race_date=$2
                      AND schedule_id=$3
                      AND rank <= 3
                    ORDER BY rank ASC
                """, guild_id, race_date, schedule_id)

                if len(top3) < 3:
                    return {"status": "no_result"}

                first = top3[0]["pet_id"]
                second = top3[1]["pet_id"]
                third = top3[2]["pet_id"]

                # =========================
                # ② 総プール取得（ロック）
                # =========================
                pool_row = await conn.fetchrow("""
                    SELECT total_pool, carry_in
                    FROM race_trifecta_pools
                    WHERE guild_id=$1
                      AND race_date=$2
                      AND schedule_id=$3
                    FOR UPDATE
                """, guild_id, race_date, schedule_id)

                if not pool_row or pool_row["total_pool"] == 0:
                    return {"status": "no_pool"}

                total_pool = pool_row["total_pool"]

                # =========================
                # ③ 的中者取得
                # =========================
                winners = await conn.fetch("""
                    SELECT user_id, amount
                    FROM race_trifecta_bets
                    WHERE guild_id=$1
                      AND race_date=$2
                      AND schedule_id=$3
                      AND first_pet_id=$4
                      AND second_pet_id=$5
                      AND third_pet_id=$6
                """,
                    guild_id,
                    race_date,
                    schedule_id,
                    first,
                    second,
                    third
                )

                # =========================
                # ④ 的中者がいる場合
                # =========================
                if winners:

                    total_winning_amount = sum(w["amount"] for w in winners)

                    payouts = []

                    for w in winners:
                        share = total_pool * (w["amount"] / total_winning_amount)
                        share = int(share)

                        await conn.execute("""
                            UPDATE users
                            SET balance = balance + $1
                            WHERE user_id=$2 AND guild_id=$3
                        """, share, str(w["user_id"]), guild_id)

                        payouts.append({
                            "user_id": w["user_id"],
                            "payout": share
                        })

                    # =========================
                    # 🔥 レースプールリセット
                    # =========================
                    await conn.execute("""
                        UPDATE race_trifecta_pools
                        SET total_pool = 0,
                            carry_in = 0
                        WHERE guild_id=$1
                          AND race_date=$2
                          AND schedule_id=$3
                    """, guild_id, race_date, schedule_id)

                    return {
                        "status": "hit",
                        "payouts": payouts,
                        "total_pool": total_pool
                    }

                # =========================
                # ⑤ 的中ゼロ → キャリー
                # =========================
                else:

                    # 🔥 サーバーキャリーへ加算
                    await conn.execute("""
                        INSERT INTO race_trifecta_carry (guild_id, carry_over)
                        VALUES ($1, $2)
                        ON CONFLICT (guild_id)
                        DO UPDATE SET carry_over =
                            race_trifecta_carry.carry_over + $2
                    """, guild_id, total_pool)

                    # 今レースプールはリセット
                    await conn.execute("""
                        UPDATE race_trifecta_pools
                        SET total_pool = 0,
                            carry_in = 0
                        WHERE guild_id=$1
                          AND race_date=$2
                          AND schedule_id=$3
                    """, guild_id, race_date, schedule_id)

                    return {
                        "status": "carry",
                        "carry_amount": total_pool
                    }
    # ======================================================
    # キャリー関係
    # ======================================================
    async def get_trifecta_carry(self, guild_id: str) -> int:
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            value = await conn.fetchval("""
                SELECT carry_over
                FROM race_trifecta_carry
                WHERE guild_id=$1
            """, guild_id)

            return value or 0

    async def add_trifecta_carry(self, guild_id: str, amount: int):
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO race_trifecta_carry (guild_id, carry_over)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET carry_over =
                    race_trifecta_carry.carry_over + $2
            """, guild_id, amount)

    async def reset_trifecta_carry(self, guild_id: str):
        await self._ensure_pool()

        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE race_trifecta_carry
                SET carry_over = 0
                WHERE guild_id=$1
            """, guild_id)

    # ======================================================
    # バッジ付与
    # ======================================================
    async def add_user_badge(self, user_id: str, guild_id: str, badge: str):
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                INSERT INTO user_badges (guild_id, user_id, badge)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
            """, guild_id, user_id, badge)

            print("INSERT RESULT:", result)

            rows = await conn.fetch("SELECT * FROM user_badges;")
            print("TABLE NOW:", rows)

    # ======================================================
    # ユーザーのバッジ一覧取得
    # ======================================================
    async def get_user_badges(self, user_id: str) -> list[str]:
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT badge
                FROM user_badges
                WHERE user_id = $1
            """, user_id)

        print("ROWS:", rows)
        return [r["badge"] for r in rows]

    # ======================================================
    # バッジ削除
    # ======================================================
    async def remove_user_badge(self, user_id: str, guild_id: str, badge: str):
        await self._ensure_pool()
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM user_badges
                WHERE guild_id = $1
                  AND user_id = $2
                  AND badge = $3
            """, guild_id, user_id, badge)

    # ======================================================
    # 単勝：ユーザー購入口数取得
    # ======================================================
    async def get_user_single_units(
        self,
        guild_id,
        race_date,
        schedule_id,
        user_id,
        pet_id
    ):
        guild_id = str(guild_id)
        user_id = str(user_id)
        race_date = str(race_date)
        schedule_id = int(schedule_id)

        row = await self._fetchrow("""
            SELECT COALESCE(SUM(amount),0) AS total
            FROM race_bets
            WHERE guild_id=$1
              AND race_date=$2
              AND schedule_id=$3
              AND user_id=$4
              AND pet_id=$5
        """,
            guild_id,
            race_date,
            schedule_id,
            user_id,
            pet_id
        )

        total = row["total"] if row else 0
        units = total // 1000   # 単勝は1口1000rrc

        return units



