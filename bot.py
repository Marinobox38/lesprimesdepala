import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# ========== Flask Keep Alive ==========
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run).start()

# ========== Variables ==========
def must_get_env(var):
    value = os.getenv(var)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante : {var}")
    return value

TOKEN = must_get_env("token")
GUILD_ID = int(must_get_env("guildId"))
ADMIN_CHANNEL_ID = int(must_get_env("adminChannelId"))
FORM_SUBMIT_CHANNEL_ID = int(must_get_env("requestChannelId"))
PUBLIC_BOUNTY_CHANNEL_ID = 1402778898923651242
PUBLIC_ACCEPTED_BOUNTY_CHANNEL_ID = 1402779650421424168
STAFF_ROLE_ID = 1402780875694801007
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982
ADMIN_ROLE_ID = 1402780875694801007

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== On Ready ==========
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")

# ========== Logs ==========
async def log_action(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

# ========== Views ==========

class CloseTicketModal(discord.ui.Modal, title="Raison de fermeture du ticket"):
    raison = discord.ui.TextInput(label="Raison de la fermeture", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, ticket_channel):
        super().__init__()
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        # Log la raison
        await log_action(f"Ticket {self.ticket_channel.name} fermé par {interaction.user} avec raison : {self.raison.value}")
        # Envoie la raison dans le channel ticket avant suppression
        await self.ticket_channel.send(f"Ticket fermé par {interaction.user.mention}\n**Raison :** {self.raison.value}")
        await interaction.response.send_message("Ticket fermé. Ce salon sera supprimé dans 5 secondes.", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=5))
        await self.ticket_channel.delete()

class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel != self.ticket_channel:
            await interaction.response.send_message("Cette action ne peut être effectuée que dans le ticket concerné.", ephemeral=True)
            return
        modal = CloseTicketModal(self.ticket_channel)
        await interaction.response.send_modal(modal)

class PrimeValidationView(discord.ui.View):
    def __init__(self, author, author_name, prime_embed):
        super().__init__(timeout=None)
        self.author = author
        self.author_name = author_name
        self.prime_embed = prime_embed

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success, custom_id="accept_prime")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Envoie MP à l'auteur
        try:
            await self.author.send("✅ Votre prime a été acceptée et publiée publiquement !")
        except:
            pass
        # Envoie dans le salon public
        public_channel = bot.get_channel(PUBLIC_ACCEPTED_BOUNTY_CHANNEL_ID)
        if public_channel:
            view = PrimeClaimView(self.prime_embed)
            await public_channel.send(embed=self.prime_embed, view=view)
        await interaction.response.send_message("✅ Prime acceptée et publiée.", ephemeral=True)
        await interaction.message.delete()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="refuse_prime")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.author.send("❌ Votre prime a été refusée.")
        except:
            pass
        await interaction.response.send_message("⛔ Prime refusée.", ephemeral=True)
        await interaction.message.delete()

class PrimeClaimView(discord.ui.View):
    def __init__(self, prime_embed):
        super().__init__(timeout=None)
        self.prime_embed = prime_embed

    @discord.ui.button(label="J'ai tué la cible", style=discord.ButtonStyle.success, custom_id="claim_button")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        category = interaction.channel.category
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"signalement-{interaction.user.name}".lower(),
            overwrites=overwrites,
            category=category
        )
        await ticket_channel.send(
            f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime.\nMerci d'envoyer la preuve ici !",
            view=CloseTicketView(ticket_channel)
        )
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

class PrimeModal(discord.ui.Modal, title="Proposer une Prime"):
    pseudo = discord.ui.TextInput(label="Votre pseudo", max_length=32)
    cible = discord.ui.TextInput(label="Joueur visé", max_length=32)
    montant = discord.ui.TextInput(label="Montant de la prime")
    faction = discord.ui.TextInput(label="Votre faction", max_length=32)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="💰 Nouvelle Prime Proposée",
            description=(
                f"**Proposée par :** {self.pseudo.value}\n"
                f"**Cible :** {self.cible.value}\n"
                f"**Montant :** {self.montant.value}\n"
                f"**Faction :** {self.faction.value}"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Proposée par {interaction.user.display_name}")
        view = PrimeValidationView(interaction.user, self.pseudo.value, embed)
        # Envoi dans le salon de modération / validation des primes
        form_channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        if form_channel:
            await form_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Prime envoyée pour validation !", ephemeral=True)

class PrimeInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket_from_afficher")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        category = interaction.channel.category
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower(),
            overwrites=overwrites,
            category=category
        )
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — Nouveau ticket créé par {interaction.user.mention}", view=CloseTicketView(ticket_channel))
        await interaction.response.send_message(f"🎟️ Ticket créé : {ticket_channel.mention}", ephemeral=True)

class TicketDeployView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Créer un ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        category = interaction.channel.category
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower(),
            overwrites=overwrites,
            category=category
        )
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — Nouveau ticket créé par {interaction.user.mention}", view=CloseTicketView(ticket_channel))
        await interaction.response.send_message(f"🎟️ Ticket créé : {ticket_channel.mention}", ephemeral=True)

# ========== Commandes Slash ==========

@bot.tree.command(name="ticket-deploy", description="Déploie le message avec bouton pour créer un ticket", guild=discord.Object(id=GUILD_ID))
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Support / Tickets",
        description="Cliquez sur le bouton ci-dessous pour ouvrir un ticket et contacter le staff.",
        color=discord.Color.blue()
    )
    view = TicketDeployView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="prime", description="Proposer une prime", guild=discord.Object(id=GUILD_ID))
