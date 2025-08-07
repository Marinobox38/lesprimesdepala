import discord
from discord.ext import commands
from discord import app_commands
import os
from flask import Flask
from threading import Thread

# ==== Flask Keep Alive ====
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run).start()

# ==== Variables ====
TOKEN = os.getenv("token")
GUILD_ID = int(os.getenv("guildId"))
STAFF_ROLE_ID = 1402780875694801007
LOG_CHANNEL_ID = 1403052907364093982

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Views ====

class CloseTicketReasonModal(discord.ui.Modal, title="Raison de fermeture du ticket"):
    reason = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, ticket_channel):
        super().__init__()
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        # Log fermeture avec raison
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"Ticket {self.ticket_channel.name} fermé par {interaction.user} pour la raison : {self.reason.value}")
        # Supprimer le salon
        await self.ticket_channel.delete()
        # Confirmer à l'utilisateur
        await interaction.response.send_message("Le ticket a été fermé avec la raison enregistrée.", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Affiche le modal de raison de fermeture
        await interaction.response.send_modal(CloseTicketReasonModal(self.ticket_channel))

class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
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

class ReportTicketView(discord.ui.View):
    def __init__(self, cible_pseudo):
        super().__init__(timeout=None)
        self.cible_pseudo = cible_pseudo

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_report_ticket")
    async def close_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseTicketReasonModal(interaction.channel))

# ==== Commandes ====

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Bot prêt en tant que {bot.user}")

def has_staff_role(interaction: discord.Interaction):
    return any(role.id == STAFF_ROLE_ID for role in interaction.user.roles)

# /ticket-deploy
@bot.tree.command(name="ticket-deploy", description="Déploie le message pour ouvrir un ticket", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Besoin d'aide ?",
        description="Clique sur le bouton ci-dessous pour ouvrir un ticket.",
        color=discord.Color.blurple()
    )
    view = OpenTicketView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Message de ticket déployé !", ephemeral=True)

@ticket_deploy.error
async def ticket_deploy_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)

# /ban [user] [duration] [reason]
@bot.tree.command(name="ban", description="Bannir un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur à bannir", duration="Durée en minutes (0 = permanent)", reason="Raison du ban")
async def ban(interaction: discord.Interaction, user: discord.Member, duration: int = 0, reason: str = "Non spécifiée"):
    try:
        await user.ban(reason=reason)
        # Log
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"{interaction.user} a banni {user} pour {duration} minutes. Raison : {reason}")
        await interaction.response.send_message(f"✅ {user} a été banni. Raison : {reason}")

        if duration > 0:
            # Unban after duration
            async def unban_after():
                await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(minutes=duration))
                await interaction.guild.unban(user)
                if log_channel:
                    await log_channel.send(f"{user} a été unbanni automatiquement après {duration} minutes.")

            bot.loop.create_task(unban_after())
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du ban : {e}", ephemeral=True)

# /kick [user] [reason]
@bot.tree.command(name="kick", description="Expulser un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur à expulser", reason="Raison de l'expulsion")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "Non spécifiée"):
    try:
        await user.kick(reason=reason)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"{interaction.user} a expulsé {user}. Raison : {reason}")
        await interaction.response.send_message(f"✅ {user} a été expulsé. Raison : {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'expulsion : {e}", ephemeral=True)

# /warn [user] [reason]
@bot.tree.command(name="warn", description="Avertir un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur à avertir", reason="Raison de l'avertissement")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    try:
        await user.send(f"⚠️ Vous avez été averti par un membre du staff pour la raison suivante : {reason}")
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"{interaction.user} a averti {user}. Raison : {reason}")
        await interaction.response.send_message(f"✅ {user} a été averti par MP.")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'envoi de l'avertissement : {e}", ephemeral=True)

# /mute [user]
@bot.tree.command(name="mute", description="Mute un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur à mute")
async def mute(interaction: discord.Interaction, user: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        # Crée le rôle si inexistant
        mute_role = await interaction.guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False, speak=False))
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False)
    await user.add_roles(mute_role)
    await interaction.response.send_message(f"✅ {user} est maintenant mute.")
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"{interaction.user} a mute {user}.")

# /unmute [user]
@bot.tree.command(name="unmute", description="Unmute un utilisateur", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(user="Utilisateur à unmute")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if mute_role and mute_role in user.roles:
        await user.remove_roles(mute_role)
        await interaction.response.send_message(f"✅ {user} n'est plus mute.")
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"{interaction.user} a unmute {user}.")
    else:
        await interaction.response.send_message("Cet utilisateur n'est pas mute.", ephemeral=True)

# /message [text]
@bot.tree.command(name="message", description="Envoyer un message au nom du bot", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(text="Texte à envoyer")
async def message(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

# /embed [title] [description]
@bot.tree.command(name="embed", description="Envoyer un embed au nom du bot", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(STAFF_ROLE_ID)
@app_commands.describe(title="Titre de l'embed", description="Description de l'embed")
async def embed(interaction: discord.Interaction, title: str, description: str):
    embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# /site
@bot.tree.command(name="site", description="Afficher le lien du site", guild=discord.Object(id=GUILD_ID))
async def site(interaction: discord.Interaction):
    await interaction.response.send_message("Voici le site : https://lesprimesdepaladium.com")

# /signaler [user]
@bot.tree.command(name="signaler", description="Signaler un joueur (ouvre un ticket)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="Joueur à signaler")
async def signaler(interaction: discord.Interaction, user: discord.Member):
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
    await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} a signalé le joueur **{user.display_name}**. Vous pouvez discuter ici.", view=ReportTicketView(user.display_name))
    await interaction.response.send_message(f"✅ Ticket de signalement créé : {ticket_channel.mention}", ephemeral=True)

# ==== Gestion erreurs ====

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Une erreur est survenue : {error}", ephemeral=True)

# ==== Run ====
bot.run(TOKEN)
