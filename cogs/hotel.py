import discord
from discord.ext import commands
from discord import app_commands
GUILD_ID = 1475448864122208350

class CheckinButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="チェックイン",
            style=discord.ButtonStyle.green,
            emoji="🏨"
        )

    async def callback(self, interaction: discord.Interaction):

        bot = interaction.client
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await bot.db.get_hotel_settings(guild_id)

        if not settings:
            return await interaction.response.send_message(
                "ホテルが初期設定されていません。",
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

        # ルーム保存
        await bot.db.save_room(
            str(vc.id),
            guild_id,
            user_id,
            None
        )

        # ユーザー移動
        if interaction.user.voice:
            await interaction.user.move_to(vc)

        await interaction.response.send_message(
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


class HotelCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


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
