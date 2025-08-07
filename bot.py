import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
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

# Channels & Roles (à adapter)
WELCOME_CHANNEL_ID = 1403090073746014210
PUBLIC_BOUNTY_CHANNEL_ID = 1402779650421424168
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982
STAFF_ROLE_ID = 1402780875694801007
ADMIN_ROLE_ID = 1402780875694801007
REQUEST_CHANNEL_ID = 1402778898923651242  # où vont les propositions de primes

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== Messages de bienvenue ==========
welcome_messages = [
    "Bienvenue sur le serveur !",
    "Salut et bienvenue, amuse-toi bien !",
    "Un nouveau membre parmi nous, bienvenue !",
    "Heureux de te voir ici !",
    "Bienvenue, prêt à relever des défis ?"
]

# ========== On Ready ==========
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")

# ========== Bienvenue ==========
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

# ========== Logs ==========
async def log_action(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

# ========== Views ==========
class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ouvre un modal pour demander la raison de fermeture avant suppression
        await interaction.response.send_modal(CloseTicketModal(self.ticket_channel, interaction.user))

class CloseTicketModal(discord.ui.Modal, title="Raison de la fermeture du ticket"):
    raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, ticket_channel, closer):
        super().__init__()
        self.ticket_channel = ticket_channel
        self.closer = closer

    async def on_submit(self, interaction: discord.Interaction):
        # Envoi log raison de fermeture
        await log_action(f"Ticket {self.ticket_channel.name} fermé par {self.closer} pour la raison : {self.raison.value}")
        await interaction.response.send_message(f"Ticket fermé. Raison : {self.raison.value}", ephemeral=True)
        await self.ticket_channel.delete()

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
        # Envoie message accepté à l'auteur
        try:
            await self.author.send(f"✅ Votre prime de {self.montant} pour la cible {self.cible} a été acceptée et publiée publiquement !")
        except discord.Forbidden:
            pass

        # Poste dans le salon public avec bouton "J'ai tué la cible"
        public_channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        if public_channel:
            view = PrimeClaimView(self.cible)
            embed_public = discord.Embed(title="💰 Prime publiée",
                                       description=f"**Proposée par :** {self.pseudo}\n**Cible :** {self.cible}\n**Montant :** {self.montant}\n**Faction :** {self.faction}",
                                       color=discord.Color.green())
            embed_public.set_footer(text=f"Proposée par {self.pseudo}")
            await public_channel.send(content=f"<@&{PRIME_PING_ROLE_ID}>", embed=embed_public, view=view)

        await interaction.response.send_message("✅ Prime acceptée et publiée !", ephemeral=True)
        # Supprime le message original avec boutons (validation)
        await interaction.message.delete()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="prime_refuse")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Envoie message refusé à l'auteur
        try:
            await self.author.send(f"❌ Votre prime pour la cible {self.cible} a été refusée.")
        except discord.Forbidden:
            pass
        await interaction.response.send_message("⛔ Prime refusée.", ephemeral=True)
        await interaction.message.delete()

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
        category = interaction.channel.category
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"signalement-{interaction.user.name}",
            overwrites=overwrites,
            category=category
        )
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame la prime sur **{self.cible}**.\nMerci d'envoyer la preuve ici !", view=CloseTicketView(ticket_channel))
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

