# bot.py — Version complète (XP+Levels + Économie + Vérif + Logs + Creepy + Anti-spam + DOORS mini-jeu + Modération warn)
# ✅ 1 seul on_message (TRÈS IMPORTANT)
# ✅ save_json NON async (corrige ton crash)
# ✅ config.json + xp_data.json + eco_data.json requis

import os
import json
import time
import random
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# ENV / TOKEN
# =========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing (.env).")

# =========================
# HELPERS JSON
# =========================
def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path: str, data):
    # écriture “safe”
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# =========================
# CONFIG
# =========================
CFG = load_json("config.json", {})

def cfg_int(key, fallback=0):
    try:
        return int(CFG.get(key, fallback))
    except:
        return fallback

GUILD_ID = cfg_int("guild_id")

VERIFY_CHANNEL_ID = cfg_int("verify_channel_id")
VERIFY_MESSAGE_ID = cfg_int("verify_message_id")
VERIFIED_ROLE_ID = cfg_int("verified_role_id")
VERIFY_EMOJI = CFG.get("verify_emoji", "🩸")

WELCOME_CHANNEL_ID = cfg_int("welcome_channel_id")
LOG_CHANNEL_ID = cfg_int("log_channel_id")

CREEPY_CHANNEL_ID = cfg_int("creepy_channel_id")
CREEPY_INTERVAL_MIN = int(CFG.get("creepy_interval_minutes", 240))

# Anti-spam
SPAM_MAX = int(CFG.get("spam_max_msgs", 6))
SPAM_WINDOW = int(CFG.get("spam_window_seconds", 5))
MUTE_MINUTES = int(CFG.get("mute_minutes", 2))
MUTED_ROLE_ID = cfg_int("muted_role_id")

# XP / Levels
XP_FILE = "xp_data.json"
LEVEL_CHANNEL_ID = cfg_int("level_channel_id")
XP_COOLDOWN = int(CFG.get("xp_cooldown_seconds", 30))
LEVELS_MAP = CFG.get("levels", {})  # ex: {"1": role_id, "5": role_id, ...}

# Économie
ECO_FILE = "eco_data.json"
ECO = CFG.get("economy", {})
CURRENCY_NAME = ECO.get("currency_name", "Sang")
MONEY_MIN = int(ECO.get("money_per_message_min", 1))
MONEY_MAX = int(ECO.get("money_per_message_max", 3))
DAILY_AMOUNT = int(ECO.get("daily_amount", 250))

# =========================
# INTENTS / BOT
# =========================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATA IN MEMORY
# =========================
xp_data = load_json(XP_FILE, {})        # { "user_id": {"xp":int,"level":int} }
eco_data = load_json(ECO_FILE, {})      # { "user_id": {"money":int,"last_daily": "ISO"} }

spam_tracker = defaultdict(list)        # user_id -> [timestamps]
last_xp_time = {}                      # user_id -> last_time
doors_sessions = {}                    # user_id -> session dict
warns = load_json("warns.json", {})    # { "guild_id": { "user_id": [ {by, reason, ts} ] } }

CREEPY_LINES = [
    "🌑 Quelqu’un observe depuis l’ombre.",
    "👁️ Ne fixe pas la liste des membres trop longtemps.",
    "🩸 Une porte vient de s’ouvrir.",
    "📡 Signal instable…",
    "🔦 Si la lumière clignote… baisse le son."
]

# =========================
# UTIL DISCORD
# =========================
async def send_safe(channel_id: int, text: str):
    if not channel_id:
        return
    ch = bot.get_channel(channel_id)
    if ch:
        try:
            await ch.send(text)
        except:
            pass

def now_utc():
    return datetime.now(timezone.utc)

def get_guild_only(ctx):
    if not ctx.guild:
        raise commands.NoPrivateMessage("Commande serveur uniquement.")
    return ctx.guild

# =========================
# XP / LEVEL HELPERS
# =========================
def xp_needed(next_level: int) -> int:
    # simple
    return 100 * next_level

async def apply_level_roles(member: discord.Member, new_level: int):
    guild = member.guild

    # retirer anciens rôles niveaux
    for lvl_str, role_id in LEVELS_MAP.items():
        role = guild.get_role(int(role_id))
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Level role update")
            except:
                pass

    # ajouter rôle si correspond
    role_id = LEVELS_MAP.get(str(new_level))
    if role_id:
        role = guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role, reason=f"Reached level {new_level}")
            except:
                pass

