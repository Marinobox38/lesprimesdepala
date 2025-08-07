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
        # Vérifier que la personne a les permissions staff/admin pour fermer
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
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame la prime sur **{self.cible}**.\nMerci d'envoyer la preuve ici !", view=CloseTicketView(ticket_channel))
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
        # Envoi MP à l'auteur
        try:
            await self.author.send(f"✅ Votre prime de {self.montant} pour la cible {self.cible} a été acceptée et publiée publiquement !")
        except discord.Forbidden:
            pass

        # Publication publique avec mention du rôle
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
            # Ajout du bouton "Signaler la prime"
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
                    await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction2.user.mention} signale la prime sur **{self.cible}**.\nMerci de détailler le problème ici !", view=CloseTicketView(ticket_channel))
                    await interaction2.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

            await public_channel.send(f"<@&{PRIME_PING_ROLE_ID}>", embed=embed_public, view=ReportPrimeView())
        else:
            await interaction.response.send_message("❌ Le canal public des primes n'a pas été trouvé.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Prime acceptée et publiée.", ephemeral=True)
        # Supprimer le message original pour éviter les doublons
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
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a ouvert un ticket.", view=CloseTicketView(ticket_channel))
        await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)

@bot.tree.command(name="ticket-deploy", description="Déployer le message pour créer des tickets", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Support - Création de ticket",
        description=(
            "Pour obtenir de l'aide ou signaler un problème, cliquez sur le bouton ci-dessous pour créer un ticket."
        ),
        color=discord.Color.orange()
    )
    view = TicketDeployView()
    request_channel = bot.get_channel(REQUEST_CHANNEL_ID)
if request_channel:
    await request_channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Votre prime a été envoyée au staff pour validation.", ephemeral=True)
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
    await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a ouvert un ticket.", view=CloseTicketView(ticket_channel))
    await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)

# Commande /afficher qui explique la commande /prime avec bouton
class AfficherPrimeView(discord.ui.View):
    @discord.ui.button(label="Proposer une prime", style=discord.ButtonStyle.primary, custom_id="open_prime_modal")
    async def open_prime_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PrimeModal())