# ========== Modals ==========
class PrimeModal(discord.ui.Modal, title="Proposer une Prime"):
    pseudo = discord.ui.TextInput(label="Votre pseudo", required=True)
    cible = discord.ui.TextInput(label="Joueur visé", required=True)
    montant = discord.ui.TextInput(label="Montant de la prime", required=True)
    faction = discord.ui.TextInput(label="Votre faction", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="💰 Nouvelle Prime Proposée",
                              description=(
                                  f"**Proposée par :** {self.pseudo.value}\n"
                                  f"**Cible :** {self.cible.value}\n"
                                  f"**Montant :** {self.montant.value}\n"
                                  f"**Faction :** {self.faction.value}"
                              ),
                              color=discord.Color.orange())
        embed.set_footer(text=f"Proposée par {interaction.user.display_name}")

        # Envoi dans le salon de validation avec boutons Accepter/Refuser
        view = PrimeValidationView(interaction.user, embed, self.pseudo.value, self.cible.value, self.montant.value, self.faction.value)
        channel = bot.get_channel(REQUEST_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Prime envoyée pour validation !", ephemeral=True)

# ========== Commandes ==========
from discord import app_commands, Interaction, Embed, Color, ui
from discord.ext import commands
import discord

GUILD_ID = 1402778898923651242  # Remplace par ton ID de serveur

class ReglementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ J'accepte", style=discord.ButtonStyle.success, custom_id="reglement_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Merci d'avoir accepté le règlement ✅", ephemeral=True)
        try:
            await interaction.user.send(
                "👋 Merci d'avoir accepté le règlement du serveur **Les Primes de Paladium** !\n\nTu peux maintenant pleinement participer.\nN'oublie pas de consulter le site : https://lesprimesdepaladium.com"
            )
        except discord.Forbidden:
            pass  # L'utilisateur a désactivé les MP

@bot.tree.command(name="reglement", description="Affiche le règlement du serveur", guild=discord.Object(id=GUILD_ID))
async def reglement(interaction: Interaction):
    embed = Embed(
        title="📜 Règlement du serveur Les Primes de Paladium",
        description=(
            "**Bienvenue sur le serveur !**\nMerci de lire et respecter les règles ci-dessous pour une bonne ambiance et un bon fonctionnement. 🚨\n\n"
            "---------------------------------------------\n\n"
            "### 1. 🤝 Respect & Comportement\n"
            "- Soyez **courtois, poli et bienveillant**.\n"
            "- Aucun propos **haineux, raciste, sexiste ou homophobe** ne sera toléré.\n"
            "- **Pas d'insultes** ou provocations, même pour plaisanter.\n\n"
            "### 2. 📢 Communication\n"
            "- Utilisez les **bons salons**.\n"
            "- Évitez le **spam**, le flood ou les abus de mentions.\n"
            "- Pas de **langage SMS** excessif.\n\n"
            "### 3. 📛 Pseudo & Profil\n"
            "- Ayez un pseudo **lisible et respectueux**.\n"
            "- Pas d'usurpation d'identité (staff ou autre).\n\n"
            "### 4. 📬 Mentions & MP\n"
            "- N'envoyez pas de **DM non sollicités**.\n"
            "- Ne mentionnez le staff **qu’en cas de nécessité**.\n\n"
            "### 5. 💣 Primes & Signalements\n"
            "- Proposez des **primes sérieuses et justifiées**.\n"
            "- Les **abus ou fausses primes** seront sanctionnés.\n"
            "- Utilisez \"🔪 J’ai tué la cible\" seulement **avec une preuve**.\n"
            "- Utilisez \"🚨 Signaler la prime\" si nécessaire.\n\n"
            "### 6. 🎟️ Tickets & Support\n"
            "- Créez un ticket via `/ticket` pour toute demande importante.\n"
            "- Soyez respectueux dans les échanges avec le staff.\n\n"
            "### 7. 🛡️ Sanctions\n"
            "- ⚠️ `/warn` → Avertissement\n"
            "- ⛔ `/mute` → Mute temporaire\n"
            "- 🚷 `/kick` → Expulsion\n"
            "- 🔨 `/ban` → Bannissement\n\n"
            "### 8. 🌐 Infos utiles\n"
            "- Site : [https://lesprimesdepaladium.com](https://lesprimesdepaladium.com)\n"
            "- Besoin d’aide ? Utilise `/ticket`.\n\n"
            "---------------------------------------------\n\n"
            "**Merci de votre compréhension et bon jeu à tous !** 🎮\nL’équipe du staff 💙"
        ),
        color=Color.gold()
    )
    await interaction.response.send_message(embed=embed, view=ReglementView())

@bot.tree.command(name="ping", description="Teste si le bot est en ligne", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong !")

@bot.tree.command(name="afficher", description="Explique le fonctionnement des primes avec un bouton", guild=discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Fonctionnement des primes",
        description="Clique sur le bouton pour déposer une prime.",
        color=discord.Color.gold()
    )
    button = discord.ui.Button(
        label="⚔️ Déposer une prime",
        style=discord.ButtonStyle.primary,
        custom_id="open_prime"
    )
    view = discord.ui.View(timeout=None)
    view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="prime", description="Ouvre un formulaire pour proposer une prime", guild=discord.Object(id=GUILD_ID))
async def prime(interaction: discord.Interaction):
    await interaction.response.send_modal(PrimeModal())

@bot.tree.command(name="ticket-deploy", description="Déploie le message de création de ticket", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(title="Besoin d'aide ?", description="Clique sur le bouton ci-dessous pour créer un ticket.", color=discord.Color.blurple())
    button = discord.ui.Button(label="Créer un ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    view = discord.ui.View(timeout=None)
    view.add_item(button)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Message de ticket déployé.", ephemeral=True)

@bot.tree.command(name="ban", description="Ban un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à bannir", duration="Durée du ban en minutes (optionnel)", reason="Raison du ban")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def ban(interaction: discord.Interaction, user: discord.Member, duration: int = None, reason: str = None):
    try:
        await user.ban(reason=reason)
        await interaction.response.send_message(f"🚫 {user.mention} a été banni. Raison : {reason if reason else 'Aucune'}")
        if duration:
            unban_time = datetime.utcnow() + timedelta(minutes=duration)
            # Optionnel : stocker ce unban_time quelque part pour un déban automatique (non implémenté ici)
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du ban : {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Expulse un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à expulser", reason="Raison de l'expulsion")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.kick(reason=reason)
        await interaction.response.send_message(f"👢 {user.mention} a été expulsé. Raison : {reason if reason else 'Aucune'}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du kick : {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Avertit un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à avertir", reason="Raison de l'avertissement")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    try:
        await user.send(f"⚠️ Vous avez été averti par un membre du staff pour la raison suivante : {reason}")
        await interaction.response.send_message(f"⚠️ {user.mention} a été averti. Raison : {reason}")
    except discord.Forbidden:
        await interaction.response.send_message(f"Impossible d'envoyer le message privé à {user.mention}.", ephemeral=True)

@bot.tree.command(name="mute", description="Mute un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à mute")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def mute(interaction: discord.Interaction, user: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        try:
            mute_role = await interaction.guild.create_role(name="Muted")
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role, speak=False, send_messages=False, read_message_history=True, read_messages=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de la création du rôle mute : {e}", ephemeral=True)
            return
    await user.add_roles(mute_role)
    await interaction.response.send_message(f"🔇 {user.mention} a été mute.")

@bot.tree.command(name="unmute", description="Unmute un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à unmute")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def unmute(interaction: discord.Interaction, user: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
        return
    await user.remove_roles(mute_role)
    await interaction.response.send_message(f"🔈 {user.mention} a été unmute.")

@bot.tree.command(name="message", description="Envoyer un message au nom du bot", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(message="Message à envoyer")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def message(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(name="embed", description="Envoyer un embed au nom du bot", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(title="Titre", description="Description")
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def embed(interaction: discord.Interaction, title: str, description: str):
    embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="site", description="Affiche le lien du site", guild=discord.Object(id=GUILD_ID))
async def site(interaction: discord.Interaction):
    await interaction.response.send_message("Voici le site : https://lesprimesdepaladium.com")

@bot.tree.command(name="signaler", description="Signaler un joueur (ouvre un ticket)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à signaler")
async def signaler(interaction: discord.Interaction, user: discord.Member):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
        interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True),
    }
    category = interaction.channel.category
    ticket_channel = await interaction.guild.create_text_channel(
        name=f"signalement-{user.name}",
        overwrites=overwrites,
        category=category
    )
    await ticket_channel.send(
        f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a signalé {user.mention}. "
        "Merci de discuter ici avec le staff.",
        view=CloseTicketView(ticket_channel)
    )
    await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)

# ========== Interaction component handler ==========
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data.get("custom_id")
        if cid == "open_prime":
            await interaction.response.send_modal(PrimeModal())
        elif cid == "create_ticket":
            # Création d’un ticket d’aide pour l’utilisateur
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True),
                interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
            }
            category = interaction.channel.category
            ticket_channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                overwrites=overwrites,
                category=category
            )
            await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a créé un ticket.", view=CloseTicketView(ticket_channel))
            await interaction.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)
        elif cid == "close_ticket":
            # Ce bouton est géré dans la View CloseTicketView
            pass
    else:
        await bot.process_application_commands(interaction)

bot.run(TOKEN)