async def announce_level_up(member: discord.Member, new_level: int):
    if LEVEL_CHANNEL_ID:
        ch = member.guild.get_channel(LEVEL_CHANNEL_ID)
        if ch:
            await ch.send(f"🏆 {member.mention} vient d’atteindre le **niveau {new_level}** !")

# =========================
# ECONOMY HELPERS
# =========================
def ensure_user_eco(uid: str):
    if uid not in eco_data:
        eco_data[uid] = {"money": 0, "last_daily": None}

def ensure_user_xp(uid: str):
    if uid not in xp_data:
        xp_data[uid] = {"xp": 0, "level": 0}

# =========================
# CREEPY LOOP
# =========================
async def creepy_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if CREEPY_CHANNEL_ID:
                channel = bot.get_channel(CREEPY_CHANNEL_ID)
                if channel and GUILD_ID:
                    guild = bot.get_guild(GUILD_ID)
                    members = guild.member_count if guild else "???"
                    msg = random.choice(CREEPY_LINES)
                    msg += f"\n⏳ {now_utc().strftime('%H:%M')} — 👥 {members} âmes"
                    await channel.send(msg)
        except:
            pass

        await asyncio.sleep(max(5, CREEPY_INTERVAL_MIN) * 60)

# =========================
# EVENTS
# =========================
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    bot.loop.create_task(creepy_loop())

@bot.event
async def on_member_join(member: discord.Member):
    if GUILD_ID and member.guild.id != GUILD_ID:
        return
    await send_safe(
        WELCOME_CHANNEL_ID,
        f"🩸 {member.mention} bienvenue dans **L’ANTRE DES DAMNÉS**.\n"
        f"Réagis dans <#{VERIFY_CHANNEL_ID}> avec {VERIFY_EMOJI} pour te vérifier."
    )

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    await send_safe(
        LOG_CHANNEL_ID,
        f"🗑️ Message supprimé par {message.author.mention} dans <#{message.channel.id}> :\n"
        f"```{(message.content or '')[:500]}```"
    )

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
            await send_safe(LOG_CHANNEL_ID, f"✅ {member.mention} a été vérifié.")
        except:
            pass

# =========================
# DOORS MINI GAME
# =========================
@dataclass
class DoorsState:
    room: int = 0
    hp: int = 3
    hiding: bool = False
    started_at: float = 0.0

def doors_get(uid: int):
    s = doors_sessions.get(uid)
    if not s:
        return None
    return s

def doors_start(uid: int):
    doors_sessions[uid] = DoorsState(room=1, hp=3, hiding=False, started_at=time.time())
    return doors_sessions[uid]

def doors_end(uid: int):
    if uid in doors_sessions:
        del doors_sessions[uid]

# =========================
# ONE on_message (anti-spam + xp + economy + commands)
# =========================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return await bot.process_commands(message)

    # ---- Anti-spam ----
    uid = message.author.id
    now = now_utc()
    spam_tracker[uid] = [t for t in spam_tracker[uid] if (now - t) < timedelta(seconds=SPAM_WINDOW)]
    spam_tracker[uid].append(now)

    if len(spam_tracker[uid]) >= SPAM_MAX:
        # mute si possible
        if MUTED_ROLE_ID:
            role = message.guild.get_role(MUTED_ROLE_ID)
            if role:
                try:
                    await message.author.add_roles(role, reason="Anti-spam")
                    await message.channel.send(f"🛑 {message.author.mention} mute {MUTE_MINUTES} min (spam).")
                    # unmute auto
                    async def unmute_later(member, role_to_remove):
                        await asyncio.sleep(max(10, MUTE_MINUTES * 60))
                        try:
                            await member.remove_roles(role_to_remove, reason="Auto unmute")
                        except:
                            pass
                    bot.loop.create_task(unmute_later(message.author, role))
                except:
                    await message.channel.send(f"🛑 {message.author.mention} ralentis…")
        else:
            await message.channel.send(f"🛑 {message.author.mention} ralentis…")

        spam_tracker[uid] = []
        return await bot.process_commands(message)

    # ---- XP + Economy cooldown ----
    uid_str = str(uid)
    last = last_xp_time.get(uid_str, 0)
    now_ts = time.time()
    if now_ts - last >= XP_COOLDOWN:
        last_xp_time[uid_str] = now_ts

        # XP
        ensure_user_xp(uid_str)
        xp_gain = random.randint(5, 15)
        xp_data[uid_str]["xp"] += xp_gain

        level = int(xp_data[uid_str]["level"])
        xp = int(xp_data[uid_str]["xp"])
        if xp >= xp_needed(level + 1):
            xp_data[uid_str]["level"] = level + 1
            new_level = level + 1
            await apply_level_roles(message.author, new_level)
            await announce_level_up(message.author, new_level)

        # Economy
        ensure_user_eco(uid_str)
        gain = random.randint(MONEY_MIN, MONEY_MAX)
        eco_data[uid_str]["money"] += gain

        # Save
        save_json(XP_FILE, xp_data)
        save_json(ECO_FILE, eco_data)

    # ---- commands ----
    await bot.process_commands(message)

