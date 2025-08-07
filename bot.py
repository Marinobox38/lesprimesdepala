import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import asyncio
import random

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
STAFF_ROLE_ID = 1402780875694801007  # Remplacer par l'ID réel
PRIME_PING_ROLE_ID = 1403052017521393755
LOG_CHANNEL_ID = 1403052907364093982

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== Utils ==========
async def log_action(guild, message):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

async def send_dm(user, message):
    try:
        await user.send(message)
    except Exception:
        pass  # On ignore si le DM est fermé

# ========== Modal Formulaire Prime ==========
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
            commentaire=self.commentaire.value or "Aucun"
        )
        await interaction.response.send_message("Merci ! Confirmez si vous avez envoyé la prime :", view=view, ephemeral=True)

# ========== Payment Confirmation View ==========
class PaymentConfirmationView(discord.ui.View):
    def __init__(self, pseudo_pala, cible, montant, commentaire):
        super().__init__(timeout=None)
        self.pseudo_pala = pseudo_pala
        self.cible = cible
        self.montant = montant
        self.commentaire = commentaire

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

        view = AcceptRefuseView(embed, self.pseudo_pala, self.cible, self.montant, self.commentaire)
        channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, view=view)
            await interaction.response.send_message("✅ Demande envoyée aux administrateurs.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Salon admin introuvable.", ephemeral=True)

# ========== Accept / Refuse View ==========
class AcceptRefuseView(discord.ui.View):
    def __init__(self, original_embed, pseudo_pala, cible, montant, commentaire):
        super().__init__(timeout=None)
        self.original_embed = original_embed
        self.pseudo_pala = pseudo_pala
        self.cible = cible
        self.montant = montant
        self.commentaire = commentaire

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Envoi MP à l'auteur
        guild = interaction.guild
        member = discord.utils.get(guild.members, name=self.pseudo_pala)
        if not member:
            # Essaie par mention ou autre, sinon on ignore MP
            try:
                member = await bot.fetch_user(interaction.user.id)
            except:
                member = None
        if member:
            await send_dm(member, f"Votre demande de prime a été **acceptée**.\n"
                                 f"Cible : {self.cible}\nMontant : {self.montant}\nCommentaire : {self.commentaire}")

        # Envoi dans le channel public avec ping rôle
        embed = discord.Embed(title="🎯 Prime active !", color=discord.Color.red())
        embed.add_field(name="Cible", value=self.cible, inline=False)
        embed.add_field(name="Montant", value=self.montant, inline=False)
        embed.set_footer(text="Cliquez sur un bouton ci-dessous pour réclamer ou signaler la prime.")

        view = ClaimAndReportView(self.cible, self.montant)

        channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        if channel:
            await channel.send(f"<@&{PRIME_PING_ROLE_ID}>", embed=embed, view=view)
            await interaction.response.send_message("Prime acceptée et publiée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Salon de publication introuvable.", ephemeral=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        # MP à l'auteur
        guild = interaction.guild
        member = discord.utils.get(guild.members, name=self.pseudo_pala)
        if not member:
            try:
                member = await bot.fetch_user(interaction.user.id)
            except:
                member = None
        if member:
            await send_dm(member, f"Votre demande de prime a été **refusée**.\n"
                                 f"Cible : {self.cible}\nMontant : {self.montant}\nCommentaire : {self.commentaire}")
        await interaction.response.send_message("Prime refusée.", ephemeral=True)

# ========== Claim and Report View ==========
class ClaimAndReportView(discord.ui.View):
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
            discord.utils.get(guild.roles, id=STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)

        view = CloseTicketView()
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime sur **{self.cible}**.\nMontant : {self.montant}\nMerci d'envoyer la preuve ici !", view=view)
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

    @discord.ui.button(label="Signaler la prime", style=discord.ButtonStyle.danger)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            discord.utils.get(guild.roles, id=STAFF_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(f"signalement-{interaction.user.name}", overwrites=overwrites, category=category)

        view = CloseTicketView()
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} signale une prime sur **{self.cible}**.\nMerci d'examiner ce signalement.", view=view)
        await interaction.response.send_message(f"✅ Ticket de signalement ouvert : {ticket_channel.mention}", ephemeral=True)

# ========== Close Ticket View ==========
class CloseTicketView(discord.ui.View):
    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

# ========== Commandes Slash ==========

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

# ========== Modération Commandes ==========
@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(membre="Le membre à bannir", raison="Raison du ban", duree="Durée en minutes (optionnel)")
@commands.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str, duree: int = None):
    try:
        await membre.ban(reason=raison)
        await interaction.response.send_message(f"{membre.mention} a été banni pour : {raison} (durée: {duree or 'permanent'})")

        msg = f"Vous avez été banni du serveur {interaction.guild.name}.\nRaison : {raison}\n"
        if duree:
            msg += f"Durée : {duree} minutes.\n"
            await asyncio.sleep(duree * 60)
            await interaction.guild.unban(membre)
            await interaction.channel.send(f"{membre.mention} a été débanni automatiquement après {duree} minutes.")
        await send_dm(membre, msg)

        # Log
        await log_action(interaction.guild, f"⚠️ {membre} banni par {interaction.user}. Raison : {raison}. Durée : {duree or 'permanent'}")
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

        # Log
        await log_action(interaction.guild, f"⚠️ {membre} expulsé par {interaction.user}. Raison : {raison}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'expulsion : {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Mute un membre")
