import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import asyncio

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run).start()

def must_get_env(var):
    value = os.getenv(var)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante : {var}")
    return value

TOKEN = must_get_env("token")
GUILD_ID = int(must_get_env("guildId"))

# Channels & Roles (à adapter)
WELCOME_CHANNEL_ID = 1403090073746014210
PUBLIC_BOUNTY_CHANNEL_ID = 1402779650421424168
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982
STAFF_ROLE_ID = 1402780875694801007
ADMIN_ROLE_ID = 1402780875694801007
REQUEST_CHANNEL_ID = 1402778898923651242  # salon des propositions primes
TICKET_CATEGORY_ID = None  # À définir si tu veux organiser les tickets dans une catégorie spécifique

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

welcome_messages = [
    "Bienvenue sur le serveur !",
    "Salut et bienvenue, amuse-toi bien !",
    "Un nouveau membre parmi nous, bienvenue !",
    "Heureux de te voir ici !",
    "Bienvenue, prêt à relever des défis ?"
]
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")
    check_giveaways.start()  # démarre la tâche de vérification des giveaways

@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        message = random.choice(welcome_messages)
        await channel.send(f"{message} {member.mention}")
    try:
        dm_message = (
            f"Bonjour {member.name} ! 👋\n\n"
            "Bienvenue sur notre serveur ! Ici, tu pourras participer à nos primes, ouvrir des tickets pour le support, "
            "et bien plus encore.\n"
            "N'hésite pas à lire les règles et à demander si tu as besoin d'aide. Bon séjour parmi nous ! 😊"
        )
        await member.send(dm_message)
    except discord.Forbidden:
        pass

async def log_action(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id in (STAFF_ROLE_ID, ADMIN_ROLE_ID) for role in interaction.user.roles):
            await interaction.response.send_message("❌ Vous n'avez pas la permission de fermer ce ticket.", ephemeral=True)
            return

        modal = CloseTicketModal(self.ticket_channel, interaction.user)
        await interaction.response.send_modal(modal)

class CloseTicketModal(discord.ui.Modal, title="Raison de la fermeture du ticket"):
    raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, ticket_channel, closer):
        super().__init__()
        self.ticket_channel = ticket_channel
        self.closer = closer

    async def on_submit(self, interaction: discord.Interaction):
        await log_action(f"Ticket {self.ticket_channel.name} fermé par {self.closer} pour la raison : {self.raison.value}")
        await interaction.response.send_message(f"Ticket fermé. Raison : {self.raison.value}", ephemeral=True)
        await self.ticket_channel.delete()
class PrimeClaimView(discord.ui.View):
    def __init__(self, cible):
        super().__init__(timeout=None)
        self.cible = cible

    @discord.ui.button(label="J'ai tué la cible", style=discord.ButtonStyle.success, custom_id="claim_button")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        category = None
        if TICKET_CATEGORY_ID:
            category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"signalement-{interaction.user.name}",
            overwrites=overwrites,
            category=category
        )
        await ticket_channel.send(
            f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame la prime sur **{self.cible}**.\n"
            f"Merci d'envoyer la preuve ici !",
            view=CloseTicketView(ticket_channel)
        )
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

class PrimeValidationView(discord.ui.View):
    def __init__(self, author, embed, pseudo, cible, montant, faction):
        super().__init__(timeout=None)
        self.author = author
        self.embed = embed
        self.pseudo = pseudo
        self.cible = cible
        self.montant = montant
        self.faction = faction

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success, custom_id="prime_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.author.send(f"✅ Votre prime de {self.montant} pour la cible {self.cible} a été acceptée et publiée publiquement !")
        except discord.Forbidden:
            pass

        public_channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        if public_channel:
            view = PrimeClaimView(self.cible)
            embed_public = discord.Embed(
                title="💰 Prime publiée",
                description=(
                    f"**Proposée par :** {self.pseudo}\n"
                    f"**Cible :** {self.cible}\n"
                    f"**Montant :** {self.montant}\n"
                    f"**Faction :** {self.faction}"
                ),
                color=discord.Color.green()
            )
            embed_public.set_footer(text=f"Proposée par {self.pseudo}")

            class ReportPrimeView(discord.ui.View):
                @discord.ui.button(label="Signaler la prime", style=discord.ButtonStyle.secondary, custom_id="report_prime")
                async def report_prime(self, interaction2: discord.Interaction, button2: discord.ui.Button):
                    overwrites = {
                        interaction2.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        interaction2.user: discord.PermissionOverwrite(view_channel=True),
                        interaction2.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
                    }
                    category = None
                    if TICKET_CATEGORY_ID:
                        category = interaction2.guild.get_channel(TICKET_CATEGORY_ID)
                    ticket_channel = await interaction2.guild.create_text_channel(
                        name=f"signalement-prime-{interaction2.user.name}",
                        overwrites=overwrites,
                        category=category
                    )
                    await ticket_channel.send(
                        f"<@&{STAFF_ROLE_ID}> — {interaction2.user.mention} signale la prime sur **{self.cible}**.\n"
                        f"Merci de détailler le problème ici !",
                        view=CloseTicketView(ticket_channel)
                    )
                    await interaction2.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

            await public_channel.send(f"<@&{PRIME_PING_ROLE_ID}>", embed=embed_public, view=ReportPrimeView())
        else:
            await interaction.response.send_message("❌ Le canal public des primes n'a pas été trouvé.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Prime acceptée et publiée.", ephemeral=True)
        await interaction.message.delete()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="prime_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.author.send(f"❌ Votre prime de {self.montant} pour la cible {self.cible} a été refusée.")
        except discord.Forbidden:
            pass
        await interaction.response.send_message("❌ Prime refusée et auteur prévenu.", ephemeral=True)
        await interaction.message.delete()
