import os
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.gentenv("DISCORD_TOKEN")

if not TOKEN:
    print("Token not found in environnement")
    exit()

# =========
# Setup
# =========
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN manquant dans .env")

with open("config.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)

def cfg_int(k): return int(CFG.get(k, 0))

GUILD_ID = cfg_int("guild_id")
VERIFY_CHANNEL_ID = cfg_int("verify_channel_id")
VERIFY_MESSAGE_ID = cfg_int("verify_message_id")
VERIFIED_ROLE_ID = cfg_int("verified_role_id")
WELCOME_CHANNEL_ID = cfg_int("welcome_channel_id")
LOG_CHANNEL_ID = cfg_int("log_channel_id")
CREEPY_CHANNEL_ID = cfg_int("creepy_channel_id")

VERIFY_EMOJI = CFG.get("verify_emoji", "🩸")
CREEPY_INTERVAL_MIN = int(CFG.get("creepy_interval_minutes", 240))

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
    "🔦 Si tu entends ton nom en vocal… quitte immédiatement."
]

async def log(text: str):
    if not LOG_CHANNEL_ID:
        return
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        try:
            await ch.send(text)
        except:
            pass

# =========
# Events
# =========
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    bot.loop.create_task(creepy_loop())

@bot.event
async def on_member_join(member: discord.Member):
    if GUILD_ID and member.guild.id != GUILD_ID:
        return

    ch = bot.get_channel(WELCOME_CHANNEL_ID) if WELCOME_CHANNEL_ID else None
    if ch:
        try:
            await ch.send(
                f"🩸 {member.mention}… tu es entré dans **L’ANTRE DES DAMNÉS**.\n\n"
                f"Va dans <#{VERIFY_CHANNEL_ID}> et réagis avec {VERIFY_EMOJI}.\n"
                "🌑 Ne reste pas seul."
            )
        except:
            pass

    await log(f"📥 Arrivée : **{member}**")

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild:
        return
    if GUILD_ID and message.guild.id != GUILD_ID:
        return
    if not message.author or message.author.bot:
        return

    content = (message.content or "")[:180] or "*(vide ou embed)*"
    await log(f"🧾 Message supprimé dans {message.channel.mention} par **{message.author}** : {content}")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # uniquement ton serveur
    if GUILD_ID and payload.guild_id != GUILD_ID:
        return

    # uniquement le salon de validation
    if payload.channel_id != VERIFY_CHANNEL_ID:
        return

    # uniquement l'emoji
    if str(payload.emoji) != VERIFY_EMOJI:
        return

    # uniquement le message précis (recommandé)
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
        await log("⚠️ Rôle introuvable (verified_role_id).")
        return

    # évite de redonner le rôle
    if role in member.roles:
        return

    try:
        await member.add_roles(role, reason="Validation 🩸 accepte-ou-pars")
        await log(f"🩸 Validation : rôle **{role.name}** donné à **{member}**")
        try:
            await member.send("🩸 Pacte accepté. Bienvenue dans l’ombre.")
        except:
            pass
    except discord.Forbidden:
        await log("⚠️ Forbidden : vérifie Manage Roles + hiérarchie (rôle du bot au-dessus).")
    except Exception as e:
        await log(f"⚠️ Erreur add_roles: {e}")

# =========
# Creepy loop
# =========
async def creepy_loop():
    await bot.wait_until_ready()
    interval = max(5, CREEPY_INTERVAL_MIN) * 60
    while not bot.is_closed():
        ch = bot.get_channel(CREEPY_CHANNEL_ID) if CREEPY_CHANNEL_ID else None
        if ch:
            try:
                await ch.send(random.choice(CREEPY_LINES))
            except:
                pass
        await asyncio.sleep(interval)

# =========
# Commands (pas slash)
# =========
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
        "👁️ Quelqu’un… est déjà de l’autre côté."
    )

bot.run(TOKEN)



