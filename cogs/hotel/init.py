import discord
from .hotel_cog import HotelCog

async def setup(bot):
    cog = HotelCog(bot)
    await bot.add_cog(cog)

    # 指定ギルド同期
    if hasattr(bot, "GUILD_IDS"):
        for cmd in cog.get_app_commands():
            for gid in bot.GUILD_IDS:
                bot.tree.add_command(cmd, guild=discord.Object(id=gid))

    print("🏨 Hotel module loaded.")
