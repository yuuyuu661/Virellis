import asyncio
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

GUILD_ID = 1475448864122208350


# =========================================================
# 共通ヘルパー
# =========================================================
async def get_admin_role_ids(bot, guild_id: str) -> list[str]:
    row = await bot.db.get_settings(guild_id)
    if not row:
        return []
    return row["admin_roles"] or []


async def is_admin_user(bot, member: discord.Member, guild_id: str) -> bool:
    admin_roles = await get_admin_role_ids(bot, guild_id)
    return any(str(r.id) in admin_roles for r in member.roles)


async def is_hotel_manager(bot, member: discord.Member, guild_id: str) -> bool:
    cfg = await bot.db.get_hotel_settings(guild_id)
    if not cfg or not cfg["manager_role"]:
        return False
    return any(str(r.id) == str(cfg["manager_role"]) for r in member.roles)


async def can_manage_room(bot, member: discord.Member, guild_id: str, owner_id: str) -> bool:
    if str(member.id) == str(owner_id):
        return True
    if await is_admin_user(bot, member, guild_id):
        return True
    if await is_hotel_manager(bot, member, guild_id):
        return True
    return False


async def send_hotel_log(guild: discord.Guild, bot, guild_id: str, embed: discord.Embed):
    cfg = await bot.db.get_hotel_settings(guild_id)
    if not cfg or not cfg["log_channel"]:
        return

    ch = guild.get_channel(int(cfg["log_channel"]))
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception as e:
            print("[Hotel] log send error:", e)


def utcnow():
    return datetime.utcnow()


async def choose_category(guild: discord.Guild, category_ids: list[str]) -> Optional[discord.CategoryChannel]:
    candidates: list[tuple[int, discord.CategoryChannel]] = []

    for cid in category_ids or []:
        ch = guild.get_channel(int(cid))
        if isinstance(ch, discord.CategoryChannel):
            voice_count = sum(1 for c in ch.channels if isinstance(c, discord.VoiceChannel))
            candidates.append((voice_count, ch))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# =========================================================
