import discord
from discord.ext import commands
from discord import app_commands


GUILD_ID = 1475448864122208350


class BalanceCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    # =========================
    # 残高確認
    # =========================
    @app_commands.command(name="bal", description="残高を確認します")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def balance(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None
    ):

        guild_id = str(interaction.guild.id)

        # 自分
        if user is None:
            user = interaction.user

        # 他人確認 → admin必要
        if user != interaction.user:

            settings = await self.bot.db.get_settings(guild_id)

            admin_roles = settings["admin_roles"] if settings else []

            if not any(str(role.id) in admin_roles for role in interaction.user.roles):

                return await interaction.response.send_message(
                    "❌ 他人の残高を見る権限がありません。",
                    ephemeral=True
                )

        balance = await self.bot.db.get_balance(
            str(user.id),
            guild_id
        )
        settings = await self.bot.db.get_settings(guild_id)
        unit = settings["currency_unit"] if settings else ""

        if balance is None:

            return await interaction.response.send_message(
                "このユーザーはまだ通貨を使用していません。",
                ephemeral=True
            )

        embed = discord.Embed(
            title="💰 残高",
            color=0x2ecc71
        )

        embed.add_field(
            name="ユーザー",
            value=user.mention,
            inline=False
        )

        embed.add_field(
            name="残高",
            value=f"{balance:,} {unit}",
            inline=False
        )

        await interaction.response.send_message(embed=embed)


    # =========================
    # 送金
    # =========================
    @app_commands.command(name="pay", description="ユーザーに送金します")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def pay(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int
    ):

        guild_id = str(interaction.guild.id)
        sender_id = str(interaction.user.id)
        target_id = str(user.id)

        if amount <= 0:
            return await interaction.response.send_message(
                "❌ 金額は1以上にしてください。",
                ephemeral=True
            )

        if user.bot:
            return await interaction.response.send_message(
                "❌ Botには送金できません。",
                ephemeral=True
            )

        if user.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ 自分には送金できません。",
                ephemeral=True
            )

        sender_balance = await self.bot.db.get_balance(
            sender_id,
            guild_id
        )

        if sender_balance < amount:

            return await interaction.response.send_message(
                f"❌ 残高不足です。\n所持：{sender_balance:,}",
                ephemeral=True
            )

        # 送金処理
        await self.bot.db.remove_balance(
            sender_id,
            guild_id,
            amount
        )

        await self.bot.db.add_balance(
            target_id,
            guild_id,
            amount
        )

        embed = discord.Embed(
            title="💸 送金完了",
            color=0xf1c40f
        )

        embed.add_field(
            name="送金者",
            value=interaction.user.mention,
            inline=False
        )

        embed.add_field(
            name="受取人",
            value=user.mention,
            inline=False
        )

        settings = await self.bot.db.get_settings(guild_id)
        unit = settings["currency_unit"] if settings else ""        
        embed.add_field(
            name="金額",
            value=f"{amount:,} {unit}",
            inline=False
        )


        await interaction.response.send_message(embed=embed)


# =========================
# Cog登録
# =========================
async def setup(bot):
    await bot.add_cog(BalanceCog(bot))
