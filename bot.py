import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio

from db import Database

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1475448864122208350

# =========================
# Intents
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True

# =========================
# Bot
# =========================
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================
# DB
# =========================
bot.db = Database()

# =========================
# Ready
# =========================
@bot.event
async def on_ready():

    print("===== BOT START =====")

    print(f"Logged in as {bot.user}")

    # DB初期化
    await bot.db.init_db()

    print("Database Ready")

    # Slash同期
    guild = discord.Object(id=GUILD_ID)

    synced = await bot.tree.sync(guild=guild)

    print(f"Slash synced : {len(synced)} commands")

# =========================
# Cog読み込み
# =========================
async def load_cogs():

    extensions = [
        "cogs.init",
        "cogs.balance",
        "cogs.admin",
        "cogs.hotel.hotel_cog"
    ]

    for ext in extensions:

        try:
            await bot.load_extension(ext)
            print(f"Loaded {ext}")

        except Exception as e:
            print(f"Failed {ext} : {e}")

# =========================
# Main
# =========================
async def main():

    async with bot:

        await load_cogs()

        await bot.start(TOKEN)

# =========================
# Run
# =========================
if __name__ == "__main__":
    asyncio.run(main())
