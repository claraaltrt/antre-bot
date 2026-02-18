import os
import json
import random
import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv

# ======================================================
# ENV / TOKEN
# ======================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing in .env")

# ======================================================
# FILES
# ======================================================
CONFIG_FILE = "config.json"
XP_FILE = "xp_data.json"
ECO_FILE = "eco_data.json"

# ======================================================
# JSON UTIL (IMPORTANT: PAS async)
# ======================================================
def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ======================================================
# CONFIG
# ======================================================
CFG = load_json(CONFIG_FILE, {})

def cfg_int(key, default=0):
    try:
        return int(CFG.get(key, default))
    except:
        return default

GUILD_ID = cfg_int("guild_id")

VERIFY_CHANNEL_ID = cfg_int("verify_channel_id")
VERIFY_MESSAGE_ID = cfg_int("verify_message_id")
VERIFIED_ROLE_ID = cfg_int("verified_role_id")
WELCOME_CHANNEL_ID = cfg_int("welcome_channel_id")
LOG_CHANNEL_ID = cfg_int("log_channel_id")

CREEPY_CHANNEL_ID = cfg_int("creepy_channel_id")
VERIFY_EMOJI = CFG.get("verify_emoji", "🩸")
CREEPY_INTERVAL_MIN = int(CFG.get("creepy_interval_minutes", 240))

# Anti-spam / mute
SPAM_MAX = int(CFG.get("spam_max_msgs", 6))
SPAM_WINDOW = int(CFG.get("spam_window_seconds", 5))
MUTE_MINUTES = int(CFG.get("mute_minutes", 2))
MUTED_ROLE_ID = cfg_int("muted_role_id")

# Possessed (optionnel)
POSSESSED_ROLE_ID = cfg_int("possessed_role_id")
POSSESSED_INTERVAL_H = int(CFG.get("possessed_interval_hours", 24))
POSSESSED_DURATION_MIN = int(CFG.get("possessed_duration_minutes", 30))

# Immersif
IMMERSIVE_VOICE_IDS = CFG.get("immersive_voice_channel_ids", [])
IMMERSIVE_TEXT_CHANNEL_ID = cfg_int("immersive_text_channel_id")

# Levels / XP
LEVEL_CHANNEL_ID = cfg_int("level_channel_id")
XP_COOLDOWN = int(CFG.get("xp_cooldown_seconds", 30))
LEVEL_ROLES = CFG.get("levels", {})  # {"1": role_id, "5": role_id, ...}

# Economy
ECO = CFG.get("economy", {})
CURRENCY_NAME = ECO.get("currency_name", "Sang")
MONEY_MIN = int(ECO.get("money_per_message_min", 1))
MONEY_MAX = int(ECO.get("money_per_message_max", 3))
DAILY_AMOUNT = int(ECO.get("daily_amount", 250))

# ======================================================
# INTENTS / BOT
# ======================================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================================================
# DATA (runtime)
# ======================================================
xp_data = load_json(XP_FILE, {})
eco_data = load_json(ECO_FILE, {})

last_msg_time = {}  # cooldown XP/eco
spam_tracker = defaultdict(list)

# DOORS mini-game states
doors_sessions = {}  # user_id -> {"door": int, "hp": int, "coins": int, "hidden": bool}

CREEPY_LINES = [
    "🌑 Quelqu’un observe depuis l’ombre.",
    "👁️ Ne fixe pas la liste des membres trop longtemps.",
    "🩸 Une porte vient de s’ouvrir.",
    "📡 Signal instable…",
    "🔦 Si la lumière clignote… baisse le son."
]

# ======================================================
# HELPERS
# ======================================================
def utc_now():
    return datetime.now(timezone.utc)

async def get_channel(guild: discord.Guild, channel_id: int):
    if not guild or not channel_id:
        return None
    ch = guild.get_channel(channel_id)
    if ch:
        return ch
    try:
        return await guild.fetch_channel(channel_id)
    except:
        return None