# モーダル
# =========================================================
class LimitModal(discord.ui.Modal, title="人数制限変更"):
    limit = discord.ui.TextInput(
        label="人数",
        placeholder="0 = 無制限",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        guild_id = str(interaction.guild.id)

        room = await bot.db.get_room(str(interaction.channel.id))
        if not room:
            return await interaction.response.send_message("ホテルルームではありません", ephemeral=True)

        if not await can_manage_room(bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message("部屋の所有者または管理者のみ変更できます", ephemeral=True)

        try:
            limit = int(self.limit.value)
            if limit < 0 or limit > 99:
                raise ValueError
        except Exception:
            return await interaction.response.send_message("0〜99 の数字を入力してください", ephemeral=True)

        vc = interaction.guild.get_channel(int(room["vc_id"]))
        if not isinstance(vc, discord.VoiceChannel):
            return await interaction.response.send_message("VCが見つかりませんでした", ephemeral=True)

        await vc.edit(user_limit=limit)

        await interaction.response.send_message(
            f"👥 人数制限を **{limit}** に変更しました",
            ephemeral=True
        )


class RenameModal(discord.ui.Modal, title="部屋名変更"):
    name = discord.ui.TextInput(
        label="新しい部屋名",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        guild_id = str(interaction.guild.id)

        room = await bot.db.get_room(str(interaction.channel.id))
        if not room:
            return await interaction.response.send_message("ホテルルームではありません", ephemeral=True)

        if not await can_manage_room(bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message("部屋の所有者または管理者のみ変更できます", ephemeral=True)

        vc = interaction.guild.get_channel(int(room["vc_id"]))
        if not isinstance(vc, discord.VoiceChannel):
            return await interaction.response.send_message("VCが見つかりませんでした", ephemeral=True)

        await vc.edit(name=self.name.value)

        await interaction.response.send_message(
            f"✏️ 部屋名を **{self.name.value}** に変更しました",
            ephemeral=True
        )


# =========================================================
# ルーム操作ボタン
# =========================================================
class ExtendButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="24時間延長",
            style=discord.ButtonStyle.blurple,
            emoji="🎫",
            custom_id="hotel_extend"
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        room = await bot.db.get_room(str(interaction.channel.id))
        if not room:
            return await interaction.response.send_message(
                "このチャンネルはホテルではありません",
                ephemeral=True
            )

        if not await can_manage_room(bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message(
                "部屋の所有者または管理者のみ延長できます",
                ephemeral=True
            )

        tickets = await bot.db.get_tickets(user_id, guild_id)

        if tickets <= 0:
            return await interaction.response.send_message(
                "チケットがありません",
                ephemeral=True
            )

        # チケット消費
        await bot.db.remove_tickets(user_id, guild_id, 1)

        expire = room["expire_at"] or utcnow()
        new_expire = expire + timedelta(hours=24)

        # 期限更新
        await bot.db.update_room_expire(
            str(interaction.channel.id),
            new_expire
        )

        await interaction.response.send_message(
            f"🏨 24時間延長しました\n新しい期限: <t:{int(new_expire.timestamp())}:F>",
            ephemeral=True
        )

class TimeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="残り時間",
            style=discord.ButtonStyle.gray,
            emoji="⏰",
            custom_id="hotel_time"
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message("ホテルルームではありません", ephemeral=True)

        expire = room["expire_at"]
        if not expire:
            return await interaction.response.send_message("期限情報がありません", ephemeral=True)

        remaining = expire - utcnow()
        total_sec = int(remaining.total_seconds())

        if total_sec <= 0:
            return await interaction.response.send_message("⏰ まもなく期限切れです", ephemeral=True)

        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60

        await interaction.response.send_message(
            f"⏰ 残り **{hours}時間 {minutes}分**\n期限: <t:{int(expire.timestamp())}:F>",
            ephemeral=True
        )


class DeleteRoomButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="部屋を削除",
            style=discord.ButtonStyle.red,
            emoji="🗑️",
            custom_id="hotel_delete"
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        guild_id = str(interaction.guild.id)

        room = await bot.db.get_room(str(interaction.channel.id))
        if not room:
            return await interaction.response.send_message("ホテルルームではありません", ephemeral=True)

        if not await can_manage_room(bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message("部屋の所有者または管理者のみ削除できます", ephemeral=True)

        vc = interaction.guild.get_channel(int(room["vc_id"]))

        await interaction.response.send_message("🧹 部屋を削除します", ephemeral=True)

        await bot.db.delete_room(room["owner_id"], room["guild_id"])

        if vc:
            try:
                await vc.delete(reason="ホテルルーム削除")
            except Exception as e:
                print("[Hotel] room delete error:", e)


class LimitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="人数制限",
            style=discord.ButtonStyle.gray,
            emoji="👥",
            custom_id="hotel_limit"
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message("ホテルルームではありません", ephemeral=True)

        await interaction.response.send_modal(LimitModal())


class UnlockButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="接続許可（検索）",
            style=discord.ButtonStyle.green,
            emoji="🔓",
            custom_id="hotel_unlock"
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client
        guild_id = str(interaction.guild.id)

        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message(
                "ホテルルームではありません",
                ephemeral=True
            )

        if not await can_manage_room(bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message(
                "部屋の所有者または管理者のみ実行できます",
                ephemeral=True
            )

        await interaction.response.send_modal(AllowMemberSearchModal(room))

class AllowMemberSearchModal(discord.ui.Modal, title="接続許可ユーザー検索"):

    keyword = discord.ui.TextInput(
        label="ユーザーID / 名前 / ニックネーム",
        placeholder="例: 123456 / yuu / ゆう"
    )

    def __init__(self, room):
        super().__init__()
        self.room = room

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild
        query = self.keyword.value.strip()

        vc = guild.get_channel(int(self.room["vc_id"]))

        if not isinstance(vc, discord.VoiceChannel):
            return await interaction.response.send_message(
                "VCが見つかりません",
                ephemeral=True
            )

        candidates = []

        if query.isdigit():
            m = guild.get_member(int(query))
            if m:
                candidates.append(m)

        q = query.lower()

        for m in guild.members:
            if q in m.name.lower() or (m.nick and q in m.nick.lower()):
                candidates.append(m)

        candidates = list({m.id: m for m in candidates}.values())

        if not candidates:
            return await interaction.response.send_message(
                "一致するユーザーが見つかりません",
                ephemeral=True
            )

        if len(candidates) == 1:

            member = candidates[0]

            ow = vc.overwrites_for(member)
            ow.view_channel = True
            ow.connect = True

            await vc.set_permissions(member, overwrite=ow)

            return await interaction.response.send_message(
                f"✅ {member.display_name} に接続許可を付与しました",
                ephemeral=True
            )

        view = AllowMemberSelectView(candidates, vc)

        await interaction.response.send_message(
            "ユーザーを選択してください👇",
            view=view,
            ephemeral=True
        )

class AllowMemberSelectView(discord.ui.View):

    def __init__(self, members, vc):
        super().__init__(timeout=20)
        self.add_item(AllowMemberSelect(members, vc))


class AllowMemberSelect(discord.ui.Select):

    def __init__(self, members, vc):

        self.vc = vc

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in members
        ]

        super().__init__(
            placeholder="ユーザーを選択",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)

        ow = self.vc.overwrites_for(member)
        ow.view_channel = True
        ow.connect = True

        await self.vc.set_permissions(member, overwrite=ow)

        await interaction.response.send_message(
            f"✅ {member.display_name} に接続許可を付与しました",
            ephemeral=True
        )

class LockButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="接続拒否",
            style=discord.ButtonStyle.red,
            emoji="🔒",
            custom_id="hotel_lock"
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client
        guild_id = str(interaction.guild.id)

        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message(
                "ホテルルームではありません",
                ephemeral=True
            )

        if not await can_manage_room(bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message(
                "部屋の所有者または管理者のみ実行できます",
                ephemeral=True
            )

        vc = interaction.guild.get_channel(int(room["vc_id"]))

        owner_id = str(room["owner_id"])

        allowed = [
            m for m, perms in vc.overwrites.items()
            if (
                isinstance(m, discord.Member)
                and perms.connect
                and str(m.id) != owner_id
                and not m.bot
            )
        ]

        if not allowed:
            return await interaction.response.send_message(
                "許可済みユーザーはいません",
                ephemeral=True
            )

        view = DenySelectView(allowed, vc)

        await interaction.response.send_message(
            "拒否するユーザーを選択",
            view=view,
            ephemeral=True
        )

class DenySelectView(discord.ui.View):

    def __init__(self, members, vc):
        super().__init__(timeout=20)
        self.add_item(DenySelect(members, vc))


class DenySelect(discord.ui.Select):

    def __init__(self, members, vc):

        self.vc = vc

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in members
        ]

        super().__init__(
            placeholder="拒否するユーザー",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        member = interaction.guild.get_member(int(self.values[0]))

        await self.vc.set_permissions(
            member,
            connect=False,
            view_channel=False
        )

        await interaction.response.send_message(
            f"🚫 {member.display_name} を拒否しました",
            ephemeral=True
        )


class RenameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="名前変更",
            style=discord.ButtonStyle.gray,
            emoji="✏️",
            custom_id="hotel_rename"
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message("ホテルルームではありません", ephemeral=True)

        await interaction.response.send_modal(RenameModal())


class RoomView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ExtendButton())
        self.add_item(TimeButton())
        self.add_item(DeleteRoomButton())
        self.add_item(LimitButton())
        self.add_item(LockButton())
        self.add_item(UnlockButton())
        self.add_item(RenameButton())


# =========================================================
# チケット購入ボタン
# =========================================================
class TicketBuyButton(discord.ui.Button):
    def __init__(self, amount: int):
        super().__init__(
            label=f"{amount}枚購入",
            style=discord.ButtonStyle.gray,
            custom_id=f"hotel_buy_{amount}"
        )
        self.amount = amount

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await bot.db.get_hotel_settings(guild_id)
        if not settings:
            return await interaction.response.send_message("ホテル設定がありません", ephemeral=True)

        if self.amount == 1:
            price = settings["ticket_price_1"] or 0
        elif self.amount == 10:
            price = settings["ticket_price_10"] or 0
        elif self.amount == 30:
            price = settings["ticket_price_30"] or 0
        else:
            return await interaction.response.send_message("不正な購入枚数です", ephemeral=True)

        if price <= 0:
            return await interaction.response.send_message("この購入プランは未設定です", ephemeral=True)

        balance = await bot.db.get_balance(user_id, guild_id)
        if balance < price:
            return await interaction.response.send_message(
                f"残高が足りません\n必要: {price}",
                ephemeral=True
            )

        result = await bot.db.remove_balance(user_id, guild_id, price)
        if not result:
            return await interaction.response.send_message("残高の更新に失敗しました", ephemeral=True)

        new_tickets = await bot.db.add_tickets(user_id, guild_id, self.amount)

        await interaction.response.send_message(
            f"🎫 チケットを **{self.amount}枚** 購入しました\n現在の所持枚数: **{new_tickets}枚**",
            ephemeral=True
        )


class TicketView(discord.ui.View):
    def __init__(self, ticket_price_30: Optional[int]):
        super().__init__(timeout=60)
        self.add_item(TicketBuyButton(1))
        self.add_item(TicketBuyButton(10))
        if ticket_price_30 and ticket_price_30 > 0:
            self.add_item(TicketBuyButton(30))


class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="チケット購入",
            style=discord.ButtonStyle.blurple,
            emoji="🎫",
            custom_id="hotel_ticket"
        )

    async def callback(self, interaction: discord.Interaction):
        settings = await interaction.client.db.get_hotel_settings(str(interaction.guild.id))
        price30 = settings["ticket_price_30"] if settings else None

        await interaction.response.send_message(
            "購入する枚数を選択してください",
            view=TicketView(price30),
            ephemeral=True
        )


# =========================================================
# チェックイン
# =========================================================
class CheckinButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="チェックイン",
            style=discord.ButtonStyle.green,
            emoji="🏨",
            custom_id="hotel_checkin"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client
        guild = interaction.guild
        guild_id = str(guild.id)
        user_id = str(interaction.user.id)

        settings = await bot.db.get_hotel_settings(guild_id)
        if not settings:
            return await interaction.followup.send("ホテルが初期設定されていません。", ephemeral=True)

        room = await bot.db.get_room_by_owner(user_id, guild_id)
        if room:
            vc = guild.get_channel(int(room["vc_id"]))
            if vc is None:
                await bot.db.delete_room(room["owner_id"], room["guild_id"])
            else:
                return await interaction.followup.send("⚠ すでにホテルルームを所持しています。", ephemeral=True)

        tickets = await bot.db.get_tickets(user_id, guild_id)
        if tickets <= 0:
            return await interaction.followup.send("ホテルチケットがありません。", ephemeral=True)

        category = await choose_category(guild, settings["category_ids"] or [])
        if not category:
            return await interaction.followup.send("カテゴリーが見つかりません。", ephemeral=True)

        # 先にチケット消費
        await bot.db.remove_tickets(user_id, guild_id, 1)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
            interaction.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True),
        }

        try:
            vc = await guild.create_voice_channel(
                name=f"{interaction.user.display_name}の部屋",
                category=category,
                overwrites=overwrites
            )

        except Exception as e:
            print("[Hotel] VC create error:", e)
            await bot.db.add_tickets(user_id, guild_id, 1)
            return await interaction.followup.send("VCの作成に失敗しました。チケットは返却しました。", ephemeral=True)

        expire_at = utcnow() + timedelta(hours=24)

        # 重要:
        # ルーム操作は VC 内テキストで行わせるため text_id も vc.id に合わせる
        await bot.db.save_room(
            guild_id,
            user_id,
            str(vc.id),
            str(vc.id),
            expire_at
        )

        embed = discord.Embed(
            title="🏨 ホテルルーム",
            description=(
                "この部屋は24時間で自動削除されます\n"
                "チケットで延長できます\n\n"
                f"期限: <t:{int(expire_at.timestamp())}:F>"
            ),
            color=0x2ecc71
        )

        try:
            await vc.send(embed=embed, view=RoomView())
        except Exception as e:
            print("[Hotel] VC text send error:", e)

        if interaction.user.voice:
            try:
                await interaction.user.move_to(vc)
            except Exception:
                pass

        await interaction.followup.send(
            f"🏨 {vc.mention} を作成しました\nVCチャットに操作パネルがあります",
            ephemeral=True
        )

        log = discord.Embed(title="🏨 ホテルチェックイン", color=0x2ecc71)
        log.add_field(name="ユーザー", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        log.add_field(name="VC", value=vc.mention, inline=False)
        log.add_field(name="期限", value=f"<t:{int(expire_at.timestamp())}:F>", inline=False)
        await send_hotel_log(guild, bot, guild_id, log)


class HotelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CheckinButton())
        self.add_item(TicketButton())


# =========================================================
# Cog
# =========================================================
class HotelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cleanup_lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(HotelView())
        self.bot.add_view(RoomView())

        if not self.room_checker.is_running():
            self.room_checker.start()
        if not self.orphan_cleaner.is_running():
            self.orphan_cleaner.start()
        if not self.owner_protector.is_running():
            self.owner_protector.start()

    async def cog_unload(self):
        if self.room_checker.is_running():
            self.room_checker.cancel()
        if self.orphan_cleaner.is_running():
            self.orphan_cleaner.cancel()
        if self.owner_protector.is_running():
            self.owner_protector.cancel()

    # -------------------------------------------------
    # ルーム期限切れチェック
    # -------------------------------------------------
    @tasks.loop(minutes=1)
    async def room_checker(self):
        async with self._cleanup_lock:
            rooms = await self.bot.db.get_all_rooms()
            now = utcnow()

            for room in rooms:
                expire = room["expire_at"]
                if not expire or now < expire:
                    continue

                guild = self.bot.get_guild(int(room["guild_id"]))
                if guild:
                    vc = guild.get_channel(int(room["vc_id"]))
                    if vc:
                        try:
                            await vc.delete(reason="ホテル期限切れ")
                        except Exception as e:
                            print("[Hotel] room delete error:", e)

                await self.bot.db.delete_room(room["owner_id"], room["guild_id"])

    @room_checker.before_loop
    async def before_room_checker(self):
        await self.bot.wait_until_ready()

    # -------------------------------------------------
    # 孤児データ掃除
    # -------------------------------------------------
    @tasks.loop(minutes=5)
    async def orphan_cleaner(self):
        async with self._cleanup_lock:
            rooms = await self.bot.db.get_all_rooms()

            for room in rooms:
                guild = self.bot.get_guild(int(room["guild_id"]))
                if not guild:
                    continue

                vc = guild.get_channel(int(room["vc_id"]))
                if vc is None:
                    await self.bot.db.delete_room(room["owner_id"], room["guild_id"])
                    print(f"[Hotel] orphan cleanup: owner={room['owner_id']} guild={room['guild_id']}")

    @orphan_cleaner.before_loop
    async def before_orphan_cleaner(self):
        await self.bot.wait_until_ready()

    # -------------------------------------------------
    # 部屋主保護
    # -------------------------------------------------
    @tasks.loop(seconds=30)
    async def owner_protector(self):
        rooms = await self.bot.db.get_all_rooms()

        for room in rooms:
            guild = self.bot.get_guild(int(room["guild_id"]))
            if not guild:
                continue

            vc = guild.get_channel(int(room["vc_id"]))
            if not isinstance(vc, discord.VoiceChannel):
                continue

            owner = guild.get_member(int(room["owner_id"]))
            if owner is None:
                continue

            ow = vc.overwrites_for(owner)
            changed = False

            if ow.connect is False:
                ow.connect = True
                changed = True
            if ow.view_channel is False:
                ow.view_channel = True
                changed = True

            if changed:
                try:
                    await vc.set_permissions(owner, overwrite=ow, reason="ホテル部屋主保護")
                except Exception:
                    pass

    @owner_protector.before_loop
    async def before_owner_protector(self):
        await self.bot.wait_until_ready()

    # -------------------------------------------------
    # VC削除時のDB掃除
    # -------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.VoiceChannel):
            return

        room = await self.bot.db.get_room(str(channel.id))
        if room:
            await self.bot.db.delete_room(room["owner_id"], room["guild_id"])
            print(f"[Hotel] channel delete cleanup: {channel.id}")

    # =========================
    # ホテル初期設定
    # =========================
    @app_commands.command(name="ホテル初期設定")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def hotel_setup(
        self,
        interaction: discord.Interaction,
        カテゴリー1: discord.CategoryChannel,
        チケット1枚価格: int,
        チケット10枚価格: int,
        ホテル管理ロール: Optional[discord.Role] = None,
        ログチャンネル: Optional[discord.TextChannel] = None,
        サブ垢ロール: Optional[discord.Role] = None,
        チケット30枚価格: Optional[int] = None,
        カテゴリー2: Optional[discord.CategoryChannel] = None,
        カテゴリー3: Optional[discord.CategoryChannel] = None,
    ):
        guild_id = str(interaction.guild.id)

        if not await is_admin_user(self.bot, interaction.user, guild_id):
            return await interaction.response.send_message("❌ 管理者ロールが必要です。", ephemeral=True)

        categories = [カテゴリー1, カテゴリー2, カテゴリー3]
        category_ids = [str(c.id) for c in categories if c is not None]

        await self.bot.db.set_hotel_settings(
            guild_id,
            str(ホテル管理ロール.id) if ホテル管理ロール else None,
            str(ログチャンネル.id) if ログチャンネル else None,
            str(サブ垢ロール.id) if サブ垢ロール else None,
            チケット1枚価格,
            チケット10枚価格,
            チケット30枚価格,
            category_ids
        )

        txt = "🏨 ホテル設定を保存しました\n"
        txt += f"カテゴリ: {', '.join(c.mention for c in categories if c)}\n"
        txt += f"1枚: {チケット1枚価格} / 10枚: {チケット10枚価格}"
        if チケット30枚価格:
            txt += f" / 30枚: {チケット30枚価格}"

        await interaction.response.send_message(txt, ephemeral=True)

    # =========================
    # ホテルパネル設置
    # =========================
    @app_commands.command(name="ホテルパネル設置")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def hotel_panel(
        self,
        interaction: discord.Interaction,
        タイトル: str,
        本文: str
    ):
        guild_id = str(interaction.guild.id)

        if not await is_admin_user(self.bot, interaction.user, guild_id):
            return await interaction.response.send_message("❌ 管理者ロールが必要です。", ephemeral=True)

        embed = discord.Embed(
            title=タイトル,
            description=本文,
            color=0x2ecc71
        )

        await interaction.response.send_message(embed=embed, view=HotelView())

    # =========================
    # チケット枚数確認
    # =========================
    @app_commands.command(name="ホテルチケット枚数確認")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ticket_check(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        tickets = await self.bot.db.get_tickets(user_id, guild_id)

        await interaction.response.send_message(
            f"🎫 あなたのホテルチケット\n現在 **{tickets} 枚**",
            ephemeral=True
        )

    # =========================
    # ルーム操作パネル再送
    # =========================
    @app_commands.command(name="ホテルボタン再送")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def hotel_resend_panel(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        room = await self.bot.db.get_room(str(interaction.channel.id))
        if not room:
            return await interaction.response.send_message("❌ このチャンネルはホテルルームではありません。", ephemeral=True)

        if not await can_manage_room(self.bot, interaction.user, guild_id, room["owner_id"]):
            return await interaction.response.send_message("❌ 作成者または管理者のみ再送できます。", ephemeral=True)

        await interaction.channel.send("🔄 操作パネルを再送しました", view=RoomView())
        await interaction.response.send_message("🔄 再送しました", ephemeral=True)

    # =========================
    # ホテルリセット
    # =========================
    @app_commands.command(name="ホテルリセット")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def hotel_reset(self, interaction: discord.Interaction, 対象: discord.Member):
        guild_id = str(interaction.guild.id)

        if not await is_admin_user(self.bot, interaction.user, guild_id):
            return await interaction.response.send_message("❌ 管理者ロールが必要です。", ephemeral=True)

        room = await self.bot.db.get_room_by_owner(str(対象.id), guild_id)
        if not room:
            return await interaction.response.send_message("⚠ そのユーザーは現在ホテルルームを所持していません。", ephemeral=True)

        vc = interaction.guild.get_channel(int(room["vc_id"]))
        if vc:
            try:
                await vc.delete(reason="ホテルリセット")
            except Exception:
                pass

        await self.bot.db.delete_room(room["owner_id"], room["guild_id"])

        await interaction.response.send_message(
            f"🧹 {対象.mention} のホテルデータをリセットしました",
            ephemeral=True
        )

    # =========================
    # チケット管理
    # =========================
    @app_commands.command(name="hotel_ticket")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.describe(
        member="対象ユーザー",
        mode="add / remove / set",
        amount="枚数"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="付与", value="add"),
            app_commands.Choice(name="減算", value="remove"),
            app_commands.Choice(name="上書き", value="set"),
        ]
    )
    async def hotel_ticket(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        mode: app_commands.Choice[str],
        amount: int
    ):
        guild_id = str(interaction.guild.id)

        admin_ok = await is_admin_user(self.bot, interaction.user, guild_id)
        manager_ok = await is_hotel_manager(self.bot, interaction.user, guild_id)

        if not (admin_ok or manager_ok):
            return await interaction.response.send_message(
                "❌ 管理者またはホテル管理ロールが必要です。",
                ephemeral=True
            )

        if amount < 0:
            return await interaction.response.send_message("❌ 0以上を指定してください。", ephemeral=True)

        user_id = str(member.id)
        current = await self.bot.db.get_tickets(user_id, guild_id)

        if mode.value == "add":
            new_amount = await self.bot.db.add_tickets(user_id, guild_id, amount)
            op_text = f"+{amount}"
        elif mode.value == "remove":
            new_amount = await self.bot.db.remove_tickets(user_id, guild_id, amount)
            op_text = f"-{amount}"
        else:
            diff = amount - current
            if diff >= 0:
                new_amount = await self.bot.db.add_tickets(user_id, guild_id, diff)
            else:
                new_amount = await self.bot.db.remove_tickets(user_id, guild_id, abs(diff))
            op_text = f"={amount}"

        await interaction.response.send_message(
            f"🎫 {member.mention} のホテルチケットを {op_text} しました\n現在: **{new_amount}枚**",
            ephemeral=True
        )

    # -------------------------------------------------
    # エラーハンドラ
    # -------------------------------------------------
    @hotel_setup.error
    @hotel_panel.error
    @ticket_check.error
    @hotel_resend_panel.error
    @hotel_reset.error
    @hotel_ticket.error
    async def hotel_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        print("[Hotel] command error:", repr(error))
        if interaction.response.is_done():
            await interaction.followup.send("エラーが発生しました。コンソールを確認してください。", ephemeral=True)
        else:
            await interaction.response.send_message("エラーが発生しました。コンソールを確認してください。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(HotelCog(bot))





