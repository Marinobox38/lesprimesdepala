import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import asyncio
import random

# === Flask Keep Alive ===
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run).start()

# === Variables ===
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
STAFF_ROLE_ID = 1402780875694801007  # Remplace par ton vrai ID staff
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# === Utilitaires ===

async def send_dm(user: discord.User, message: str):
    try:
        await user.send(message)
    except Exception:
        print(f"Impossible d'envoyer un MP à {user}")

async def log_action(guild: discord.Guild, message: str):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

# === Classes pour les Tickets ===

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

class SignalTicketView(discord.ui.View):
    def __init__(self, cible):
        super().__init__(timeout=None)
        self.cible = cible

    @discord.ui.button(label="Signaler la prime", style=discord.ButtonStyle.danger)
    async def signal(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            discord.utils.get(guild.roles, id=STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(f"signalement-{interaction.user.name}", overwrites=overwrites, category=category)
        view = CloseTicketView()
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime sur **{self.cible}**.\nMerci d'envoyer la preuve ici !", view=view)
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

# === Formulaire Prime ===

class BountyForm(discord.ui.Modal, title="Demande de prime"):
    cible = discord.ui.TextInput(label="Cible", placeholder="Nom de la cible", required=True, max_length=100)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, placeholder="Détails sur la prime", required=True)
    preuve = discord.ui.TextInput(label="Preuve (lien ou autre)", placeholder="Lien vers une preuve", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = guild.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("Le salon des primes n'a pas été trouvé.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Nouvelle prime sur {self.cible.value}", description=self.description.value, color=discord.Color.red())
        if self.preuve.value:
            embed.add_field(name="Preuve", value=self.preuve.value, inline=False)
        embed.set_footer(text=f"Demandé par {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        view = SignalTicketView(self.cible.value)

        # Mention du rôle avant l'embed
        await channel.send(f"<@&{PRIME_PING_ROLE_ID}>")
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Votre prime a bien été soumise !", ephemeral=True)

# === Commandes Slash ===

@bot.tree.command(name="prime", description="Faire une demande de prime")
async def prime(interaction: discord.Interaction):
    await interaction.response.send_modal(BountyForm())

@bot.tree.command(name="ticket-deploy", description="Déployer le message de création de ticket")
@commands.has_permissions(administrator=True)
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(title="Création de ticket", description=(
        "Pour toute demande ou signalement, utilisez le bouton ci-dessous.\n"
        "Merci de respecter les modérateurs et les règles du serveur."
    ), color=discord.Color.blue())
    view = TicketDeployView()
    await interaction.response.send_message(embed=embed, view=view)

class TicketDeployView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Créer un ticket", style=discord.ButtonStyle.primary)
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            discord.utils.get(guild.roles, id=STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)
        view = CloseTicketView()
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a ouvert un ticket.", view=view)
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

# === Validation prime (accept/refuse) ===

async def send_prime_response(user: discord.User, accepted: bool, details: str):
    status = "acceptée" if accepted else "refusée"
    try:
        await user.send(f"Votre demande de prime a été **{status}**.\nDétails : {details}")
    except Exception:
        print(f"Impossible d'envoyer le MP à {user} concernant la prime {status}.")

@bot.tree.command(name="accept-prime", description="Accepter une demande de prime")
@commands.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur ayant fait la demande", details="Détails de la validation")
async def accept_prime(interaction: discord.Interaction, user: discord.User, details: str):
    await send_prime_response(user, True, details)
    await interaction.response.send_message(f"Prime acceptée et utilisateur notifié.")

@bot.tree.command(name="refuse-prime", description="Refuser une demande de prime")
@commands.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur ayant fait la demande", details="Détails du refus")
async def refuse_prime(interaction: discord.Interaction, user: discord.User, details: str):
    await send_prime_response(user, False, details)
    await interaction.response.send_message(f"Prime refusée et utilisateur notifié.")

# === Commandes Modération ===

@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(membre="Le membre à bannir", raison="Raison du ban", duree="Durée en minutes (optionnel)")
@commands.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str, duree: int = None):
    try:
        await membre.ban(reason=raison)
        await interaction.response.send_message(f"{membre.mention} a été banni pour : {raison} (durée: {duree or 'permanente'})")

        msg = f"Vous avez été banni du serveur {interaction.guild.name}.\nRaison : {raison}\n"
        if duree:
            msg += f"Durée : {duree} minutes.\n"
            await asyncio.sleep(duree * 60)
            await interaction.guild.unban(membre)
            await interaction.channel.send(f"{membre.mention} a été débanni automatiquement après {duree} minutes.")
        await send_dm(membre, msg)

        # Log
        await log_action(interaction.guild, f"⚠️ {membre} banni par {interaction.user}. Raison : {raison}. Durée : {duree or 'permanente'}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du ban : {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(membre="Le membre à expulser", raison="Raison de l'expulsion")
@commands.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str):
    try:
        await membre.kick(reason=raison)
        await interaction.response.send_message(f"{membre.mention} a été expulsé pour : {raison}")
        await send_dm(membre, f"Vous avez été expulsé du serveur {interaction.guild.name}.\nRaison : {raison}")
        await log_action(interaction.guild, f"⚠️ {membre} expulsé par {interaction.user}. Raison : {raison}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'expulsion : {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Mute un membre")
@app_commands.describe(membre="Le membre à mute", duree="Durée du mute en minutes", raison="Raison du mute")
@commands.has_permissions(manage_messages=True)
async def mute(interaction: discord.Interaction, membre: discord.Member, duree: int, raison: str):
    try:
        mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if mute_role is None:
            mute_role = await interaction.guild.create_role(name="Muted", reason="Role pour mute")
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, speak=False, add_reactions=False)

        await membre.add_roles(mute_role, reason=raison)
        await interaction.response.send_message(f"{membre.mention} a été mute pour {duree} minutes pour : {raison}")
        await send_dm(membre, f"Vous avez été mute dans {interaction.guild.name} pour {duree} minutes.\nRaison : {raison}")

        await log_action(interaction.guild, f"🔇 {membre} mute par {interaction.user} pour {duree} minutes. Raison : {raison}")

        await asyncio.sleep(duree * 60)
        await membre.remove_roles(mute_role, reason="Fin du mute")
        await interaction.channel.send(f"{membre.mention} a été unmute après {duree} minutes.")

    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du mute : {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Unmute un membre")
@app_commands.describe(membre="Le membre à unmute")
@commands.has_permissions(manage_messages=True)
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    try:
        mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if mute_role is None:
            await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
            return
        await membre.remove_roles(mute_role, reason=f"Unmute par {interaction.user}")
        await interaction.response.send_message(f"{membre.mention} a été unmute.")
        await send_dm(membre, f"Vous avez été unmute dans {interaction.guild.name}.")
        await log_action(interaction.guild, f"🔈 {membre} unmute par {interaction.user}.")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'unmute : {e}", ephemeral=True)

# === Giveaways ===

giveaways = {}

class Giveaway:
    def __init__(self, channel, prize, duration_minutes, host):
        self.channel = channel
        self.prize = prize
        self.duration = duration_minutes * 60
        self.host = host
        self.message = None
        self.end_time = datetime.utcnow() + timedelta(seconds=self.duration)
        self.entries = set()
        self.task = None

    async def start(self):
        embed = discord.Embed(title="🎉 Giveaway !", description=f"Prix : {self.prize}\nTemps restant : {self.duration//60} minutes", color=discord.Color.green())
        embed.set_footer(text=f"Lancé par {self.host}", icon_url=self.host.avatar.url if self.host.avatar else None)
        self.message = await self.channel.send(embed=embed)
        await self.message.add_reaction("🎉")
        self.task = asyncio.create_task(self._countdown())

    async def _countdown(self):
        while True:
            remaining = (self.end_time - datetime.utcnow()).total_seconds()
            if remaining <= 0:
                await self.finish()
                break
            await asyncio.sleep(10)
            await self.update_embed(int(remaining))

    async def update_embed(self, seconds_left):
        if self.message:
            minutes, seconds = divmod(seconds_left, 60)
            embed = discord.Embed(title="🎉 Giveaway !", description=f"Prix : {self.prize}\nTemps restant : {minutes}m {seconds}s", color=discord.Color.green())
            embed.set_footer(text=f"Lancé par {self.host}", icon_url=self.host.avatar.url if self.host.avatar else None)
            await self.message.edit(embed=embed)

    async def finish(self):
        if self.message:
            if len(self.entries) == 0:
                await self.message.channel.send("Personne n'a participé au giveaway.")
                embed = discord.Embed(title="🎉 Giveaway terminé", description="Pas de participants.", color=discord.Color.red())
            else:
                winner_id = random.choice(list(self.entries))
                winner = self.channel.guild.get_member(winner_id)
                embed = discord.Embed(title="🎉 Giveaway terminé", description=f"Félicitations à {winner.mention} qui a gagné : {self.prize} !", color=discord.Color.gold())
                await self.message.channel.send(f"Félicitations {winner.mention} ! Tu as gagné le giveaway : {self.prize} !")
            await self.message.edit(embed=embed)
            giveaways.pop(self.message.id, None)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.id in giveaways:
        giveaway = giveaways[reaction.message.id]
        if str(reaction.emoji) == "🎉":
            giveaway.entries.add(user.id)

@bot.tree.command(name="giveaway-create", description="Créer un giveaway")
@commands.has_permissions(manage_guild=True)
@app_commands.describe(channel="Salon où lancer le giveaway", durée="Durée en minutes", prix="Le prix du giveaway")
async def giveaway_create(interaction: discord.Interaction, channel: discord.TextChannel, durée: int, prix: str):
    giveaway = Giveaway(channel, prix, durée, interaction.user)
    giveaways_channel = giveaways
    await giveaway.start()
    giveaways[giveaway.message.id] = giveaway
    await interaction.response.send_message(f"Giveaway lancé dans {channel.mention} pour {durée} minutes, prix : {prix}")

@bot.tree.command(name="giveaway-end", description="Terminer un giveaway")
@commands.has_permissions(manage_guild=True)
@app_commands.describe(message_id="ID du message giveaway")
async def giveaway_end(interaction: discord.Interaction, message_id: int):
    if message_id not in giveaways:
        await interaction.response.send_message("Giveaway introuvable.", ephemeral=True)
        return
    giveaway = giveaways[message_id]
    await giveaway.finish()
    await interaction.response.send_message("Giveaway terminé.")

@bot.tree.command(name="giveaway-reroll", description="Reroll un giveaway")
@commands.has_permissions(manage_guild=True)
@app_commands.describe(message_id="ID du message giveaway")
async def giveaway_reroll(interaction: discord.Interaction, message_id: int):
    if message_id not in giveaways:
        await interaction.response.send_message("Giveaway introuvable.", ephemeral=True)
        return
    giveaway = giveaways[message_id]
    if len(giveaway.entries) == 0:
        await interaction.response.send_message("Aucun participant pour reroll.", ephemeral=True)
        return
    winner_id = random.choice(list(giveaway.entries))
    winner = giveaway.channel.guild.get_member(winner_id)
    await giveaway.channel.send(f"Le nouveau gagnant du giveaway est {winner.mention} !")
    await interaction.response.send_message("Reroll effectué.")

# === Événement Ready ===
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")

bot.run(TOKEN)
