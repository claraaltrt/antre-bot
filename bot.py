import os
import json
import random
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# Token + config
# =========================
load_dotenv()  # OK en local, ne gêne pas Railway
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing. Add it in Railway Variables or .env locally.")

CONFIG_PATH = "config.json"
if not os.path.exists(CONFIG_PATH):
    raise SystemExit("config.json not found (must be next to bot.py).")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CFG = json.load(f)

def cfg_int(key: str) -> int:
    try:
        return int(CFG.get(key, 0))
    except Exception:
        return 0

GUILD_ID = cfg_int("guild_id")
VERIFY_CHANNEL_ID = cfg_int("verify_channel_id")
VERIFY_MESSAGE_ID = cfg_int("verify_message_id")
VERIFIED_ROLE_ID = cfg_int("verified_role_id")
WELCOME_CHANNEL_ID = cfg_int("welcome_channel_id")
LOG_CHANNEL_ID = cfg_int("log_channel_id")
CREEPY_CHANNEL_ID = cfg_int("creepy_channel_id")

VERIFY_EMOJI = CFG.get("verify_emoji", "🩸")
CREEPY_INTERVAL_MIN = int(CFG.get("creepy_interval_minutes", 240))

# =========================
# Intents + bot
# =========================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

CREEPY_LINES = [
    "📡 Signal faible… quelqu’un respire derrière la porte.",
    "🌑 Ne regarde pas la liste des membres trop longtemps.",
    "👁️ Il y a un compte ici… qui n’appartient à personne.",
    "🩸 Une porte s’est ouverte. Personne ne l’a touchée.",
    "🔦 Si tu entends ton nom en vocal… quitte immédiatement.",
    "📡 Un souffle traverse les couloirs.",
    "🌑 Quelqu’un observe la porte 000.",
    "👁️ Ne fixe pas ton écran trop longtemps.",
    "🩸 Ils entendent quand tu ris.",
    "🔦 Si la lumière clignote… baisse le son."
]

# =========================
# Helpers
# =========================
async def send_safe(channel_id: int, text: str):
    if not channel_id:
        return
    try:
        ch = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        await ch.send(text)
    except Exception:
        pass

async def log(text: str):
    await send_safe(LOG_CHANNEL_ID, text)

# =========================
# Events
# =========================
@bot.event
async def on_ready():
    print(f"✅ Connected as {bot.user}")
    bot.loop.create_task(creepy_loop())

@bot.event
async def on_member_join(member: discord.Member):
    if GUILD_ID and member.guild.id != GUILD_ID:
        return

    await send_safe(
        WELCOME_CHANNEL_ID,
        f"🩸 {member.mention}… bienvenue dans **L’ANTRE DES DAMNÉS**.\n"
        f"Va dans <#{VERIFY_CHANNEL_ID}> et réagis avec {VERIFY_EMOJI}.\n"
        "🌑 Ne reste pas seul."
    )
    await log(f"📥 Join: **{member}**")

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild:
        return
    if GUILD_ID and message.guild.id != GUILD_ID:
        return
    if not message.author or message.author.bot:
        return

    content = (message.content or "")[:180] or "(empty/embed)"
    await log(f"🧾 Deleted in {message.channel.mention} by **{message.author}**: {content}")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # server check
    if GUILD_ID and payload.guild_id != GUILD_ID:
        return

    # validation channel check
    if payload.channel_id != VERIFY_CHANNEL_ID:
        return

    # emoji check
    if str(payload.emoji) != VERIFY_EMOJI:
        return

    # message check (recommended)
    if VERIFY_MESSAGE_ID and payload.message_id != VERIFY_MESSAGE_ID:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    role = guild.get_role(VERIFIED_ROLE_ID)
    if not role:
        await log("⚠️ Role not found (verified_role_id).")
        return

    if role in member.roles:
        return

    try:
        await member.add_roles(role, reason="Verification reaction")
        await log(f"🩸 Verified: **{member}** got role **{role.name}**")
        try:
            await member.send("🩸 Pacte accepté. Bienvenue dans l’ombre.")
        except Exception:
            pass
    except discord.Forbidden:
        await log("⚠️ Missing permission: Manage Roles / role hierarchy.")
    except Exception as e:
        await log(f"⚠️ Error add_roles: {e}")

# =========================
# Creepy loop
# =========================
async def creepy_loop():
    await bot.wait_until_ready()
    interval = max(5, CREEPY_INTERVAL_MIN) * 60
    while not bot.is_closed():
        if CREEPY_CHANNEL_ID:
            await send_safe(CREEPY_CHANNEL_ID, random.choice(CREEPY_LINES))
        await asyncio.sleep(interval)

# =========================
# Commands (classic)
# =========================
@bot.command()
async def session(ctx, minutes: int = 10):
    await ctx.send(
        f"🎙️ **Session horreur** dans **{minutes} minutes**.\n"
        "🔦 Préparez vos écouteurs.\n"
        "🌑 Ne restez pas seuls."
    )

@bot.command()
async def porte000(ctx):
    await ctx.send(
        "🚪 **Porte 000** détectée.\n"
        "📡 Signal instable…\n"
        "👁️ Quelqu’un est déjà de l’autre côté."
    )
    @bot.command()
async def ping(ctx):
    await ctx.send("🩸 Je suis là… et j’écoute.")

@bot.command()
async def night(ctx):
    await ctx.send("🌘 𝐋𝐀 𝐍𝐔𝐈𝐓 𝐒𝐀𝐍𝐒 𝐅𝐈𝐍 … approche.\n🔦 Restez groupés.")

@bot.command()
async def doors(ctx):
    await ctx.send(
        "🚪 **DOORS** — Conseils :\n"
        "• Écoute les sons (Rush/Ambush)\n"
        "• Cache-toi vite dès que ça clignote\n"
        "• Garde une lampe pour les couloirs\n"
        "• Ne panique pas… c’est là qu’ils te prennent."
    )

@bot.command()
async def mimic(ctx):
    await ctx.send(
        "🌲 **The Mimic** — Conseils :\n"
        "• Joue en équipe, annonce tout\n"
        "• Fais attention aux faux bruits\n"
        "• Ne cours pas au hasard\n"
        "• Si tu vois une silhouette immobile… recule."
    )

@bot.command()
async def intruder(ctx):
    await ctx.send(
        "📺 **The Intruder** — Règles :\n"
        "• Ferme les portes\n"
        "• Éteins quand il faut\n"
        "• Observe les signaux\n"
        "• Si l’écran se fige… il est proche."
    )

@bot.command()
async def aide(ctx):
    await ctx.send(
        "🕯️ **Commandes** :\n"
        "`!ping` `!night` `!doors` `!mimic` `!intruder` `!session 10` `!porte000`"
    )

# =========================
# Run
# =========================
bot.run(TOKEN)