@bot.tree.command(name="prime", description="Proposer une prime", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    pseudo="Le pseudo du joueur proposant la prime",
    cible="La cible de la prime",
    montant="Le montant proposé pour la prime",
    faction="La faction concernée"
)
async def prime(interaction: discord.Interaction, pseudo: str, cible: str, montant: str, faction: str):
    if interaction.channel.id != REQUEST_CHANNEL_ID:
        await interaction.response.send_message(f"❌ Cette commande doit être utilisée dans le canal <#{REQUEST_CHANNEL_ID}>.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Proposition de prime",
        description=(
            f"**Proposée par :** {pseudo}\n"
            f"**Cible :** {cible}\n"
            f"**Montant :** {montant}\n"
            f"**Faction :** {faction}"
        ),
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Proposée par {pseudo}")

    view = PrimeValidationView(interaction.user, embed, pseudo, cible, montant, faction)
    request_channel = bot.get_channel(REQUEST_CHANNEL_ID)
    if request_channel:
        await request_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Votre prime a été envoyée au staff pour validation.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Impossible de trouver le salon de propositions.", ephemeral=True)
# Commande /ticket-deploy pour envoyer message avec bouton création ticket
class TicketDeployView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Créer un ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        category = None
        if TICKET_CATEGORY_ID:
            category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            category=category
        )
        await ticket_channel.send(
            f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a ouvert un ticket.",
            view=CloseTicketView(ticket_channel)
        )
        await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)

@bot.tree.command(name="ticket-deploy", description="Déployer le message pour créer des tickets", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Support - Création de ticket",
        description="Pour obtenir de l'aide ou signaler un problème, cliquez sur le bouton ci-dessous pour créer un ticket.",
        color=discord.Color.orange()
    )
    view = TicketDeployView()
    request_channel = bot.get_channel(REQUEST_CHANNEL_ID)
    if request_channel:
        await request_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Message de création de ticket envoyé.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Impossible de trouver le salon de propositions.", ephemeral=True)

# Commande /ticket (ouvre un ticket) - accessible en serveur uniquement
@bot.tree.command(name="ticket", description="Ouvrir un ticket pour le support", guild=discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
        interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
    }
    category = None
    if TICKET_CATEGORY_ID:
        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
    ticket_channel = await interaction.guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        overwrites=overwrites,
        category=category
    )
    await ticket_channel.send(
        f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a ouvert un ticket.",
        view=CloseTicketView(ticket_channel)
    )
    await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)
