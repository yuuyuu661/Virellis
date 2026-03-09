import inspect
import discord
from discord.ext import commands
from discord import app_commands

from logger import log_pay


class BalanceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ================================
    # 内部ヘルパー: 管理者判定
    # ================================
    async def _can_view_others(self, member: discord.Member) -> bool:
        """
        他ユーザーの残高を見てもよいかどうかを判定する。
        ・Discordの管理者権限
        ・settings.admin_roles に登録されたロール
        のどちらかを持っていれば True
        """
        # Discord の「サーバー管理者」権限
        if member.guild_permissions.administrator:
            return True

        # DB設定に登録されている管理者ロール
        settings = await self.bot.db.get_settings()
        admin_roles = settings["admin_roles"] or []

        return any(str(r.id) in admin_roles for r in member.roles)

    # ================================
    # /bal 残高確認（指定ユーザーを見る場合は管理者ロール必須）
    # ================================
    @app_commands.command(
        name="bal",
        description="自分または指定ユーザーの残高を確認します"
    )
    @app_commands.describe(
        member="確認したいユーザー（省略時は自分）"
    )
    async def bal(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):
        bot = self.bot
        guild = interaction.guild
        user = interaction.user

        if guild is None:
            return await interaction.response.send_message(
                "サーバー内でのみ使用できます。",
                ephemeral=True
            )

        db = bot.db

        # 対象ユーザー（未指定なら自分）
        target = member or user

        if target.id != user.id:
            settings = await db.get_settings()
            admin_roles = settings["admin_roles"] or []

            if not any(str(r.id) in admin_roles for r in user.roles):
                return await interaction.response.send_message(
                    "❌ 他ユーザーの残高を確認するには管理者ロールが必要です。",
                    ephemeral=True
                )

        try:
            # 残高
            row = await db.get_user(str(target.id), str(guild.id))
            # チケット枚数
            tickets = await db.get_tickets(str(target.id), str(guild.id))
            # ジャンボ購入数
            jumbo_count = await db.jumbo_get_user_count(
                str(guild.id),
                str(target.id)
            )

            # 通貨単位
            settings = await db.get_settings()
            unit = settings["currency_unit"]
        except Exception as e:
            print("bal error:", repr(e))
            if interaction.response.is_done():
                return await interaction.followup.send(
                    "内部エラーが発生しました。（bal）",
                    ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    "内部エラーが発生しました。（bal）",
                    ephemeral=True
                )

        await interaction.response.send_message(
            f"💰 **{target.display_name} の残高**\n"
            f"所持金: **{row['balance']} {unit}**\n"
            f"チケット: **{tickets}枚**\n"
            f"ジャンボ: **{jumbo_count}口 🎫**",
            ephemeral=True
        )

    # ================================
    # /pay 送金（メモ対応）
    # ================================
    @app_commands.command(
        name="pay",
        description="指定ユーザーに通貨を送金します（メモ対応）"
    )
    @app_commands.describe(
        member="送金先のユーザー",
        amount="送金額（整数）",
        memo="任意のメモ（省略可）"
    )
    async def pay(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: int,
        memo: str | None = None
    ):
        bot = self.bot
        guild = interaction.guild
        sender = interaction.user

        if guild is None:
            return await interaction.response.send_message(
                "サーバー内でのみ使用できます。",
                ephemeral=True
            )

        if amount <= 0:
            return await interaction.response.send_message(
                "送金額は1以上を指定してください。",
                ephemeral=True
            )

        db = bot.db

        try:
            settings = await db.get_settings()
            unit = settings["currency_unit"]

            # 残高チェック
            sender_row = await db.get_user(str(sender.id), str(guild.id))
            if sender_row["balance"] < amount:
                return await interaction.response.send_message(
                    f"残高が足りません。\n現在: {sender_row['balance']} {unit}",
                    ephemeral=True
                )

            # 送金実行
            await db.remove_balance(str(sender.id), str(guild.id), amount)
            await db.add_balance(str(member.id), str(guild.id), amount)
        except Exception as e:
            print("pay error:", repr(e))
            if interaction.response.is_done():
                return await interaction.followup.send(
                    "内部エラーが発生しました。（pay）",
                    ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    "内部エラーが発生しました。（pay）",
                    ephemeral=True
                )

        # --- 返信メッセージ ---
        # 金額に応じてパネル色を決定
        if amount >= 1_000_000:
            color = 0xE74C3C  # 赤
        elif amount >= 500_000:
            color = 0xE67E22  # オレンジ
        elif amount >= 300_000:
            color = 0xF1C40F  # 黄色
        elif amount >= 100_000:
            color = 0x2ECC71  # 緑
        elif amount >= 10_000:
            color = 0x1ABC9C  # 水色
        else:
            color = 0x3498DB  # 青

        embed = discord.Embed(
            title="💸  送金完了！",
            description=(
                f"\n"
                f" **送金者**：{sender.mention}\n"
                f" **受取**：{member.mention}\n"
                f"\n"
            ),
            color=color
        )

        # 金額フィールド（見やすく太字）
        embed.add_field(
            name="  送金額",
            value=f"\n**{amount:,} {unit}**\n",
            inline=False
        )

        # メモ（任意）
        if memo:
            embed.add_field(
                name="📝  メモ",
                value=f"\n{memo}\n",
                inline=False
            )

        # サムネイル画像（右上に表示）
        embed.set_thumbnail(url="attachment://pay.png")

        # 画像ファイルの添付
        file = discord.File("pay.png", filename="pay.png")

        await interaction.response.send_message(
            embed=embed,
            file=file
        )
        # --- ログ ---
        try:
            sig = inspect.signature(log_pay)
            if "memo" in sig.parameters:
                await log_pay(
                    bot=bot,
                    settings=settings,
                    from_id=sender.id,
                    to_id=member.id,
                    amount=amount,
                    memo=memo,
                )
            else:
                await log_pay(
                    bot=bot,
                    settings=settings,
                    from_id=sender.id,
                    to_id=member.id,
                    amount=amount,
                )
        except Exception as e:
            print("log_pay error:", repr(e))


async def setup(bot: commands.Bot):
    """Cog を登録し、/bal と /pay を各ギルドに紐付ける"""
    cog = BalanceCog(bot)
    await bot.add_cog(cog)

    for cmd in cog.get_app_commands():
        for gid in getattr(bot, "GUILD_IDS", []):
            bot.tree.add_command(cmd, guild=discord.Object(id=gid))
