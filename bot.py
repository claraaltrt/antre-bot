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

# ==================================================
# TOKEN
# ==================================================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing.")

# ==================================================
# CONFIG
# ==================================================

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
LEVEL_CHANNEL_ID = cfg_int("level_channel_id")

VERIFY_EMOJI = CFG.get("verify_emoji", "🩸")
CREEPY_INTERVAL = int(CFG.get("creepy_interval_minutes", 240))
XP_COOLDOWN = int(CFG.get("xp_cooldown_seconds", 30))
LEVELS = CFG.get("levels", {})

# ==================================================
# INTENTS
# ==================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================================================
# DATA FILES
# ==================================================

XP_FILE = "xp_data.json"
WARNS_FILE = "warns.json"

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

xp_data = load_json(XP_FILE)
warns_data = load_json(WARNS_FILE)

last_xp_gain = {}
spam_tracker = defaultdict(list)

# ==================================================
# UTIL
# ==================================================

async def send_safe(channel_id, text):
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(text)

async def modlog(text):
    await send_safe(LOG_CHANNEL_ID, text)

def xp_needed(level):
    return 100 * level

def is_mod(member):
    return member.guild_permissions.manage_messages

# ==================================================
# EVENTS
# ==================================================

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

@bot.event
async def on_message_delete(message):
    if not message.guild or message.author.bot:
        return
    await modlog(f"🗑️ Message supprimé par {message.author}: {message.content[:200]}")

@bot.event
async def on_message_edit(before, after):
    if not before.guild or before.author.bot:
        return
    if before.content == after.content:
        return
    await modlog(
        f"✏️ Message modifié par {before.author}\n"
        f"Avant: {before.content[:200]}\n"
        f"Après: {after.content[:200]}"
    )

# ==================================================
# MESSAGE HANDLER (ANTI-SPAM + XP)
# ==================================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Anti-spam
    now_dt = datetime.utcnow()
    spam_tracker[message.author.id] = [
        t for t in spam_tracker[message.author.id]
        if now_dt - t < timedelta(seconds=5)
    ]
    spam_tracker[message.author.id].append(now_dt)

    if len(spam_tracker[message.author.id]) >= 5:
        await message.channel.send(f"🔇 {message.author.mention} ralentis...")
        spam_tracker[message.author.id] = []

    # XP
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

        save_json(XP_FILE, xp_data)

    await bot.process_commands(message)

# ==================================================
# LEVEL SYSTEM
# ==================================================

async def level_up(member, level):
    guild = member.guild
    level_channel = guild.get_channel(LEVEL_CHANNEL_ID)

    for lvl, role_id in LEVELS.items():
        role = guild.get_role(role_id)
        if role and role in member.roles:
            await member.remove_roles(role)

    if str(level) in LEVELS:
        role = guild.get_role(LEVELS[str(level)])
        if role:
            await member.add_roles(role)

    if level_channel:
        await level_channel.send(f"🏆 {member.mention} atteint le niveau {level} !")

# ==================================================
# MINI-JEU DOORS
# ==================================================

doors_sessions = {}

def new_session():
    return {"door": 1, "hp": 3, "gold": 0, "in_run": True}

@bot.command()
async def doorsstart(ctx):
    doors_sessions[str(ctx.author.id)] = new_session()
    await ctx.send("🚪 Run DOORS commencée ! Tape `!open`.")

@bot.command()
async def open(ctx):
    s = doors_sessions.get(str(ctx.author.id))
    if not s:
        return await ctx.send("Tape `!doorsstart` d'abord.")
    s["door"] += 1
    if random.random() < 0.3:
        await ctx.send("🚨 Rush apparaît ! Tape `!hide`.")
    else:
        await ctx.send(f"🚪 Porte {s['door']} ouverte.")

@bot.command()
async def hide(ctx):
    s = doors_sessions.get(str(ctx.author.id))
    if not s:
        return
    if random.random() < 0.7:
        await ctx.send("🪑 Tu te caches avec succès.")
    else:
        s["hp"] -= 1
        await ctx.send(f"💥 Touché ! ❤️ {s['hp']}")
        if s["hp"] <= 0:
            del doors_sessions[str(ctx.author.id)]
            await ctx.send("☠️ Game Over.")

# ==================================================
# COMMANDES MODERATION
# ==================================================

@bot.command()
async def warn(ctx, member: discord.Member, *, reason="Aucune raison"):
    if not is_mod(ctx.author):
        return await ctx.send("Permission refusée.")
    warns_data.setdefault(str(member.id), []).append(reason)
    save_json(WARNS_FILE, warns_data)
    await ctx.send(f"⚠️ {member} averti.")
    await modlog(f"WARN {member} par {ctx.author}: {reason}")

@bot.command()
async def warns(ctx, member: discord.Member):
    warns = warns_data.get(str(member.id), [])
    if not warns:
        return await ctx.send("Aucun warn.")
    await ctx.send("\n".join(warns))

@bot.command()
async def clear(ctx, amount: int = 10):
    if not is_mod(ctx.author):
        return
    deleted = await ctx.channel.purge(limit=amount+1)
    await ctx.send(f"{len(deleted)-1} messages supprimés.", delete_after=3)

# ==================================================
# COMMANDES BASE
# ==================================================

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong !")

@bot.command()
async def rank(ctx):
    uid = str(ctx.author.id)
    if uid not in xp_data:
        return await ctx.send("Pas encore d'XP.")
    await ctx.send(f"Niveau {xp_data[uid]['level']} | XP {xp_data[uid]['xp']}")

# ==================================================
# CREEPY LOOP
# ==================================================

CREEPY_LINES = [
    "🌑 Quelqu’un observe depuis l’ombre.",
    "👁️ Une présence approche.",
    "🩸 La porte 000 grince..."
]

async def creepy_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        if CREEPY_CHANNEL_ID:
            channel = bot.get_channel(CREEPY_CHANNEL_ID)
            if channel:
                await channel.send(random.choice(CREEPY_LINES))
        await asyncio.sleep(max(5, CREEPY_INTERVAL) * 60)

# ==================================================
# RUN
# ==================================================

bot.run(TOKEN)