# Partie 6 : Gestion des commandes modération (ban, kick, mute, unmute)

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member} a été banni. Raison : {reason}")
        await member.send(f"Vous avez été banni du serveur. Raison : {reason}")
        log_channel = bot.get_channel(1403052907364093982)  # ID du salon logs
        if log_channel:
            await log_channel.send(f"{member} a été banni par {ctx.author}. Raison : {reason}")
    except Exception as e:
        await ctx.send(f"Erreur lors du ban : {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member} a été expulsé. Raison : {reason}")
        await member.send(f"Vous avez été expulsé du serveur. Raison : {reason}")
        log_channel = bot.get_channel(1403052907364093982)
        if log_channel:
            await log_channel.send(f"{member} a été expulsé par {ctx.author}. Raison : {reason}")
    except Exception as e:
        await ctx.send(f"Erreur lors de l'expulsion : {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def mute(ctx, member: discord.Member):
    try:
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            # Création du rôle si il n'existe pas
            mute_role = await ctx.guild.create_role(name="Muted")
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, speak=False, send_messages=False, read_message_history=True, read_messages=False)
        await member.add_roles(mute_role)
        await ctx.send(f"{member} a été rendu muet.")
        await member.send("Vous avez été rendu muet sur le serveur.")
        log_channel = bot.get_channel(1403052907364093982)
        if log_channel:
            await log_channel.send(f"{member} a été rendu muet par {ctx.author}.")
    except Exception as e:
        await ctx.send(f"Erreur lors du mute : {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def unmute(ctx, member: discord.Member):
    try:
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if mute_role in member.roles:
            await member.remove_roles(mute_role)
            await ctx.send(f"{member} n'est plus muet.")
            await member.send("Vous avez été débanni (unmute) sur le serveur.")
            log_channel = bot.get_channel(1403052907364093982)
            if log_channel:
                await log_channel.send(f"{member} a été débanni (unmute) par {ctx.author}.")
        else:
            await ctx.send(f"{member} n'était pas muet.")
    except Exception as e:
        await ctx.send(f"Erreur lors du unmute : {e}")
# Partie 7 : Gestion des giveaways simples

import asyncio
import random

giveaways = {}  # Pour stocker les giveaways en cours {message_id: data}

@bot.command()
@commands.has_permissions(administrator=True)
async def giveaway(ctx, duration: int, *, prize: str):
    """
    Lance un giveaway.
    duration : durée en secondes
    prize : description du lot
    """
    embed = discord.Embed(title="🎉 Giveaway 🎉", description=f"Lot : {prize}\nDurée : {duration} secondes", color=0x00ff00)
    embed.set_footer(text="Réagissez avec 🎉 pour participer !")
    message = await ctx.send(embed=embed)
    await message.add_reaction("🎉")

    giveaways[message.id] = {
        "channel": ctx.channel.id,
        "prize": prize,
        "end_time": asyncio.get_event_loop().time() + duration,
        "message": message,
    }

    await asyncio.sleep(duration)

    # Fin du giveaway
    message = giveaways[message.id]["message"]
    message = await ctx.channel.fetch_message(message.id)
    users = set()
    for reaction in message.reactions:
        if str(reaction.emoji) == "🎉":
            users = await reaction.users().flatten()
            break
    users = [user for user in users if not user.bot]

    if len(users) == 0:
        await ctx.send("Aucun participant au giveaway.")
    else:
        winner = random.choice(users)
        await ctx.send(f"Félicitations {winner.mention} ! Tu as gagné : {prize} 🎉")

    del giveaways[message.id]
import discord
from discord.ext import commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

LOG_CHANNEL_ID = 1403052907364093982
ADMIN_ROLE_ID = 1402780875694801007

def is_admin():
    def predicate(ctx):
        return ADMIN_ROLE_ID in [role.id for role in ctx.author.roles]
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}')

async def send_log(bot, message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

async def send_dm(user, content):
    try:
        await user.send(content)
    except Exception as e:
        print(f"Impossible d'envoyer un MP à {user}: {e}")

@bot.command()
@is_admin()
async def ban(ctx, member: discord.Member, *, reason="Non spécifiée"):
    await member.ban(reason=reason)
    await ctx.send(f"{member} a été banni pour : {reason}")
    await send_dm(member, f"Tu as été banni du serveur pour la raison suivante : {reason}")
    await send_log(bot, f"{ctx.author} a banni {member} pour : {reason}")

@bot.command()
@is_admin()
async def kick(ctx, member: discord.Member, *, reason="Non spécifiée"):
    await member.kick(reason=reason)
    await ctx.send(f"{member} a été expulsé pour : {reason}")
    await send_dm(member, f"Tu as été expulsé du serveur pour la raison suivante : {reason}")
    await send_log(bot, f"{ctx.author} a expulsé {member} pour : {reason}")

# On va utiliser un rôle 'Muted' à créer sur le serveur
@bot.command()
@is_admin()
async def mute(ctx, member: discord.Member, *, reason="Non spécifiée"):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        await ctx.send("Le rôle 'Muted' n'existe pas. Merci de le créer avec les permissions appropriées.")
        return
    await member.add_roles(muted_role, reason=reason)
    await ctx.send(f"{member} a été mute pour : {reason}")
    await send_dm(member, f"Tu as été mute sur le serveur pour la raison suivante : {reason}")
    await send_log(bot, f"{ctx.author} a mute {member} pour : {reason}")

@bot.command()
@is_admin()
async def unmute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        await ctx.send("Le rôle 'Muted' n'existe pas.")
        return
    await member.remove_roles(muted_role)
    await ctx.send(f"{member} a été unmute.")
    await send_dm(member, "Tu as été unmute sur le serveur.")
    await send_log(bot, f"{ctx.author} a unmute {member}")

# N'oublie pas d'ajouter le token à la fin, si ce n'est pas déjà fait :
# bot.run('TON_TOKEN_ICI')
import os

if __name__ == "__main__":
    TOKEN = os.getenv("token")
    if not TOKEN:
        print("Erreur : la variable d'environnement 'token' n'est pas définie.")
    else:
        bot.run(TOKEN)