async def prime(interaction: discord.Interaction):
    modal = PrimeModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="afficher", description="Affiche une explication de la commande /prime avec bouton pour ouvrir un ticket", guild=discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Commande /prime",
        description="La commande `/prime` permet de créer une prime. Pour toute question ou problème, ouvre un ticket en cliquant sur le bouton ci-dessous.",
        color=discord.Color.green()
    )
    view = PrimeInfoView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="site", description="Affiche le lien du site des primes", guild=discord.Object(id=GUILD_ID))
async def site(interaction: discord.Interaction):
    await interaction.response.send_message("🌐 Voici le site des primes : https://lesprimesdepaladium.com", ephemeral=False)

@bot.tree.command(name="signaler", description="Signaler un joueur en ouvrant un ticket", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Le joueur à signaler")
async def signaler(interaction: discord.Interaction, user: discord.Member):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
        interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
    }
    category = interaction.channel.category
    ticket_channel = await interaction.guild.create_text_channel(
        name=f"signalement-{user.name}".lower(),
        overwrites=overwrites,
        category=category
    )
    await ticket_channel.send(
        f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a signalé {user.mention}. Vous pouvez discuter ici.",
        view=CloseTicketView(ticket_channel)
    )
    await interaction.response.send_message(f"✅ Ticket de signalement créé : {ticket_channel.mention}", ephemeral=True)

# ========== Commandes Modération ==========

def is_staff():
    def predicate(interaction: discord.Interaction):
        return STAFF_ROLE_ID in [role.id for role in interaction.user.roles]
    return app_commands.check(predicate)

@bot.tree.command(name="ban", description="Bannir un utilisateur temporairement ou définitivement", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à bannir", duration="Durée en minutes (0 = permanent)", reason="Raison du ban")
@is_staff()
async def ban(interaction: discord.Interaction, user: discord.Member, duration: int, reason: str):
    try:
        await user.ban(reason=reason)
        await log_action(f"{interaction.user} a banni {user} pour {duration} minutes. Raison: {reason}")
        await interaction.response.send_message(f"✅ {user} a été banni. Durée: {'permanente' if duration == 0 else f'{duration} minutes'}.", ephemeral=False)
        if duration > 0:
            # Unban après délai
            async def unban_task():
                await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(minutes=duration))
                await interaction.guild.unban(user)
                await log_action(f"Unban automatique de {user} après {duration} minutes.")
            bot.loop.create_task(unban_task())
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors du ban : {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à expulser", reason="Raison du kick")
@is_staff()
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):
    try:
        await user.kick(reason=reason)
        await log_action(f"{interaction.user} a expulsé {user}. Raison: {reason}")
        await interaction.response.send_message(f"✅ {user} a été expulsé.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors du kick : {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Avertir un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à avertir", reason="Raison de l'avertissement")
@is_staff()
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    try:
        await user.send(f"⚠️ Vous avez été averti par un membre du staff pour la raison suivante : {reason}")
        await log_action(f"{interaction.user} a averti {user}. Raison: {reason}")
        await interaction.response.send_message(f"✅ {user} a été averti par MP.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de l'avertissement : {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Mettre en sourdine un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à mute", duration="Durée en minutes (0 = permanent)", reason="Raison du mute")
@is_staff()
async def mute(interaction: discord.Interaction, user: discord.Member, duration: int, reason: str):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if mute_role is None:
        # Créer le rôle Muted si pas existant
        mute_role = await interaction.guild.create_role(name="Muted", reason="Création rôle mute")
        # Interdire parler et envoyer messages dans tous les channels
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False, add_reactions=False)
    try:
        await user.add_roles(mute_role, reason=reason)
        await log_action(f"{interaction.user} a mute {user} pour {duration} minutes. Raison: {reason}")
        await interaction.response.send_message(f"✅ {user} est mute.", ephemeral=True)
        if duration > 0:
            async def unmute_task():
                await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(minutes=duration))
                await user.remove_roles(mute_role, reason="Fin du mute automatique")
                await log_action(f"Unmute automatique de {user} après {duration} minutes.")
            bot.loop.create_task(unmute_task())
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors du mute : {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Retirer le mute d'un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à unmute")
@is_staff()
async def unmute(interaction: discord.Interaction, user: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if mute_role is None:
        await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
        return
    try:
        await user.remove_roles(mute_role, reason=f"Unmute demandé par {interaction.user}")
        await log_action(f"{interaction.user} a unmute {user}")
        await interaction.response.send_message(f"✅ {user} n'est plus mute.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors du unmute : {e}", ephemeral=True)

# ========== Envoi de message / embed ==========

@bot.tree.command(name="message", description="Envoyer un message au nom du bot", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(message="Message à envoyer")
@is_staff()
async def message(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(name="embed", description="Envoyer un embed au nom du bot", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(title="Titre de l'embed", description="Description de l'embed", color="Couleur hex (ex: #FF0000)")
@is_staff()
async def embed(interaction: discord.Interaction, title: str, description: str, color: str = "#00FF00"):
    try:
        color_int = int(color.lstrip("#"), 16)
        emb = discord.Embed(title=title, description=description, color=color_int)
        await interaction.response.send_message(embed=emb)
    except Exception as e:
        await interaction.response.send_message(f"Erreur de création d'embed : {e}", ephemeral=True)

# ========== Interactions boutons (pour créer ticket etc) ==========

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        if custom_id == "create_ticket_button" or custom_id == "open_ticket_from_afficher":
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True),
                interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
            }
            category = interaction.channel.category
            ticket_channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}".lower(),
                overwrites=overwrites,
                category=category
            )
            await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — Nouveau ticket créé par {interaction.user.mention}", view=CloseTicketView(ticket_channel))
            await interaction.response.send_message(f"🎟️ Ticket créé : {ticket_channel.mention}", ephemeral=True)

bot.run(TOKEN)