class PrimeModal(discord.ui.Modal, title="Proposer une prime"):
    pseudo = discord.ui.TextInput(label="Votre pseudo", max_length=50)
    cible = discord.ui.TextInput(label="Cible de la prime", max_length=100)
    montant = discord.ui.TextInput(label="Montant de la prime", max_length=20)
    faction = discord.ui.TextInput(label="Faction", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Proposition de prime",
            description=(
                f"**Proposée par :** {self.pseudo.value}\n"
                f"**Cible :** {self.cible.value}\n"
                f"**Montant :** {self.montant.value}\n"
                f"**Faction :** {self.faction.value}"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Proposée par {self.pseudo.value}")

        view = PrimeValidationView(interaction.user, embed, self.pseudo.value, self.cible.value, self.montant.value, self.faction.value)
        request_channel = bot.get_channel(REQUEST_CHANNEL_ID)
    if request_channel:
    await request_channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Votre prime a été envoyée au staff pour validation.", ephemeral=True)
else:
    await interaction.response.send_message("❌ Impossible de trouver le salon de propositions.", ephemeral=True)


@bot.tree.command(name="afficher", description="Affiche une explication sur la commande /prime", guild=discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Comment proposer une prime ?",
        description=(
            "Pour proposer une prime, utilisez la commande `/prime` ou cliquez sur le bouton ci-dessous pour ouvrir un formulaire."
        ),
        color=discord.Color.green()
    )
    view = AfficherPrimeView()
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="message", description="Faire dire un message au bot", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(message="Message à faire dire au bot")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)


@bot.tree.command(name="embed", description="Envoyer un embed personnalisé", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(title="Titre de l'embed", description="Description de l'embed", color="Couleur hex (ex: #FF0000)")
async def embed(interaction: discord.Interaction, title: str, description: str, color: str = "#0099ff"):
    try:
        color_value = int(color.strip("#"), 16)
    except ValueError:
        color_value = 0x0099ff
    embed_msg = discord.Embed(title=title, description=description, color=color_value)
    await interaction.response.send_message(embed=embed_msg)


async def send_log_and_dm(action, member: discord.Member, staff: discord.Member, reason: str):
    # Envoi DM à la cible
    try:
        await member.send(f"Vous avez été {action} par {staff} pour la raison : {reason}")
    except discord.Forbidden:
        pass
    # Log dans le salon dédié
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"{member} a été {action} par {staff} pour la raison : {reason}")

@bot.tree.command(name="ban", description="Bannir un membre", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(member="Membre à bannir", reason="Raison du bannissement")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.ban(reason=reason)
    await send_log_and_dm("banni", member, interaction.user, reason)
    await interaction.response.send_message(f"{member} a été banni.", ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(member="Membre à expulser", reason="Raison de l'expulsion")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.kick(reason=reason)
    await send_log_and_dm("kické", member, interaction.user, reason)
    await interaction.response.send_message(f"{member} a été expulsé.", ephemeral=True)


MUTED_ROLE_NAME = "Mute"

@bot.tree.command(name="mute", description="Mute un membre", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(member="Membre à mute", reason="Raison du mute")
async def mute(interaction: discord.Interaction, member: discord.Member, reason: str):
    muted_role = discord.utils.get(interaction.guild.roles, name=MUTED_ROLE_NAME)
    if muted_role is None:
        await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
        return
    await member.add_roles(muted_role, reason=reason)
    await send_log_and_dm("muté", member, interaction.user, reason)
    await interaction.response.send_message(f"{member} a été mute.", ephemeral=True)

@bot.tree.command(name="unmute", description="Unmute un membre", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(member="Membre à unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    muted_role = discord.utils.get(interaction.guild.roles, name=MUTED_ROLE_NAME)
    if muted_role is None:
        await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
        return
    await member.remove_roles(muted_role)
    await send_log_and_dm("unmuté", member, interaction.user, "Unmute manuel")
    await interaction.response.send_message(f"{member} a été unmute.", ephemeral=True)


giveaways = {}  # stocke giveaways actifs : message_id -> info

@bot.tree.command(name="giveaway", description="Créer un giveaway", guild=discord.Object(id=GUILD_ID))
@commands.has_role(ADMIN_ROLE_ID)
@app_commands.describe(
    channel="Salon où poster le giveaway",
    prize="Nom du cadeau",
    duration="Durée en minutes",
    winners="Nombre de gagnants"
)
async def giveaway(interaction: discord.Interaction, channel: discord.TextChannel, prize: str, duration: int, winners: int):
    if duration <= 0 or winners <= 0:
        await interaction.response.send_message("La durée et le nombre de gagnants doivent être positifs.", ephemeral=True)
        return
    embed = discord.Embed(
        title="🎉 Giveaway !",
        description=f"Prix : {prize}\nDurée : {duration} minutes\nNombre de gagnants : {winners}",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="Cliquez sur 🎉 pour participer !")

    view = GiveawayView()
    msg = await channel.send(embed=embed, view=view)

    end_time = datetime.utcnow() + timedelta(minutes=duration)
    giveaways[msg.id] = {
        "channel_id": channel.id,
        "message_id": msg.id,
        "prize": prize,
        "end_time": end_time,
        "winners": winners,
        "participants": set()
    }

    await interaction.response.send_message(f"Giveaway créé dans {channel.mention}", ephemeral=True)

class GiveawayView(discord.ui.View):
    @discord.ui.button(emoji="🎉", style=discord.ButtonStyle.secondary, custom_id="giveaway_participate")
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway_info = giveaways.get(interaction.message.id)
        if giveaway_info is None:
            await interaction.response.send_message("Ce giveaway n'existe plus.", ephemeral=True)
            return
        if interaction.user.id in giveaway_info["participants"]:
            await interaction.response.send_message("Vous participez déjà à ce giveaway.", ephemeral=True)
            return
        giveaway_info["participants"].add(interaction.user.id)
        await interaction.response.send_message("Participation enregistrée !", ephemeral=True)

@tasks.loop(seconds=30)
async def check_giveaways():
    now = datetime.utcnow()
    to_remove = []
    for msg_id, info in giveaways.items():
        if now >= info["end_time"]:
            channel = bot.get_channel(info["channel_id"])
            if channel is None:
                to_remove.append(msg_id)
                continue
            try:
                msg = await channel.fetch_message(msg_id)
            except discord.NotFound:
                to_remove.append(msg_id)
                continue
            participants = list(info["participants"])
            if len(participants) == 0:
                await channel.send(f"Giveaway pour **{info['prize']}** terminé : aucun participant.")
            else:
                winners = random.sample(participants, min(info["winners"], len(participants)))
                winners_mentions = ", ".join(f"<@{w}>" for w in winners)
                await channel.send(f"🎉 Giveaway terminé ! Félicitations à : {winners_mentions} pour **{info['prize']}** !")
            to_remove.append(msg_id)
    for msg_id in to_remove:
        giveaways.pop(msg_id, None)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("Vous n'avez pas la permission d'utiliser cette commande.")
    else:
        await ctx.send(f"Une erreur est survenue : {error}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Erreur : {error}", ephemeral=True)


bot.run(TOKEN)
