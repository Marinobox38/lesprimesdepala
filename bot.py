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
PUBLIC_BOUNTY_CHANNEL_ID = int(must_get_env("publicChannelId"))
STAFF_ROLE_ID = 123456789012345678  # À adapter
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
class PrimeButtons(discord.ui.View):
    def __init__(self, cible):
        super().__init__(timeout=None)
        self.cible = cible

    @discord.ui.button(label="J'ai tué la cible", style=discord.ButtonStyle.success, custom_id="claim_button")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Merci d'envoyer une capture d'écran comme preuve.", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

class ReportButton(discord.ui.View):
    def __init__(self, cible):
        super().__init__(timeout=None)
        self.cible = cible

    @discord.ui.button(label="Signaler la prime", style=discord.ButtonStyle.danger, custom_id="report_button")
    async def report_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"signalement-{interaction.user.name}",
            overwrites=overwrites,
            category=interaction.channel.category
        )
        await ticket_channel.send(
            f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime sur **{self.cible}**.\nMerci d'envoyer la preuve ici !",
            view=CloseTicketView()
        )
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

# ========== Commandes ==========
@bot.tree.command(name="ping", description="Teste si le bot est en ligne", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong !")

@bot.tree.command(name="ticket-deploy", description="Déploie le message de création de ticket", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(title="Besoin d'aide ?", description="Clique sur le bouton ci-dessous pour créer un ticket.", color=discord.Color.blurple())
    view = CloseTicketView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Message de ticket envoyé.", ephemeral=True)

@bot.tree.command(name="prime", description="Publie une prime", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def prime(interaction: discord.Interaction, cible: str, montant: str):
    embed = discord.Embed(title="🎯 Nouvelle Prime !", description=f"Cible : **{cible}**\nMontant : **{montant}**", color=discord.Color.red())
    view = PrimeButtons(cible)
    view.add_item(discord.ui.Button(label="Réclamer la prime", style=discord.ButtonStyle.success, custom_id="claim_button"))
    report_view = ReportButton(cible)
    channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
    await channel.send(content=f"<@&{PRIME_PING_ROLE_ID}>", embed=embed, view=report_view)
    await interaction.response.send_message("✅ Prime publiée.", ephemeral=True)

@bot.tree.command(name="ticket", description="Créer un ticket privé", guild=discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
        interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
    }
    ticket_channel = await interaction.guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        overwrites=overwrites,
        category=interaction.channel.category
    )
    await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — Nouveau ticket de {interaction.user.mention}", view=CloseTicketView())
    await interaction.response.send_message(f"🎟️ Ticket créé : {ticket_channel.mention}", ephemeral=True)

# ========== Modération ==========
@bot.tree.command(name="ban", description="Bannir un membre", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.send(f"❌ Vous avez été banni pour la raison suivante : {reason}")
    await member.ban(reason=reason)
    await interaction.response.send_message(f"✅ {member.mention} a été banni.")
    await log_action(f"🔨 {member} banni par {interaction.user} — Raison : {reason}")

@bot.tree.command(name="kick", description="Expulser un membre", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.send(f"❌ Vous avez été expulsé pour la raison suivante : {reason}")
    await member.kick(reason=reason)
    await interaction.response.send_message(f"✅ {member.mention} a été expulsé.")
    await log_action(f"👢 {member} expulsé par {interaction.user} — Raison : {reason}")

@bot.tree.command(name="mute", description="Rendre muet un membre", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str):
    until = discord.utils.utcnow() + timedelta(minutes=duration)
    await member.timeout(until, reason=reason)
    await member.send(f"🔇 Vous avez été mute pendant {duration} minutes — Raison : {reason}")
    await interaction.response.send_message(f"✅ {member.mention} a été mute {duration} min.")
    await log_action(f"🔇 {member} mute par {interaction.user} pendant {duration} min — Raison : {reason}")

@bot.tree.command(name="unmute", description="Rendre la parole à un membre", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await member.send("🔊 Vous pouvez de nouveau parler sur le serveur.")
    await interaction.response.send_message(f"✅ {member.mention} a été unmute.")
    await log_action(f"🔊 {member} unmute par {interaction.user}")

# ========== Commande d'explication prime ==========
@bot.tree.command(name="afficher", description="Explique le fonctionnement des primes avec un bouton", guild=discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    embed = discord.Embed(title="Fonctionnement des primes", description="Clique sur le bouton pour proposer une prime.")
    button = discord.ui.Button(label="Proposer une prime", style=discord.ButtonStyle.primary, custom_id="open_prime")
    view = discord.ui.View(timeout=None)
    view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view)

bot.run(TOKEN)