# =========================
# BASIC COMMANDS
# =========================
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong !")

@bot.command()
async def aide(ctx):
    await ctx.send(
        "📌 **Commandes**\n"
        "✅ !ping\n"
        "✅ !aide\n"
        "🩸 !rank\n"
        "📊 !leaderboard\n"
        "💰 !balance / !daily\n"
        "🚪 DOORS: !doorsstart / !open / !hide / !doorsquit\n"
        "🛡️ Modération: !warn / !warnings / !clearwarns\n"
    )

@bot.command()
async def night(ctx):
    await ctx.send("🌙 La nuit tombe…")

@bot.command()
async def doors(ctx):
    await ctx.send("🚪 Tape **!doorsstart** pour commencer le mini-jeu DOORS.")

# =========================
# XP COMMANDS
# =========================
@bot.command()
async def rank(ctx):
    uid = str(ctx.author.id)
    ensure_user_xp(uid)
    lvl = xp_data[uid]["level"]
    xp = xp_data[uid]["xp"]
    need = xp_needed(int(lvl) + 1)
    await ctx.send(f"🏆 {ctx.author.mention} — Niveau **{lvl}** | XP **{xp}/{need}**")

@bot.command()
async def leaderboard(ctx):
    # top 10 XP
    if not xp_data:
        return await ctx.send("📊 Aucun joueur en base pour le moment.")
    items = []
    for uid, d in xp_data.items():
        try:
            items.append((int(d.get("level", 0)), int(d.get("xp", 0)), int(uid)))
        except:
            pass
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = items[:10]

    lines = []
    for i, (lvl, xp, uid_int) in enumerate(top, start=1):
        member = ctx.guild.get_member(uid_int)
        name = member.display_name if member else f"User {uid_int}"
        lines.append(f"**{i}.** {name} — lvl {lvl} (xp {xp})")

    await ctx.send("📊 **Leaderboard**\n" + "\n".join(lines))

# =========================
# ECONOMY COMMANDS
# =========================
@bot.command(aliases=["bal"])
async def balance(ctx):
    uid = str(ctx.author.id)
    ensure_user_eco(uid)
    money = eco_data[uid]["money"]
    await ctx.send(f"💰 {ctx.author.mention} — **{money} {CURRENCY_NAME}**")