@app_commands.describe(membre="Le membre à mute", duree="Durée en minutes", raison="Raison")
@commands.has_permissions(manage_messages=True)
async def mute(interaction: discord.Interaction, membre: discord.Member, duree: int, raison: str):
    guild = interaction.guild
    mute_role = discord.utils.get(guild.roles, name="Muted")
    if not mute_role:
        mute_role = await guild.create_role(name="Muted")

        for channel in guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False, add_reactions=False)

    try:
        await membre.add_roles(mute_role, reason=raison)
        await interaction.response.send_message(f"{membre.mention} est mute pour {duree} minutes.\nRaison : {raison}")
        await send_dm(membre, f"Vous avez été mute sur le serveur {guild.name} pour {duree} minutes.\nRaison : {raison}")

        # Log
        await log_action(guild, f"🔇 {membre} mute par {interaction.user} pendant {duree} minutes. Raison : {raison}")

        await asyncio.sleep(duree * 60)
        await membre.remove_roles(mute_role, reason="Fin du mute automatique")
        await interaction.channel.send(f"{membre.mention} a été unmute automatiquement après {duree} minutes.")
        await send_dm(membre, f"Votre mute sur le serveur {guild.name} est terminé.")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du mute : {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Unmute un membre")
@app_commands.describe(membre="Le membre à unmute")
@commands.has_permissions(manage_messages=True)
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    guild = interaction.guild
    mute_role = discord.utils.get(guild.roles, name="Muted")
    if not mute_role:
        await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
        return

    try:
        await membre.remove_roles(mute_role, reason=f"Unmute demandé par {interaction.user}")
        await interaction.response.send_message(f"{membre.mention} a été unmute.")
        await send_dm(membre, f"Vous avez été unmute sur le serveur {guild.name}.")

        # Log
        await log_action(guild, f"🔈 {membre} unmute par {interaction.user}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'unmute : {e}", ephemeral=True)

# ========== Giveaways ==========
class Giveaway:
    def __init__(self, channel, message, prize, end_time, host):
        self.channel = channel
        self.message = message
        self.prize = prize
        self.end_time = end_time
        self.host = host
        self.entries = set()
        self.ended = False

giveaways = {}

@bot.tree.command(name="giveaway", description="Créer un giveaway")
@app_commands.describe(channel="Salon où poster le giveaway", duree="Durée en minutes", prix="Nom du prix")
@commands.has_permissions(administrator=True)
async def giveaway_create(interaction: discord.Interaction, channel: discord.TextChannel, duree: int, prix: str):
    end_time = datetime.utcnow() + timedelta(minutes=duree)
    embed = discord.Embed(title="🎉 Giveaway 🎉", description=f"Prix : {prix}\nFin dans {duree} minutes.", color=discord.Color.gold())
    embed.set_footer(text="Réagissez avec 🎉 pour participer !")

    message = await channel.send(embed=embed)
    await message.add_reaction("🎉")

    giveaways[message.id] = Giveaway(channel, message, prix, end_time, interaction.user)
    await interaction.response.send_message(f"Giveaway créé dans {channel.mention} pour {duree} minutes.")

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.id in giveaways:
        giveaway = giveaways[reaction.message.id]
        if reaction.emoji == "🎉":
            giveaway.entries.add(user.id)

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return
    if reaction.message.id in giveaways:
        giveaway = giveaways[reaction.message.id]
        if reaction.emoji == "🎉":
            giveaway.entries.discard(user.id)

@tasks.loop(seconds=30)
async def check_giveaways():
    now = datetime.utcnow()
    ended = []
    for message_id, giveaway in giveaways.items():
        if not giveaway.ended and now >= giveaway.end_time:
            giveaway.ended = True
            if giveaway.entries:
                winner_id = random.choice(list(giveaway.entries))
                winner = giveaway.channel.guild.get_member(winner_id)
                embed = discord.Embed(title="🎉 Giveaway terminé 🎉", description=f"Le gagnant est {winner.mention} !", color=discord.Color.green())
                await giveaway.message.edit(embed=embed)
                await giveaway.channel.send(f"Félicitations {winner.mention} ! Tu as gagné : {giveaway.prize}")
            else:
                embed = discord.Embed(title="🎉 Giveaway terminé 🎉", description=f"Aucun participant, le giveaway est annulé.", color=discord.Color.red())
                await giveaway.message.edit(embed=embed)
                await giveaway.channel.send("Aucun participant pour le giveaway.")

            ended.append(message_id)
    for msg_id in ended:
        giveaways.pop(msg_id)

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")
    check_giveaways.start()

bot.run(TOKEN)
