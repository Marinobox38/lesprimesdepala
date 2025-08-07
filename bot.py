
# ========== IMPORTATIONS ET SETUP ==========
import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import asyncio
import random

# ========== FLASK KEEP ALIVE POUR RENDER ==========
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run).start()

# ========== VARIABLES ==========
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
STAFF_ROLE_ID = 123456789012345678
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== LOGGING ==========
async def log_action(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

# ========== MODAL POUR PRIME ==========
class BountyForm(discord.ui.Modal, title="Demande de Prime"):
    pseudo_pala = discord.ui.TextInput(label="Votre pseudo Paladium", required=True)
    cible = discord.ui.TextInput(label="Pseudo du joueur visé", required=True)
    montant = discord.ui.TextInput(label="Montant de la prime", required=True)
    commentaire = discord.ui.TextInput(label="Quelque chose à ajouter ?", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        view = PaymentConfirmationView(
            pseudo_pala=self.pseudo_pala.value,
            cible=self.cible.value,
            montant=self.montant.value,
            commentaire=self.commentaire.value or "Aucun",
            auteur=interaction.user
        )
        await interaction.response.send_message("Merci ! Confirmez si vous avez envoyé la prime :", view=view, ephemeral=True)

# ========== CONFIRMATION DU PAIEMENT ==========
class PaymentConfirmationView(discord.ui.View):
    def __init__(self, pseudo_pala, cible, montant, commentaire, auteur):
        super().__init__(timeout=None)
        self.pseudo_pala = pseudo_pala
        self.cible = cible
        self.montant = montant
        self.commentaire = commentaire
        self.auteur = auteur

    @discord.ui.select(
        placeholder="Avez-vous envoyé le montant de la prime à Lesprimesdepala ?",
        options=[
            discord.SelectOption(label="Oui", value="oui"),
            discord.SelectOption(label="Non", value="non")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        preuve = "Oui" if select.values[0] == "oui" else "Non"

        embed = discord.Embed(title="Nouvelle demande de prime", color=discord.Color.orange())
        embed.add_field(name="Pseudo Paladium", value=self.pseudo_pala, inline=False)
        embed.add_field(name="Cible", value=self.cible, inline=False)
        embed.add_field(name="Montant", value=self.montant, inline=False)
        embed.add_field(name="Prime envoyée ?", value=preuve, inline=False)
        embed.add_field(name="Commentaire", value=self.commentaire, inline=False)

        view = AcceptRefuseView(embed, self.auteur)

        channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, view=view)
            await interaction.response.send_message("✅ Demande envoyée aux administrateurs.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Salon admin introuvable.", ephemeral=True)

# ========== ACCEPT/REFUSE VIEW ==========
class AcceptRefuseView(discord.ui.View):
    def __init__(self, original_embed, auteur):
        super().__init__(timeout=None)
        self.original_embed = original_embed
        self.auteur = auteur

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        cible = self.original_embed.fields[1].value
        montant = self.original_embed.fields[2].value

        embed = discord.Embed(title="🎯 Prime active !", color=discord.Color.red())
        embed.add_field(name="Cible", value=cible, inline=False)
        embed.add_field(name="Montant", value=montant, inline=False)
        embed.set_footer(text="Cliquez sur le bouton ci-dessous pour réclamer la prime.")

        view = ClaimBountyView(cible, montant)

        channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        if channel:
            await channel.send(f"<@&{PRIME_PING_ROLE_ID}>", embed=embed, view=view)
            await interaction.response.send_message("Prime acceptée et publiée.", ephemeral=True)
            await self.auteur.send(f"✅ Votre prime contre **{cible}** a été acceptée pour **{montant}**.")
        await log_action(f"✅ Prime acceptée : {cible} ({montant}) par {interaction.user.name}")

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        cible = self.original_embed.fields[1].value
        montant = self.original_embed.fields[2].value
        await self.auteur.send(f"❌ Votre demande de prime sur **{cible}** ({montant}) a été refusée.")
        await interaction.response.send_message("Prime refusée.", ephemeral=True)
        await log_action(f"❌ Prime refusée : {cible} ({montant}) par {interaction.user.name}")


# ========== CLAIM PRIME VIEW ==========
class ClaimBountyView(discord.ui.View):
    def __init__(self, cible, montant):
        super().__init__(timeout=None)
        self.cible = cible
        self.montant = montant

    @discord.ui.button(label="J'ai tué la cible", style=discord.ButtonStyle.primary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)

        view = CloseTicketView()
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime sur **{self.cible}**.")
Montant : {self.montant}
await interaction.followup.send('Merci d\'envoyer la preuve ici !', view=view)
await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

    @discord.ui.button(label="Signaler la prime", style=discord.ButtonStyle.danger)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        ticket_channel = await guild.create_text_channel(f"report-{interaction.user.name}", overwrites=overwrites, category=category)
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} souhaite signaler une prime.
Merci de décrire la situation ici.")
        await interaction.response.send_message(f"🚨 Ticket de signalement ouvert : {ticket_channel.mention}", ephemeral=True)

# ========== CLOSE TICKET ==========
class CloseTicketView(discord.ui.View):
    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

# ========== COMMANDE /TICKET-DEPLOY ==========
@bot.tree.command(name="ticket-deploy", description="Déploie le bouton pour ouvrir un ticket")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket_deploy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Besoin d'aide ?",
        description="Cliquez sur le bouton ci-dessous pour ouvrir un ticket avec le staff.
Merci de respecter les modérateurs et d'expliquer clairement votre problème.",
        color=discord.Color.blue()
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Ouvrir un ticket", style=discord.ButtonStyle.success, custom_id="ouvrir_ticket"))
    await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "ouvrir_ticket":
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)
            await channel.send(f"<@&{STAFF_ROLE_ID}> — Ticket ouvert par {interaction.user.mention}", view=CloseTicketView())
            await interaction.response.send_message(f"🎫 Ticket créé : {channel.mention}", ephemeral=True)
    await bot.tree.process_interaction(interaction)

# ========== COMMANDES DE MODÉRATION ==========
@bot.tree.command(name="ban")
@app_commands.describe(user="Utilisateur à bannir", reason="Raison")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str):
    await user.send(f"🚫 Vous avez été banni pour la raison suivante : {reason}")
    await interaction.guild.ban(user, reason=reason)
    await interaction.response.send_message(f"{user} a été banni.", ephemeral=True)
    await log_action(f"🔨 {user} banni par {interaction.user} | Raison : {reason}")

