import discord
from discord.ext import commands
from discord import app_commands
GUILD_ID = 1475448864122208350
from datetime import datetime, timedelta
from discord.ext import tasks

class CheckinButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="チェックイン",
            style=discord.ButtonStyle.green,
            emoji="🏨"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await bot.db.get_hotel_settings(guild_id)

        if not settings:
            return await interaction.followup.send(
                "ホテルが初期設定されていません。",
                ephemeral=True
            )

        # -----------------------------
        # 同時チェックイン防止
        # -----------------------------
        room = await bot.db.get_room_by_owner(user_id, guild_id)

        if room:

            vc = interaction.guild.get_channel(int(room["vc_id"]))

            # VCが存在しない場合は孤児データ削除
            if vc is None:
                await bot.db.delete_room(room["vc_id"])
            else:
                return await interaction.response.send_message(
                    "⚠ すでにホテルルームを所持しています。",
                    ephemeral=True
                )

        tickets = await bot.db.get_tickets(user_id, guild_id)

        if tickets <= 0:
            return await interaction.response.send_message(
                "ホテルチケットがありません。",
                ephemeral=True
            )

        category_id = settings["category_ids"][0]
        category = interaction.guild.get_channel(int(category_id))

        if not category:
            return await interaction.response.send_message(
                "カテゴリーが見つかりません。",
                ephemeral=True
            )

        # チケット消費
        await bot.db.remove_tickets(user_id, guild_id, 1)

        # VC作成
        vc = await interaction.guild.create_voice_channel(
            name=f"{interaction.user.display_name}の部屋",
            category=category
        )
        text_channel = interaction.channel

        embed = discord.Embed(
            title="🏨 ホテルルーム",
            description="この部屋は24時間で自動削除されます\nチケットで延長できます",
            color=0x2ecc71
        )

        await interaction.channel.send(
            embed=embed,
            view=RoomView()
        )

        # ルーム保存
        expire_at = datetime.utcnow() + timedelta(hours=24)

        await bot.db.save_room(
            user_id,
            guild_id,
            str(vc.id),
            str(text_channel.id),
            expire_at
        )

        # ユーザー移動
        if interaction.user.voice:
            await interaction.user.move_to(vc)

        await interaction.followup.send(
            f"🏨 {vc.mention} を作成しました",
            ephemeral=True
        )


class TicketButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="チケット購入",
            style=discord.ButtonStyle.blurple,
            emoji="🎫"
        )

    async def callback(self, interaction: discord.Interaction):

        view = TicketView()
        await interaction.response.send_message(
            "購入する枚数を選択してください",
            view=view,
            ephemeral=True
        )


class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=60)

        self.add_item(Ticket1())
        self.add_item(Ticket10())


class Ticket1(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="1枚購入",
            style=discord.ButtonStyle.gray
        )

    async def callback(self, interaction: discord.Interaction):

        

        bot = interaction.client
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await bot.db.get_hotel_settings(guild_id)

        price = settings["ticket_price_1"]

        balance = await bot.db.get_balance(user_id, guild_id)

        if balance < price:
            return await interaction.response.send_message(
                "残高が足りません",
                ephemeral=True
            )

        await bot.db.remove_balance(user_id, guild_id, price)
        await bot.db.add_tickets(user_id, guild_id, 1)

        await interaction.response.send_message(
            "🎫 チケットを1枚購入しました",
            ephemeral=True
        )


class Ticket10(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="10枚購入",
            style=discord.ButtonStyle.gray
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await bot.db.get_hotel_settings(guild_id)

        price = settings["ticket_price_10"]

        balance = await bot.db.get_balance(user_id, guild_id)

        if balance < price:
            return await interaction.response.send_message(
                "残高が足りません",
                ephemeral=True
            )

        await bot.db.remove_balance(user_id, guild_id, price)
        await bot.db.add_tickets(user_id, guild_id, 10)

        await interaction.response.send_message(
            "🎫 チケットを10枚購入しました",
            ephemeral=True
        )


class HotelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(CheckinButton())
        self.add_item(TicketButton())
        
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

class ExtendButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="24時間延長",
            style=discord.ButtonStyle.blurple,
            emoji="🎫"
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

        if room["owner_id"] != user_id:
            return await interaction.response.send_message(
                "部屋の所有者のみ延長できます",
                ephemeral=True
            )

        tickets = await bot.db.get_tickets(user_id, guild_id)

        if tickets <= 0:
            return await interaction.response.send_message(
                "チケットがありません",
                ephemeral=True
            )

        await bot.db.remove_tickets(user_id, guild_id, 1)

        expire = room["expire_at"]

        if not expire:
            expire = datetime.utcnow()

        new_expire = expire + timedelta(hours=24)

        await bot.db.save_room(
            user_id,
            guild_id,
            str(vc.id),
            str(text_channel.id),
            expire_at
        )

        await interaction.response.send_message(
            "🏨 24時間延長しました",
            ephemeral=True
        )

class DeleteRoomButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="部屋を削除",
            style=discord.ButtonStyle.red,
            emoji="🗑️"
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client

        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return

        if str(interaction.user.id) != room["owner_id"]:
            return await interaction.response.send_message(
                "部屋の所有者のみ削除できます",
                ephemeral=True
            )

        await bot.db.delete_room(str(interaction.channel.id))

        await interaction.channel.delete()

class TimeButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="残り時間",
            style=discord.ButtonStyle.gray,
            emoji="⏰"
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client
        room = await bot.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message(
                "ホテルルームではありません",
                ephemeral=True
            )

        expire = room["expire_at"]

        if not expire:
            return await interaction.response.send_message(
                "期限情報がありません",
                ephemeral=True
            )

        now = datetime.utcnow()
        remaining = expire - now

        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)

        await interaction.response.send_message(
            f"⏰ 残り {hours}時間 {minutes}分",
            ephemeral=True
        )
class LimitButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="人数制限",
            style=discord.ButtonStyle.gray,
            emoji="👥"
        )

    async def callback(self, interaction: discord.Interaction):

        room = await interaction.client.db.get_room(str(interaction.channel.id))

        if not room:
            return await interaction.response.send_message(
                "ホテルルームではありません",
                ephemeral=True
            )

        if str(interaction.user.id) != room["owner_id"]:
            return await interaction.response.send_message(
                "部屋の所有者のみ変更できます",
                ephemeral=True
            )

        await interaction.response.send_modal(LimitModal())

class LimitModal(discord.ui.Modal, title="人数制限変更"):

    limit = discord.ui.TextInput(
        label="人数",
        placeholder="0 = 無制限",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):

        limit = int(self.limit.value)

        await interaction.channel.edit(user_limit=limit)

        await interaction.response.send_message(
            f"👥 人数制限を {limit} に変更しました",
            ephemeral=True
        )
class LockButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="接続拒否",
            style=discord.ButtonStyle.red,
            emoji="🔒"
        )

    async def callback(self, interaction: discord.Interaction):

        room = await interaction.client.db.get_room(str(interaction.channel.id))

        if str(interaction.user.id) != room["owner_id"]:
            return await interaction.response.send_message(
                "部屋の所有者のみ実行できます",
                ephemeral=True
            )

        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.connect = False

        await interaction.channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite
        )

        await interaction.response.send_message(
            "🔒 接続を拒否しました",
            ephemeral=True
        )
class UnlockButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="接続許可",
            style=discord.ButtonStyle.green,
            emoji="🔓"
        )

    async def callback(self, interaction: discord.Interaction):

        room = await interaction.client.db.get_room(str(interaction.channel.id))

        if str(interaction.user.id) != room["owner_id"]:
            return await interaction.response.send_message(
                "部屋の所有者のみ実行できます",
                ephemeral=True
            )

        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.connect = None

        await interaction.channel.set_permissions(
            interaction.guild.default_role,
            overwrite=overwrite
        )

        await interaction.response.send_message(
            "🔓 接続を許可しました",
            ephemeral=True
        )

class RenameButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="名前変更",
            style=discord.ButtonStyle.gray,
            emoji="✏️"
        )

    async def callback(self, interaction: discord.Interaction):

        room = await interaction.client.db.get_room(str(interaction.channel.id))

        if str(interaction.user.id) != room["owner_id"]:
            return await interaction.response.send_message(
                "部屋の所有者のみ変更できます",
                ephemeral=True
            )

        await interaction.response.send_modal(RenameModal())

class RenameModal(discord.ui.Modal, title="部屋名変更"):

    name = discord.ui.TextInput(
        label="新しい部屋名",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.channel.edit(name=self.name.value)

        await interaction.response.send_message(
            "✏️ 部屋名を変更しました",
            ephemeral=True
        )


            
class HotelCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(HotelView())
        bot.add_view(RoomView())
        self.room_checker.start()

    @tasks.loop(minutes=1)
    async def room_checker(self):

        rooms = await self.bot.db.get_all_rooms()

        now = datetime.utcnow()

        for room in rooms:

            expire = room["expire_at"]

            if not expire:
                continue

            if now >= expire:

                guild = self.bot.get_guild(int(room["guild_id"]))
                if not guild:
                    continue

                channel = guild.get_channel(int(room["channel_id"]))
                if not channel:
                    await self.bot.db.delete_room(room["channel_id"])
                    continue

                if channel:
                    try:
                        await channel.delete()
                    except:
                        pass

                await self.bot.db.delete_room(room["channel_id"])


    # =========================
    # ホテル初期設定
    # =========================
    @app_commands.command(name="ホテル初期設定")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def hotel_setup(
        self,
        interaction: discord.Interaction,
        カテゴリー: discord.CategoryChannel,
        チケット1枚価格: int,
        チケット10枚価格: int
    ):

        guild_id = str(interaction.guild.id)

        await self.bot.db.set_hotel_settings(
            guild_id,
            None,
            None,
            None,
            チケット1枚価格,
            チケット10枚価格,
            None,
            [str(カテゴリー.id)]
        )

        await interaction.response.send_message(
            "ホテル設定を保存しました"
        )


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

        embed = discord.Embed(
            title=タイトル,
            description=本文,
            color=0x2ecc71
        )

        await interaction.response.send_message(
            embed=embed,
            view=HotelView()
        )


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
            f"🎫 あなたのホテルチケット\n現在 {tickets} 枚",
            ephemeral=True
        )


async def setup(bot):

    await bot.add_cog(HotelCog(bot))