async def log_to_channel(guild: discord.Guild, text: str):
    if not LOG_CHANNEL_ID:
        return
    ch = await get_channel(guild, LOG_CHANNEL_ID)
    if ch:
        try:
            await ch.send(text[:1900])
        except:
            pass

def xp_needed(level: int) -> int:
    # progression simple
    return 100 * max(1, level)

def ensure_user_xp(user_id: str):
    if user_id not in xp_data:
        xp_data[user_id] = {"xp": 0, "level": 0}

def ensure_user_eco(user_id: str):
    if user_id not in eco_data:
        eco_data[user_id] = {"money": 0, "last_daily": 0}

async def apply_level_roles(member: discord.Member, new_level: int):
    # retire anciens rôles niveau
    for lvl_str, role_id in LEVEL_ROLES.items():
        role = member.guild.get_role(int(role_id))
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Level update")
            except:
                pass

    # ajoute rôle si exact match
    role_id = LEVEL_ROLES.get(str(new_level))
    if role_id:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role, reason="Level reached")
            except:
                pass

async def send_levelup(member: discord.Member, new_level: int):
    if not LEVEL_CHANNEL_ID:
        return
    ch = await get_channel(member.guild, LEVEL_CHANNEL_ID)
    if ch:
        await ch.send(f"🏆 {member.mention} vient d'atteindre le **niveau {new_level}** !")

def doors_get(user_id: int):
    return doors_sessions.get(user_id)

def doors_new(user_id: int):
    doors_sessions[user_id] = {"door": 1, "hp": 3, "coins": 0, "hidden": False}
    return doors_sessions[user_id]

# ======================================================
# EVENTS
# ======================================================
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    bot.loop.create_task(creepy_loop())
    bot.loop.create_task(possessed_loop())

@bot.event
async def on_member_join(member: discord.Member):
    if GUILD_ID and member.guild.id != GUILD_ID:
        return

    if WELCOME_CHANNEL_ID:
        ch = await get_channel(member.guild, WELCOME_CHANNEL_ID)
        if ch:
            await ch.send(
                f"🩸 {member.mention} bienvenue dans **L’ANTRE DES DAMNÉS**.\n"
                f"Réagis dans <#{VERIFY_CHANNEL_ID}> avec {VERIFY_EMOJI} pour te vérifier."
            )

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    await log_to_channel(message.guild, f"🧾 Message supprimé par {message.author} : {message.content[:300]}")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Vérification par réaction
    if GUILD_ID and payload.guild_id != GUILD_ID:
        return
    if payload.channel_id != VERIFY_CHANNEL_ID:
        return
    if str(payload.emoji) != str(VERIFY_EMOJI):
        return
    if VERIFY_MESSAGE_ID and payload.message_id != VERIFY_MESSAGE_ID:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    role = guild.get_role(VERIFIED_ROLE_ID)
    if role:
        try:
            await member.add_roles(role, reason="Verification reaction")
            await log_to_channel(guild, f"✅ {member} vérifié (role ajouté).")
        except:
            pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return

    # 1) Anti-spam simple
    now_dt = utc_now()
    user_times = spam_tracker[message.author.id]
    user_times[:] = [t for t in user_times if (now_dt - t) < timedelta(seconds=SPAM_WINDOW)]
    user_times.append(now_dt)

    if len(user_times) >= SPAM_MAX:
        await message.channel.send(f"⚠️ {message.author.mention} ralentis… (anti-spam)")
        user_times.clear()

        # mute si rôle configuré
        if MUTED_ROLE_ID:
            role = message.guild.get_role(MUTED_ROLE_ID)
            if role:
                try:
                    await message.author.add_roles(role, reason="Anti-spam mute")
                    await log_to_channel(message.guild, f"🔇 {message.author} mute {MUTE_MINUTES} min (spam).")
                    await asyncio.sleep(max(1, MUTE_MINUTES) * 60)
                    await message.author.remove_roles(role, reason="Mute expired")
                except:
                    pass

        await bot.process_commands(message)
        return

    # 2) XP + ECONOMY cooldown
    uid = str(message.author.id)
    now = time.time()
    last = last_msg_time.get(uid, 0)
    if now - last >= XP_COOLDOWN:
        last_msg_time[uid] = now

        # XP
        ensure_user_xp(uid)
        gain_xp = random.randint(5, 15)
        xp_data[uid]["xp"] += gain_xp

        # Level-up check
        cur_level = int(xp_data[uid]["level"])
        cur_xp = int(xp_data[uid]["xp"])
        if cur_xp >= xp_needed(cur_level + 1):
            xp_data[uid]["level"] = cur_level + 1
            new_level = cur_level + 1
            await apply_level_roles(message.author, new_level)
            await send_levelup(message.author, new_level)

        save_json(XP_FILE, xp_data)

        # Economy
        ensure_user_eco(uid)
        money_gain = random.randint(MONEY_MIN, MONEY_MAX)
        eco_data[uid]["money"] += money_gain
        save_json(ECO_FILE, eco_data)

    # 3) commandes
    await bot.process_commands(message)

