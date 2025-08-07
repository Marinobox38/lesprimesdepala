import discord
from discord.ext import commands
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
REQUEST_CHANNEL_ID = 1402778898923651242  # salon des propositions primes

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
        await interaction.response.send_modal(CloseTicketModal(self.ticket_channel, interaction.user))

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
            embed_public = discord.Embed(title="💰 Prime publiée",
                                       description=f"**Proposée par :** {self.pseudo}\n**Cible :** {self.cible}\n**Montant :** {self.montant}\n**Faction :** {self.faction}",
                                       color=discord.Color.green())
            embed_public.set_footer(text=f"Proposée par {self.pseudo}")
            await public_channel.send(content=f"<@&{PRIME_PING_ROLE_ID}>", embed=embed_public, view=view)

        await interaction.response.send_message("✅ Prime acceptée et publiée !", ephemeral=True)
        await interaction.message.delete()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="prime_refuse")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
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

        view = PrimeValidationView(interaction.user, embed, self.pseudo.value, self.cible.value, self.montant.value, self.faction.value)
        channel = bot.get_channel(REQUEST_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Prime envoyée pour validation !", ephemeral=True)

# ========== Commandes Slash ==========
@bot.tree.command(name="reglement", description="Affiche le règlement du serveur", guild=discord.Object(id=GUILD_ID))
async def reglement(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Règlement du serveur Les Primes de Paladium",
        description=(
            "**Bienvenue sur le serveur !**\nMerci de lire et respecter les règles ci-dessous pour une bonne ambiance et un bon fonctionnement. 🚨\n\n"
            "---------------------------------------------\n\n"
            "### 1. 🤝 Respect & Comportement\n"
            "- Soyez **courtois, poli et bienveillant**.\n"
            "- Aucun propos **haineux, raciste, sexiste ou homophobe** ne sera toléré.\n"
            "- **Pas d'insultes** ou provocations, même pour plaisanter.\n\n"
            "### 2. 📢 Communication\n"
            "- Pas de spam, flood ou messages inutiles.\n"
            "- Utilisez les salons appropriés pour chaque sujet.\n"
            "- Respectez les décisions du staff.\n\n"
            "### 3. 🎮 Primes & Jeux\n"
            "- Respectez les règles spécifiques aux primes.\n"
            "- Toute triche ou comportement déloyal est interdit.\n\n"
            "### 4. ⚠️ Sanctions\n"
            "- Le non-respect du règlement peut entraîner un **mute, kick ou ban**.\n"
            "- En cas de problème, contactez un membre du staff.\n\n"
            "---------------------------------------------\n\n"
            "Merci de votre compréhension et bon jeu ! 🎉"
        ),
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="prime", description="Proposer une prime à valider", guild=discord.Object(id=GUILD_ID))
async def prime(interaction: discord.Interaction):
    await interaction.response.send_modal(PrimeModal())

@bot.tree.command(name="ticket-deploy", description="Déploie le message pour créer un ticket", guild=discord.Object(id=GUILD_ID))
async def ticket_deploy(interaction: discord.Interaction):
    view = CloseTicketView(None)
    embed = discord.Embed(
        title="🎫 Support & Tickets",
        description=(
            "Cliquez sur le bouton ci-dessous pour ouvrir un ticket de support. "
            "Un membre du staff vous aidera dès que possible."
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

@bot.tree.command(name="afficher", description="Affiche les infos sur la commande /prime", guild=discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Proposer une prime", style=discord.ButtonStyle.primary, custom_id="open_prime_modal"))
    embed = discord.Embed(
        title="ℹ️ Commande /prime",
        description=(
            "La commande `/prime` permet de proposer une prime qui sera soumise à validation par le staff.\n"
            "Si elle est acceptée, elle sera publiée publiquement et tout le monde pourra essayer de la réclamer.\n\n"
            "Cliquez sur le bouton ci-dessous pour proposer une prime."
        ),
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Gestion du bouton "Proposer une prime" dans /afficher
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "open_prime_modal":
            await interaction.response.send_modal(PrimeModal())

# ========== Modération ==========
def has_staff_or_admin_role(member):
    return any(role.id in (STAFF_ROLE_ID, ADMIN_ROLE_ID) for role in member.roles)

@bot.tree.command(name="ban", description="Bannir un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à bannir", raison="Raison du bannissement", delete_days="Nombre de jours de messages à supprimer (0-7)")
async def ban(interaction: discord.Interaction, user: discord.Member, raison: str = "Non spécifiée", delete_days: int = 0):
    if not has_staff_or_admin_role(interaction.user):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    if delete_days < 0 or delete_days > 7:
        await interaction.response.send_message("❌ delete_days doit être entre 0 et 7.", ephemeral=True)
        return

    try:
        await user.send(f"⚠️ Vous avez été banni du serveur {interaction.guild.name} pour la raison : {raison}")
    except discord.Forbidden:
        pass

    await user.ban(reason=raison, delete_message_days=delete_days)
    await interaction.response.send_message(f"✅ {user} a été banni pour : {raison}", ephemeral=False)

    await log_action(f"{interaction.user} a banni {user} pour : {raison}")

@bot.tree.command(name="kick", description="Expulser un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à expulser", raison="Raison de l'expulsion")
async def kick(interaction: discord.Interaction, user: discord.Member, raison: str = "Non spécifiée"):
    if not has_staff_or_admin_role(interaction.user):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    try:
        await user.send(f"⚠️ Vous avez été expulsé du serveur {interaction.guild.name} pour la raison : {raison}")
    except discord.Forbidden:
        pass

    await user.kick(reason=raison)
    await interaction.response.send_message(f"✅ {user} a été expulsé pour : {raison}", ephemeral=False)

    await log_action(f"{interaction.user} a expulsé {user} pour : {raison}")

@bot.tree.command(name="mute", description="Mettre un utilisateur en sourdine", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à mute", raison="Raison du mute", duree="Durée en minutes (0 = indéfini)")
async def mute(interaction: discord.Interaction, user: discord.Member, raison: str = "Non spécifiée", duree: int = 0):
    if not has_staff_or_admin_role(interaction.user):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        await interaction.response.send_message("❌ Le rôle Muted n'existe pas.", ephemeral=True)
        return

    await user.add_roles(mute_role, reason=raison)
    await interaction.response.send_message(f"✅ {user} a été mute pour : {raison} {'pendant ' + str(duree) + ' minutes' if duree else 'indéfiniment'}", ephemeral=False)

    await log_action(f"{interaction.user} a mute {user} pour : {raison}, durée : {duree} minutes")

    if duree > 0:
        # Retirer le mute après la durée
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(minutes=duree))
        await user.remove_roles(mute_role, reason="Fin de la durée de mute automatique")
        await log_action(f"{user} a été unmute automatiquement après {duree} minutes")

@bot.tree.command(name="unmute", description="Retirer le mute d'un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Utilisateur à unmute")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    if not has_staff_or_admin_role(interaction.user):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        return

    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        await interaction.response.send_message("❌ Le rôle Muted n'existe pas.", ephemeral=True)
        return

    await user.remove_roles(mute_role, reason="Unmute demandé par un staff")
    await interaction.response.send_message(f"✅ {user} a été unmute.", ephemeral=False)

    await log_action(f"{interaction.user} a unmute {user}")

# ========== Giveaway (basique) ==========
giveaways = {}  # dict pour stocker les giveaways {message_id: {data}}

@bot.tree.command(name="giveaway", description="Créer un giveaway", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(channel="Salon où poster le giveaway", duration="Durée en secondes", prize="Nom du lot")
async def giveaway(interaction: discord.Interaction, channel: discord.TextChannel, duration: int, prize: str):
    if not has_staff_or_admin_role(interaction.user):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        return
    embed = discord.Embed(title="🎉 Giveaway !", description=f"Prix : {prize}\nDurée : {duration} secondes", color=discord.Color.purple())
    embed.set_footer(text=f"Créé par {interaction.user.display_name}")
    message = await channel.send(embed=embed, view=GiveawayView())
    giveaways[message.id] = {
        "channel_id": channel.id,
        "prize": prize,
        "end_time": datetime.utcnow() + timedelta(seconds=duration),
        "message": message,
        "entries": set()
    }
    await interaction.response.send_message(f"✅ Giveaway créé dans {channel.mention} !", ephemeral=True)

class GiveawayView(discord.ui.View):
    @discord.ui.button(label="Participer", style=discord.ButtonStyle.green, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.message.id
        if gid not in giveaways:
            await interaction.response.send_message("Ce giveaway n'existe plus.", ephemeral=True)
            return
        entries = giveaways[gid]["entries"]
        if interaction.user.id in entries:
            await interaction.response.send_message("Vous participez déjà à ce giveaway.", ephemeral=True)
            return
        entries.add(interaction.user.id)
        await interaction.response.send_message("Vous êtes inscrit au giveaway ! Bonne chance ! 🎉", ephemeral=True)

async def giveaway_checker():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.utcnow()
        to_remove = []
        for gid, data in giveaways.items():
            if now >= data["end_time"]:
                channel = bot.get_channel(data["channel_id"])
                if channel:
                    entries = data["entries"]
                    if entries:
                        winner_id = random.choice(list(entries))
                        winner = bot.get_user(winner_id)
                        await channel.send(f"🎉 Félicitations {winner.mention}, vous avez gagné le giveaway pour **{data['prize']}** !")
                    else:
                        await channel.send("Pas de participants pour ce giveaway.")
                    # Supprimer message giveaway
                    try:
                        await data["message"].delete()
                    except:
                        pass
                to_remove.append(gid)
        for gid in to_remove:
            giveaways.pop(gid, None)
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=10))

bot.loop.create_task(giveaway_checker())

# ========== Lancement ==========
bot.run(TOKEN)
