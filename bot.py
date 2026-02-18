import os
import json
import random
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# TOKEN
# =========================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing.")

# =========================
# CONFIG
# =========================

with open("config.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)

def cfg_int(key):
    try:
        return int(CFG.get(key, 0))
    except:
        return 0

GUILD_ID = cfg_int("guild_id")
VERIFY_CHANNEL_ID = cfg_int("verify_channel_id")
VERIFY_MESSAGE_ID = cfg_int("verify_message_id")
VERIFIED_ROLE_ID = cfg_int("verified_role_id")
WELCOME_CHANNEL_ID = cfg_int("welcome_channel_id")
LOG_CHANNEL_ID = cfg_int("log_channel_id")
CREEPY_CHANNEL_ID = cfg_int("creepy_channel_id")

VERIFY_EMOJI = CFG.get("verify_emoji", "🩸")
CREEPY_INTERVAL = int(CFG.get("creepy_interval_minutes", 240))

# =========================
# INTENTS
# =========================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATA
# =========================

CREEPY_LINES = [
    "🌑 Quelqu’un observe depuis l’ombre.",
    "👁️ Ne fixe pas la liste des membres trop longtemps.",
    "🩸 Une porte vient de s’ouvrir.",
    "📡 Signal instable…",
    "🔦 Si la lumière clignote… baisse le son."
]

spam_tracker = defaultdict(list)

# =========================
# UTIL
# =========================

async def send_safe(channel_id, text):
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(text)
    except:
        pass

# =========================
# EVENTS
# =========================

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    bot.loop.create_task(creepy_loop())

@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return

    await send_safe(
        WELCOME_CHANNEL_ID,
        f"🩸 {member.mention} bienvenue dans **L’ANTRE DES DAMNÉS**.\n"
        f"Réagis dans <#{VERIFY_CHANNEL_ID}> avec {VERIFY_EMOJI}."
    )

@bot.event
async def on_message_delete(message):
    if not message.guild:
        return
    if message.author.bot:
        return

    await send_safe(
        LOG_CHANNEL_ID,
        f"🧾 Message supprimé par {message.author} : {message.content[:200]}"
    )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Anti spam simple (5 messages en 5 secondes)
    now = datetime.utcnow()
    spam_tracker[message.author.id] = [
        t for t in spam_tracker[message.author.id]
        if now - t < timedelta(seconds=5)
    ]
    spam_tracker[message.author.id].append(now)

    if len(spam_tracker[message.author.id]) >= 5:
        await message.channel.send(
            f"🔇 {message.author.mention} ralentis..."
        )
        spam_tracker[message.author.id] = []

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id != GUILD_ID:
        return

    if payload.channel_id != VERIFY_CHANNEL_ID:
        return

    if str(payload.emoji) != VERIFY_EMOJI:
        return

    if VERIFY_MESSAGE_ID and payload.message_id != VERIFY_MESSAGE_ID:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    role = guild.get_role(VERIFIED_ROLE_ID)

    if member and role:
        await member.add_roles(role)

# =========================
# CREEPY LOOP
# =========================

async def creepy_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        if CREEPY_CHANNEL_ID:
            channel = bot.get_channel(CREEPY_CHANNEL_ID)
            if channel:
                guild = bot.get_guild(GUILD_ID)
                members = guild.member_count if guild else "???"
                msg = random.choice(CREEPY_LINES)
                msg += f"\n⏳ {datetime.utcnow().strftime('%H:%M')} — 👥 {members} âmes"
                await channel.send(msg)

        await asyncio.sleep(max(5, CREEPY_INTERVAL) * 60)

# =========================
# COMMANDES
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong !")

@bot.command()
async def aide(ctx):
    await ctx.send("Menu d'aide")

@bot.command()
async def night(ctx):
    await ctx.send("La nuit tombe...")

@bot.command()
async def doors(ctx):
    await ctx.send("Conseils DOORS")

# =========================
# RUN
# =========================

bot.run(TOKEN)