# ======================================================
# BACKGROUND LOOPS
# ======================================================
async def creepy_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        if CREEPY_CHANNEL_ID and GUILD_ID:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                ch = await get_channel(guild, CREEPY_CHANNEL_ID)
                if ch:
                    members = guild.member_count
                    msg = random.choice(CREEPY_LINES)
                    msg += f"\n⏳ {utc_now().strftime('%H:%M')} — 👥 {members} âmes"
                    try:
                        await ch.send(msg)
                    except:
                        pass
        await asyncio.sleep(max(5, CREEPY_INTERVAL_MIN) * 60)

async def possessed_loop():
    # optionnel: donne un rôle "possessed" à quelqu’un de temps en temps
    await bot.wait_until_ready()
    while not bot.is_closed():
        if GUILD_ID and POSSESSED_ROLE_ID:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                role = guild.get_role(POSSESSED_ROLE_ID)
                if role:
                    members = [m for m in guild.members if not m.bot]
                    if members:
                        victim = random.choice(members)
                        try:
                            await victim.add_roles(role, reason="Possessed event")
                            await log_to_channel(guild, f"🩸 {victim} est possédé pendant {POSSESSED_DURATION_MIN} min.")
                            await asyncio.sleep(max(1, POSSESSED_DURATION_MIN) * 60)
                            await victim.remove_roles(role, reason="Possessed expired")
                        except:
                            pass
        await asyncio.sleep(max(1, POSSESSED_INTERVAL_H) * 3600)

# ======================================================
# COMMANDES BASE
# ======================================================
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong !")

@bot.command()
async def aide(ctx):
    await ctx.send(
        "📜 **Commandes**\n"
        "✅ !ping\n"
        "🏆 !rank\n"
        "📊 !leaderboard\n"
        f"💰 !money / !daily (monnaie: {CURRENCY_NAME})\n"
        "🎮 DOORS: !doorsstart / !open / !hide / !doorsstop\n"
    )

# ======================================================
# RANK / LEADERBOARD / PROFILE
# ======================================================
@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    ensure_user_xp(uid)
    ensure_user_eco(uid)
    lvl = xp_data[uid]["level"]
    xp = xp_data[uid]["xp"]
    money = eco_data[uid]["money"]
    need = xp_needed(int(lvl) + 1)

    await ctx.send(
        f"🏆 **Profil de {member.display_name}**\n"
        f"• Niveau: **{lvl}**\n"
        f"• XP: **{xp} / {need}**\n"
        f"• {CURRENCY_NAME}: **{money}**"
    )

@bot.command()
async def leaderboard(ctx):
    # top 10 niveau/xp
    items = []
    for uid, d in xp_data.items():
        try:
            items.append((int(d.get("level", 0)), int(d.get("xp", 0)), int(uid)))
        except:
            pass
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = items[:10]

    lines = ["📊 **Leaderboard (Top 10)**"]
    for i, (lvl, xp, uid_int) in enumerate(top, start=1):
        member = ctx.guild.get_member(uid_int)
        name = member.display_name if member else str(uid_int)
        lines.append(f"**{i}.** {name} — lvl **{lvl}** (xp {xp})")

    await ctx.send("\n".join(lines))

