import discord
from discord.ext import commands
from discord import app_commands

GUILD_ID = 1475448864122208350


class AdminCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    # =========================
    # 権限チェック
    # =========================
    async def check_admin(self, interaction):

        guild_id = str(interaction.guild.id)
        settings = await self.bot.db.get_settings(guild_id)

        if not settings:
            return False

        admin_roles = settings["admin_roles"] or []
        bank_roles = settings["bank_roles"] or []

        user_roles = [str(r.id) for r in interaction.user.roles]

        if any(r in admin_roles for r in user_roles):
            return True

        if any(r in bank_roles for r in user_roles):
            return True

        return False


    # =========================
    # 残高設定
    # =========================
    @app_commands.command(name="残高設定", description="ユーザーの残高を変更します")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def set_balance(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        金額: int,
        操作: str
    ):

        if not await self.check_admin(interaction):

            return await interaction.response.send_message(
                "❌ 権限がありません。",
                ephemeral=True
            )

        guild_id = str(interaction.guild.id)
        uid = str(user.id)

        if 操作 == "設定":

            await self.bot.db.set_balance(uid, guild_id, 金額)

        elif 操作 == "増加":

            await self.bot.db.add_balance(uid, guild_id, 金額)

        elif 操作 == "減少":

            await self.bot.db.remove_balance(uid, guild_id, 金額)

        else:

            return await interaction.response.send_message(
                "操作は 設定 / 増加 / 減少 のみです",
                ephemeral=True
            )

        balance = await self.bot.db.get_balance(uid, guild_id)

        embed = discord.Embed(
            title="💰 残高変更",
            color=0x3498db
        )

        embed.add_field(name="ユーザー", value=user.mention, inline=False)
        embed.add_field(name="操作", value=操作, inline=True)
        settings = await self.bot.db.get_settings(guild_id)
        unit = settings["currency_unit"] if settings else ""
        embed.add_field(name="金額", value=f"{金額:,} {unit}", inline=True)
        embed.add_field(name="現在残高", value=f"{balance:,} {unit}", inline=False)

        await interaction.response.send_message(embed=embed)


    # =========================
    # 残高ランキング
    # =========================
    @app_commands.command(name="残高一覧", description="サーバーの残高ランキング")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ranking(self, interaction: discord.Interaction):

        if not await self.check_admin(interaction):

            return await interaction.response.send_message(
                "❌ 権限がありません。",
                ephemeral=True
            )

        guild_id = str(interaction.guild.id)

        settings = await self.bot.db.get_settings(guild_id)
        unit = settings["currency_unit"] if settings else ""

        rows = await self.bot.db.get_ranking(guild_id)

        if not rows:

            return await interaction.response.send_message(
                "データがありません"
            )

        embed = discord.Embed(
            title="💰 残高ランキング",
            color=0xf1c40f
        )

        text = ""

        for i, r in enumerate(rows[:20], start=1):

            member = interaction.guild.get_member(int(r["user_id"]))

            if member:
                name = member.display_name
            else:
                name = r["user_id"]

            text += f"{i}. {name} — {r['balance']:,} {unit}\n"

        embed.description = text

        await interaction.response.send_message(embed=embed)


    # =========================
    # ロール送金
    # =========================
    @app_commands.command(name="ロール送金", description="ロール所持者に一括送金")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def role_pay(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        金額: int,
        操作: str
    ):

        if not await self.check_admin(interaction):

            return await interaction.response.send_message(
                "❌ 権限がありません。",
                ephemeral=True
            )

        guild_id = str(interaction.guild.id)

        members = [
            m for m in interaction.guild.members
            if role in m.roles and not m.bot
        ]

        success_count = 0
        failed_users = []

        for m in members:

            uid = str(m.id)

            balance = await self.bot.db.get_balance(uid, guild_id)

            if 操作 == "増加":

                await self.bot.db.add_balance(uid, guild_id, 金額)
                success_count += 1

            elif 操作 == "減少":

                if balance is None or balance < 金額:

                    failed_users.append(m)
                    continue

                await self.bot.db.remove_balance(uid, guild_id, 金額)
                success_count += 1

            else:
                continue

        embed = discord.Embed(
            title="💸 ロール送金",
            color=0xe67e22
        )

        embed.add_field(name="対象ロール", value=role.mention, inline=False)
        embed.add_field(name="操作", value=操作, inline=True)
        embed.add_field(name="金額", value=f"{金額:,}", inline=True)
        embed.add_field(name="成功人数", value=success_count, inline=False)

        await interaction.response.send_message(embed=embed)
        if failed_users:

            mentions = " ".join(m.mention for m in failed_users)

            await interaction.channel.send(
                f"⚠ 残高不足で減少できなかったユーザー\n{mentions}"
            )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
    
