import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
from flask import Flask
from threading import Thread
import os
from datetime import datetime, timedelta

# ====== Flask Keep Alive =======
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run).start()

# ====== Variables d'environnement =======
def must_get_env(var):
    value = os.getenv(var)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante : {var}")
    return value

TOKEN = must_get_env("token")
GUILD_ID = int(must_get_env("guildId"))

ADMIN_CHANNEL_ID = int(must_get_env("adminChannelId"))
FORM_SUBMIT_CHANNEL_ID = int(must_get_env("requestChannelId"))
PUBLIC_BOUNTY_CHANNEL_ID = int(must_get_env("publicChannelId"))

STAFF_ROLE_ID = 1402780875694801007  # Ton rôle admin/staff
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

GUILD = discord.Object(id=GUILD_ID)

# ====== On Ready =======
@bot.event
async def on_ready():
    await bot.tree.sync(guild=GUILD)
    print(f"\u2705 Connecté en tant que {bot.user}")

# ====== Commande ping simple =======
@bot.tree.command(name="ping", description="Répond pong")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# ====== Fonction utilitaire log =======
async def log_action(bot, message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

# ====== Commandes modération =======
def is_staff():
    async def predicate(interaction: discord.Interaction):
        member = interaction.user
        return any(role.id == STAFF_ROLE_ID for role in member.roles)
    return app_commands.check(predicate)

@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(member="Membre à bannir", reason="Raison du ban", duration="Durée (ex: 7d, 12h, ou vide pour permanent)")
@is_staff()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str, duration: str = None):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member.mention} a été banni pour : {reason}")
        dm_msg = f"Vous avez été banni sur {interaction.guild.name}.\nRaison : {reason}\n"
        if duration:
            dm_msg += f"Durée : {duration}\n"
        try:
            await member.send(dm_msg)
        except:
            pass
        await log_action(bot, f"🛑 {member} a été banni par {interaction.user} pour : {reason} (durée : {duration or 'permanent'})")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du ban : {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(member="Membre à expulser", reason="Raison du kick")
@is_staff()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member.mention} a été expulsé pour : {reason}")
        try:
            await member.send(f"Vous avez été expulsé sur {interaction.guild.name}.\nRaison : {reason}")
        except:
            pass
        await log_action(bot, f"👢 {member} a été expulsé par {interaction.user} pour : {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du kick : {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Mute un membre")
@app_commands.describe(member="Membre à mute", duration="Durée du mute (ex: 10m, 1h, 1d)", reason="Raison")
@is_staff()
async def mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    # Implémentation basique - nécessite rôle mute avec permissions et suppression du son
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        await interaction.response.send_message("Le rôle 'Muted' n'existe pas.", ephemeral=True)
        return
    await member.add_roles(mute_role, reason=reason)
    await interaction.response.send_message(f"{member.mention} a été mute pour {duration} : {reason}")
    try:
        await member.send(f"Vous avez été mute sur {interaction.guild.name} pour {duration}.\nRaison : {reason}")
    except:
        pass
    await log_action(bot, f"🔇 {member} a été mute par {interaction.user} pour {duration} : {reason}")

    # Gestion démute automatique après durée (simple)
    # Convertir duration en secondes
    seconds = 0
    unit = duration[-1]
    try:
        value = int(duration[:-1])
        if unit == "m":
            seconds = value * 60
        elif unit == "h":
            seconds = value * 3600
        elif unit == "d":
            seconds = value * 86400
        else:
            seconds = value  # secondes par défaut
    except:
        await interaction.channel.send("Format de durée invalide. Exemple: 10m, 1h, 1d")
        return

    async def unmute_later():
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=seconds))
        await member.remove_roles(mute_role, reason="Mute expiré")
        try:
            await member.send(f"Votre mute sur {interaction.guild.name} est terminé.")
        except:
            pass
        await log_action(bot, f"🔈 {member} a été unmute automatiquement.")

    bot.loop.create_task(unmute_later())

@bot.tree.command(name="unmute", description="Unmute un membre")
@app_commands.describe(member="Membre à unmute")
@is_staff()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        await interaction.response.send_message("Le rôle 'Muted' n'existe pas.", ephemeral=True)
        return
    await member.remove_roles(mute_role, reason=f"Unmute par {interaction.user}")
    await interaction.response.send_message(f"{member.mention} a été unmute.")
    await log_action(bot, f"🔈 {member} a été unmute par {interaction.user}.")
    try:
        await member.send(f"Vous avez été unmute sur {interaction.guild.name}.")
    except:
        pass

# ====== Commande Giveaways (exemple simple) =======
giveaways = {}  # Dict giveaway_id : {info}

