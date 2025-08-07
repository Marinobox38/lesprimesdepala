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
PUBLIC_BOUNTY_CHANNEL_ID = 1402779650421424168  # ← salon public des primes (modifié)
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
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"preuve-{interaction.user.name}",
            overwrites=overwrites,
            category=interaction.channel.category
        )
        await ticket_channel.send(
            f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} affirme avoir tué **{self.cible}**. Merci de fournir une preuve.",
            view=CloseTicketView()
        )
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

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
            f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} signale une prime sur **{self.cible}**.",
            view=CloseTicketView()
        )
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

class PrimeModal(discord.ui.Modal, title="Proposer une Prime"):
    pseudo = discord.ui.TextInput(label="Votre pseudo")
    cible = discord.ui.TextInput(label="Joueur visé")
    montant = discord.ui.TextInput(label="Montant de la prime")
    faction = discord.ui.TextInput(label="Votre faction")

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="💰 Nouvelle Prime Proposée",
                              description=f"**Proposée par :** {self.pseudo.value}\n**Cible :** {self.cible.value}\n**Montant :** {self.montant.value}\n**Faction :** {self.faction.value}",
                              color=discord.Color.orange())
        embed.set_footer(text=f"Proposée par {interaction.user.display_name}")

        view = PrimeValidationView(interaction.user, self.pseudo.value, self.cible.value, self.montant.value, self.faction.value)
        await bot.get_channel(FORM_SUBMIT_CHANNEL_ID).send(embed=embed, view=view)
        await interaction.response.send_message("✅ Prime envoyée pour validation !", ephemeral=True)

class PrimeValidationView(discord.ui.View):
    def __init__(self, author, pseudo, cible, montant, faction):
        super().__init__(timeout=None)
        self.author = author
        self.pseudo = pseudo
        self.cible = cible
        self.montant = montant
        self.faction = faction

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.author.send("✅ Votre prime a été acceptée et publiée publiquement !")

        embed = discord.Embed(title="🎯 Prime Publique",
                              description=f"**Cible :** {self.cible}\n**Montant :** {self.montant}\n**Faction :** {self.faction}\n**Proposée par :** {self.pseudo}",
                              color=discord.Color.red())
        view = discord.ui.View(timeout=None)
        view.add_item(PrimeButtons(self.cible).children[0])
        view.add_item(ReportButton(self.cible).children[0])

        await bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID).send(f"<@&{PRIME_PING_ROLE_ID}>", embed=embed, view=view)
        await interaction.response.send_message("✅ Prime acceptée !", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.author.send("❌ Votre prime a été refusée.")
        await interaction.response.send_message("⛔ Prime refusée.", ephemeral=True)

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

@bot.tree.command(name="prime", description="Ouvre un formulaire pour proposer une prime", guild=discord.Object(id=GUILD_ID))
async def prime(interaction: discord.Interaction):
    await interaction.response.send_modal(PrimeModal())

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

# ========== Commande d'explication prime ==========
@bot.tree.command(name="afficher", description="Explique le fonctionnement des primes avec un bouton", guild=discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    embed = discord.Embed(title="Fonctionnement des primes", description="Clique sur le bouton pour proposer une prime.")
    button = discord.ui.Button(label="Proposer une prime", style=discord.ButtonStyle.primary, custom_id="open_prime")
    view = discord.ui.View(timeout=None)
    view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "open_prime":
            await interaction.response.send_modal(PrimeModal())
        else:
            await bot.process_application_commands(interaction)
    else:
        await bot.process_application_commands(interaction)

bot.run(TOKEN)