@bot.tree.command(name="kick")
@app_commands.describe(user="Utilisateur à expulser", reason="Raison")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):
    await user.send(f"👢 Vous avez été expulsé pour : {reason}")
    await interaction.guild.kick(user, reason=reason)
    await interaction.response.send_message(f"{user} a été expulsé.", ephemeral=True)
    await log_action(f"👢 {user} expulsé par {interaction.user} | Raison : {reason}")

@bot.tree.command(name="mute")
@app_commands.describe(user="Utilisateur à mute", reason="Raison")
async def mute(interaction: discord.Interaction, user: discord.Member, reason: str):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    await user.add_roles(mute_role)
    await user.send(f"🔇 Vous avez été mute : {reason}")
    await interaction.response.send_message(f"{user} a été mute.", ephemeral=True)
    await log_action(f"🔇 {user} mute par {interaction.user} | Raison : {reason}")

@bot.tree.command(name="unmute")
@app_commands.describe(user="Utilisateur à unmute")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    await user.remove_roles(mute_role)
    await user.send("🔊 Vous avez été unmute.")
    await interaction.response.send_message(f"{user} a été unmute.", ephemeral=True)
    await log_action(f"🔊 {user} unmute par {interaction.user}")

# ========== COMMANDE GIVEAWAY ==========
giveaways = {}

@bot.tree.command(name="giveaway", description="Crée un giveaway")
@app_commands.describe(duration="Durée en secondes", prize="Prix à gagner")
async def giveaway(interaction: discord.Interaction, duration: int, prize: str):
    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"Prix : **{prize}**
Réagissez avec 🎉 pour participer !", color=discord.Color.green())
    embed.set_footer(text=f"Se termine dans {duration} secondes.")
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("🎉")
    giveaways[msg.id] = {"end_time": datetime.utcnow() + timedelta(seconds=duration), "prize": prize, "message": msg}
    await interaction.response.send_message("🎉 Giveaway lancé !", ephemeral=True)

@tasks.loop(seconds=10)
async def check_giveaways():
    to_remove = []
    for gid, data in giveaways.items():
        if datetime.utcnow() >= data["end_time"]:
            msg = data["message"]
            try:
                msg = await msg.channel.fetch_message(msg.id)
                users = await msg.reactions[0].users().flatten()
                users = [u for u in users if not u.bot]
                winner = random.choice(users) if users else None
                if winner:
                    await msg.channel.send(f"🎊 Félicitations {winner.mention} ! Tu gagnes **{data['prize']}**.")
                else:
                    await msg.channel.send("Aucun participant valide. Giveaway annulé.")
            except:
                pass
            to_remove.append(gid)
    for gid in to_remove:
        del giveaways[gid]

check_giveaways.start()

# ========== ON READY ==========
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")
