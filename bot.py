import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from db import Database

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot.GUILD_IDS = [
    1475448864122208350  # サーバーID
]

bot.db = Database()

@bot.event
async def on_ready():
    print(f"ログイン完了：{bot.user}")
    await bot.db.init_db()

    for gid in bot.GUILD_IDS:
        await bot.tree.sync(guild=discord.Object(id=gid))

async def load_cogs():

    extensions = [
        "cogs.balance",
        "cogs.admin",
        "cogs.hotel.setup",
    ]

    for ext in extensions:
        await bot.load_extension(ext)
        print(f"Cog loaded: {ext}")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

import asyncio
asyncio.run(main())