# ======================================================
# ECONOMIE
# ======================================================
@bot.command()
async def money(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    ensure_user_eco(uid)
    await ctx.send(f"💰 {member.mention} a **{eco_data[uid]['money']} {CURRENCY_NAME}**.")

@bot.command()
async def daily(ctx):
    uid = str(ctx.author.id)
    ensure_user_eco(uid)
    now = int(time.time())
    last = int(eco_data[uid].get("last_daily", 0))

    # 24h
    if now - last < 24 * 3600:
        remaining = (24 * 3600) - (now - last)
        h = remaining // 3600
        m = (remaining % 3600) // 60
        await ctx.send(f"⏳ Tu as déjà pris ton daily. Reviens dans **{h}h {m}m**.")
        return

    eco_data[uid]["money"] += DAILY_AMOUNT
    eco_data[uid]["last_daily"] = now
    save_json(ECO_FILE, eco_data)
    await ctx.send(f"🎁 Daily: +**{DAILY_AMOUNT} {CURRENCY_NAME}** pour {ctx.author.mention} !")

# ======================================================
# DOORS MINI-JEU
# ======================================================
@bot.command()
async def doorsstart(ctx):
    s = doors_new(ctx.author.id)
    await ctx.send(
        f"🎮 **DOORS** démarré pour {ctx.author.mention} !\n"
        f"🚪 Porte: **{s['door']}** | ❤️ Vies: **{s['hp']}** | 💰 {CURRENCY_NAME}: **{s['coins']}**\n"
        f"Commandes: **!open**, **!hide**, **!doorsstop**"
    )

@bot.command()
async def doorsstop(ctx):
    if ctx.author.id in doors_sessions:
        del doors_sessions[ctx.author.id]
        await ctx.send("🛑 Session DOORS arrêtée.")
    else:
        await ctx.send("ℹ️ Tu n'as pas de session DOORS active. Fais **!doorsstart**.")

@bot.command()
async def hide(ctx):
    s = doors_get(ctx.author.id)
    if not s:
        await ctx.send("ℹ️ Lance d'abord **!doorsstart**.")
        return
    s["hidden"] = True
    await ctx.send("🕳️ Tu te caches… (prochaine porte, tu auras plus de chances de survivre)")

@bot.command()
async def open(ctx):
    s = doors_get(ctx.author.id)
    if not s:
        await ctx.send("ℹ️ Lance d'abord **!doorsstart**.")
        return

    door = s["door"]
    danger = random.random()

    # bonus si caché
    if s["hidden"]:
        danger -= 0.20
        s["hidden"] = False

    # évènement
    if danger < 0.25:
        # loot
        gain = random.randint(5, 25)
        s["coins"] += gain
        s["door"] += 1
        await ctx.send(f"🎁 Porte {door} ouverte ! Tu trouves **+{gain} {CURRENCY_NAME}**. (➡️ Porte {s['door']})")
    elif danger < 0.80:
        # safe
        s["door"] += 1
        await ctx.send(f"🚪 Porte {door} ouverte… rien à signaler. (➡️ Porte {s['door']})")
    else:
        # monster
        s["hp"] -= 1
        if s["hp"] <= 0:
            await ctx.send(f"💀 **MONSTRE !** Tu es mort à la porte **{door}**… Fin de partie.")
            # on crédite l'éco avec les coins gagnés
            uid = str(ctx.author.id)
            ensure_user_eco(uid)
            eco_data[uid]["money"] += s["coins"]
            save_json(ECO_FILE, eco_data)
            del doors_sessions[ctx.author.id]
            return
        await ctx.send(f"👹 **MONSTRE !** Tu perds 1 vie. ❤️ Vies restantes: **{s['hp']}** (Porte {door})")

# ======================================================
# RUN
# ======================================================
bot.run(TOKEN)