@bot.tree.command(name="giveaway_create", description="Créer un giveaway")
@app_commands.describe(channel="Salon où envoyer le giveaway", prize="Nom du prix", duration="Durée (ex: 10m, 1h, 1d)")
@is_staff()
async def giveaway_create(interaction: discord.Interaction, channel: discord.TextChannel, prize: str, duration: str):
    # Convertir durée
    seconds = 0
    unit = duration[-1]
    try:
        value = int(duration[:-1])
        if unit == "m":
            seconds = value * 60
        elif unit == "h":
            seconds = value * 3600
        elif unit == "d":
            seconds = value * 86400
        else:
            await interaction.response.send_message("Unité de temps invalide (m,h,d).", ephemeral=True)
            return
    except:
        await interaction.response.send_message("Format de durée invalide. Exemple: 10m, 1h, 1d", ephemeral=True)
        return

    embed = discord.Embed(title="🎉 Giveaway !", description=f"Prix: **{prize}**\nRéagis avec 🎉 pour participer !", color=discord.Color.green())
    giveaway_msg = await channel.send(embed=embed)
    await giveaway_msg.add_reaction("🎉")

    end_time = datetime.utcnow() + timedelta(seconds=seconds)
    giveaways[giveaway_msg.id] = {
        "channel_id": channel.id,
        "prize": prize,
        "end_time": end_time,
        "message_id": giveaway_msg.id,
        "participants": set()
    }

    await interaction.response.send_message(f"Giveaway créé dans {channel.mention} pour {duration}.")

# Task qui vérifie les giveaways finis (à lancer dans on_ready)
@tasks.loop(seconds=30)
async def giveaway_check():
    to_remove = []
    for msg_id, data in giveaways.items():
        if datetime.utcnow() >= data["end_time"]:
            channel = bot.get_channel(data["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(msg_id)
                    # Récupérer les réactions 🎉
                    reaction = discord.utils.get(msg.reactions, emoji="🎉")
                    if reaction:
                        users = await reaction.users().flatten()
                        users = [u for u in users if not u.bot]
                        if users:
                            winner = users[0]  # Simple premier gagnant (améliorable)
                            embed = discord.Embed(title="🎉 Giveaway terminé !", description=f"Le gagnant est {winner.mention} !\nPrix: **{data['prize']}**", color=discord.Color.gold())
                            await channel.send(embed=embed)
                        else:
                            await channel.send("Personne n'a participé au giveaway.")
                    else:
                        await channel.send("Aucune réaction trouvée.")
                except:
                    pass
            to_remove.append(msg_id)

    for msg_id in to_remove:
        giveaways.pop(msg_id)

@giveaway_check.before_loop
async def before_giveaway():
    await bot.wait_until_ready()

giveaway_check.start()

# ====== Gestion des primes =======

class SignalPrimeView(View):
    def __init__(self, cible: str, author: discord.User):
        super().__init__(timeout=None)
        self.cible = cible
        self.author = author

    @discord.ui.button(label="J'ai tué", style=discord.ButtonStyle.success)
    async def killed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Merci d'avoir confirmé la prime.", ephemeral=True)

    @discord.ui.button(label="Signaler la prime", style=discord.ButtonStyle.danger)
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Créer un ticket pour staff
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(f"ticket-prime-{interaction.user.name}", overwrites=overwrites, category=None)
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime sur **{self.cible}**.\nMerci d'envoyer la preuve ici !")
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

# Commande pour publier une prime (exemple simplifié)
@bot.tree.command(name="publier_prime", description="Publier une nouvelle prime")
@app_commands.describe(description="Description de la prime")
@is_staff()
async def publier_prime(interaction: discord.Interaction, description: str):
    embed = discord.Embed(title="Nouvelle prime disponible !", description=description, color=discord.Color.red())
    # Mention rôle avant l'embed
    await interaction.channel.send(f"<@&{PRIME_PING_ROLE_ID}>")
    msg = await interaction.channel.send(embed=embed, view=SignalPrimeView(description, interaction.user))
    await interaction.response.send_message("Prime publiée !", ephemeral=True)

# Commande pour valider/refuser une prime (exemple)
@bot.tree.command(name="valider_prime", description="Valider ou refuser une prime")
@app_commands.describe(user="Auteur de la prime", accepted="Acceptée ou refusée", details="Détails")
@is_staff()
async def valider_prime(interaction: discord.Interaction, user: discord.User, accepted: bool, details: str):
    try:
        if accepted:
            await user.send(f"Votre prime a été **acceptée** ! Détails : {details}")
            await interaction.response.send_message(f"La prime de {user} a été acceptée.")
        else:
            await user.send(f"Votre prime a été **refusée**. Détails : {details}")
            await interaction.response.send_message(f"La prime de {user} a été refusée.")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'envoi du MP : {e}", ephemeral=True)

# ====== Commande /ticket-deploy =======
class CreateTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Créer un ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket"))

@bot.tree.command(name="ticket_deploy", description="Publier le message pour création de ticket")
@is_staff()
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(title="Besoin d'aide ?", description="Respectez le staff et créez un ticket si besoin.", color=discord.Color.blue())
    view = CreateTicketView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "create_ticket":
            guild = interaction.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
            await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a ouvert un ticket.")
            await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)

# ====== Lancement du bot =======
bot.run(TOKEN)