@bot.command()
async def daily(ctx):
    uid = str(ctx.author.id)
    ensure_user_eco(uid)

    last = eco_data[uid].get("last_daily")
    now = now_utc()

    if last:
        try:
            last_dt = datetime.fromisoformat(last)
        except:
            last_dt = None
        if last_dt and (now - last_dt) < timedelta(hours=24):
            remaining = timedelta(hours=24) - (now - last_dt)
            h = int(remaining.total_seconds() // 3600)
            m = int((remaining.total_seconds() % 3600) // 60)
            return await ctx.send(f"⏳ Déjà pris. Reviens dans **{h}h {m}m**.")

    eco_data[uid]["money"] += DAILY_AMOUNT
    eco_data[uid]["last_daily"] = now.isoformat()
    save_json(ECO_FILE, eco_data)
    await ctx.send(f"🎁 {ctx.author.mention} tu gagnes **{DAILY_AMOUNT} {CURRENCY_NAME}** (daily).")

# =========================
# DOORS COMMANDS
# =========================
@bot.command()
async def doorsstart(ctx):
    doors_start(ctx.author.id)
    await ctx.send(
        f"🚪 {ctx.author.mention} **DOORS** شروع!\n"
        f"Tu es dans la **Salle 1** | ❤️ 3\n"
        f"➡️ Utilise **!open** pour ouvrir une porte, **!hide** pour te cacher."
    )

@bot.command()
async def open(ctx):
    s = doors_get(ctx.author.id)
    if not s:
        return await ctx.send("🚪 Tu n’as pas de partie. Tape **!doorsstart**.")
    if s.hiding:
        s.hiding = False

    # événements random
    roll = random.random()

    # chance de monstre
    if roll < 0.22:
        # si caché => safe (mais là il vient d'open donc pas caché)
        s.hp -= 1
        if s.hp <= 0:
            doors_end(ctx.author.id)
            return await ctx.send(f"💀 {ctx.author.mention} **tu es mort** (Salle {s.room}). Tape !doorsstart.")
        return await ctx.send(f"👹 Un monstre surgit ! ❤️ -1 (reste {s.hp}). Essaie **!hide** vite !")

    # avance
    s.room += 1
    reward = random.randint(1, 4)
    uid = str(ctx.author.id)
    ensure_user_eco(uid)
    eco_data[uid]["money"] += reward
    save_json(ECO_FILE, eco_data)

    # win condition simple
    if s.room >= 20:
        bonus = 50
        eco_data[uid]["money"] += bonus
        save_json(ECO_FILE, eco_data)
        doors_end(ctx.author.id)
        return await ctx.send(f"🏁 {ctx.author.mention} tu as fini **DOORS** ! +{bonus} {CURRENCY_NAME}")

    await ctx.send(f"🚪 Porte ouverte → **Salle {s.room}** | +{reward} {CURRENCY_NAME}")

@bot.command()
async def hide(ctx):
    s = doors_get(ctx.author.id)
    if not s:
        return await ctx.send("🚪 Tu n’as pas de partie. Tape **!doorsstart**.")
    s.hiding = True
    await ctx.send(f"🫥 {ctx.author.mention} tu te caches… (Tape **!open** pour ressortir.)")

@bot.command()
async def doorsquit(ctx):
    s = doors_get(ctx.author.id)
    if not s:
        return await ctx.send("🚪 Aucune partie en cours.")
    doors_end(ctx.author.id)
    await ctx.send("🚪 Partie DOORS arrêtée.")

# =========================
# MODERATION — WARN
# =========================
def ensure_warn_guild(guild_id: int):
    gid = str(guild_id)
    if gid not in warns:
        warns[gid] = {}
    return warns[gid]

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Aucune raison"):
    get_guild_only(ctx)
    g = ensure_warn_guild(ctx.guild.id)
    uid = str(member.id)
    if uid not in g:
        g[uid] = []

    g[uid].append({
        "by": str(ctx.author.id),
        "reason": reason,
        "ts": now_utc().isoformat()
    })
    save_json("warns.json", warns)

    await ctx.send(f"⚠️ {member.mention} warn ✅ — **{reason}**")
    await send_safe(LOG_CHANNEL_ID, f"⚠️ WARN: {member} par {ctx.author} — {reason}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warnings(ctx, member: discord.Member):
    get_guild_only(ctx)
    g = ensure_warn_guild(ctx.guild.id)
    uid = str(member.id)
    lst = g.get(uid, [])
    if not lst:
        return await ctx.send(f"✅ {member.mention} n’a aucun warn.")

    lines = []
    for i, w in enumerate(lst[-10:], start=1):
        rid = w.get("reason", "—")
        ts = w.get("ts", "")
        lines.append(f"**{i}.** {rid} (`{ts}`)")
    await ctx.send(f"📌 Warns de {member.mention}:\n" + "\n".join(lines))

@bot.command()
@commands.has_permissions(administrator=True)
async def clearwarns(ctx, member: discord.Member):
    get_guild_only(ctx)
    g = ensure_warn_guild(ctx.guild.id)
    uid = str(member.id)
    g[uid] = []
    save_json("warns.json", warns)
    await ctx.send(f"🧹 Warns supprimés pour {member.mention}.")

# =========================
# ERROR HANDLER (pratique)
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send("⛔ Tu n’as pas la permission.")
    if isinstance(error, commands.NoPrivateMessage):
        return await ctx.send("⛔ Commande serveur uniquement.")
    await ctx.send(f"❌ Erreur: `{str(error)[:180]}`")

# =========================
# RUN
# =========================
bot.run(TOKEN)
