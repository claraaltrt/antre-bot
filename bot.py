import os
import json
import random
import asyncio
import time
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
XP_COOLDOWN = int(CFG.get("xp_cooldown_seconds", 30))

LEVELS = CFG.get("levels", {})

# =========================
# INTENTS
# =========================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATA FILES
# =========================

XP_FILE = "xp_data.json"

def load_xp():
    try:
        with open(XP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_xp(data):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

xp_data = load_xp()
last_xp_gain = {}
spam_tracker = defaultdict(list)

# =========================
# UTIL
# =========================

async def send_safe(channel_id, text):
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(text)

def xp_needed(level):
    return 100 * level

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
# MESSAGE EVENT (ANTI-SPAM + XP)
# =========================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Anti-spam (5 msg / 5 sec)
    now_dt = datetime.utcnow()
    spam_tracker[message.author.id] = [
        t for t in spam_tracker[message.author.id]
        if now_dt - t < timedelta(seconds=5)
    ]
    spam_tracker[message.author.id].append(now_dt)

    if len(spam_tracker[message.author.id]) >= 5:
        await message.channel.send(f"🔇 {message.author.mention} ralentis...")
        spam_tracker[message.author.id] = []

    # XP cooldown
    user_id = str(message.author.id)
    now = time.time()

    if user_id not in last_xp_gain or now - last_xp_gain[user_id] >= XP_COOLDOWN:
        last_xp_gain[user_id] = now

        if user_id not in xp_data:
            xp_data[user_id] = {"xp": 0, "level": 0}

        xp_data[user_id]["xp"] += random.randint(5, 15)

        level = xp_data[user_id]["level"]
        xp = xp_data[user_id]["xp"]

        if xp >= xp_needed(level + 1):
            xp_data[user_id]["level"] += 1
            await level_up(message.author, xp_data[user_id]["level"])

        save_xp(xp_data)

    await bot.process_commands(message)

# =========================
# LEVEL UP
# =========================

async def level_up(member, level):
    guild = member.guild
    level_channel = guild.get_channel(cfg_int("level_channel_id"))

    # Retirer anciens rôles
    for lvl, role_id in LEVELS.items():
        role = guild.get_role(role_id)
        if role and role in member.roles:
            await member.remove_roles(role)

    # Ajouter nouveau rôle
    if str(level) in LEVELS:
        role_id = LEVELS[str(level)]
        role = guild.get_role(role_id)
        if role:
            await member.add_roles(role)

    if level_channel:
        await level_channel.send(
            f"🏆 {member.mention} atteint le **niveau {level}** !"
        )

# =========================
# CREEPY LOOP
# =========================

CREEPY_LINES = [
    "🌑 Quelqu’un observe depuis l’ombre.",
    "👁️ Ne fixe pas la liste des membres.",
    "🩸 Une porte vient de s’ouvrir.",
    "📡 Signal instable...",
    "🔥 Si la lumière clignote… baisse le son."
]

async def creepy_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        if CREEPY_CHANNEL_ID:
            channel = bot.get_channel(CREEPY_CHANNEL_ID)
            if channel:
                msg = random.choice(CREEPY_LINES)
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
    await ctx.send("🕯️ !ping | !rank | !leaderboard | !night | !doors")

@bot.command()
async def night(ctx):
    await ctx.send("🌘 La Nuit Sans Fin approche...")

@bot.command()
async def doors(ctx):
    await ctx.send("🚪 Écoute les sons. Cache-toi vite.")

@bot.command()
async def rank(ctx):
    user_id = str(ctx.author.id)
    if user_id not in xp_data:
        await ctx.send("Tu n'as pas encore d'XP.")
        return

    lvl = xp_data[user_id]["level"]
    xp = xp_data[user_id]["xp"]

    embed = discord.Embed(
        title="🏆 Ton Rang",
        description=f"Niveau : **{lvl}**\nXP : **{xp}**",
        color=0x8B0000
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def leaderboard(ctx):
    if not xp_data:
        await ctx.send("Personne n'a encore d'XP.")
        return

    sorted_users = sorted(
        xp_data.items(),
        key=lambda x: x[1]["xp"],
        reverse=True
    )

    description = ""
    for i, (uid, data) in enumerate(sorted_users[:10], start=1):
        member = ctx.guild.get_member(int(uid))
        if member:
            description += f"**#{i}** {member.display_name} — Niveau {data['level']}\n"

    embed = discord.Embed(
        title="📊 Classement",
        description=description,
        color=0x8B0000
    )
    await ctx.send(embed=embed)

# =========================
# RUN
# =========================

bot.run(TOKEN)
