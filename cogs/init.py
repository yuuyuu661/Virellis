import discord
from discord.ext import commands
from discord import app_commands


OWNER_ID = 969739156756508672


class InitCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    # =========================
    # 初期設定
    # =========================
    @app_commands.command(name="初期設定", description="BOTの初期設定を行います")
    @app_commands.guilds(discord.Object(id=1475448864122208350))
    async def init_system(
        self,
        interaction: discord.Interaction,
        管理者ロール: discord.Role,
        銀行ロール: discord.Role,
        ホテルロール: discord.Role,
        サブ垢ロール: discord.Role,
        通貨単位: str
    ):

        # 実行者チェック
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                "❌ このコマンドは実行できません。",
                ephemeral=True
            )

        guild_id = str(interaction.guild.id)

        # DB保存
        await self.bot.db.set_settings(
            guild_id,
            admin_roles=[str(管理者ロール.id)],
            bank_roles=[str(銀行ロール.id)],
            hotel_role=str(ホテルロール.id),
            sub_role=str(サブ垢ロール.id),
            currency_unit=通貨単位
        )

        embed = discord.Embed(
            title="⚙ 初期設定完了",
            color=0x2ecc71
        )

        embed.add_field(
            name="管理者ロール",
            value=管理者ロール.mention,
            inline=False
        )

        embed.add_field(
            name="銀行ロール",
            value=銀行ロール.mention,
            inline=False
        )

        embed.add_field(
            name="ホテルロール",
            value=ホテルロール.mention,
            inline=False
        )

        embed.add_field(
            name="サブ垢ロール",
            value=サブ垢ロール.mention,
            inline=False
        )

        await interaction.response.send_message(embed=embed)


# =========================
# Cog登録
# =========================

async def setup(bot):
    await bot.add_cog(InitCog(bot))

