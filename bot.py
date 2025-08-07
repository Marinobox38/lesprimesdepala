import discord
from discord.ext import commands
from discord import app_commands
import os
from flask import Flask
from threading import Thread

# Mini serveur web pour Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# Variables d'environnement
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

# Initialisation du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Formulaire
class BountyForm(discord.ui.Modal, title="Demande de Prime"):
    pseudo_pala = discord.ui.TextInput(label="Votre pseudo Paladium", required=True)
    pseudo_discord = discord.ui.TextInput(label="Votre pseudo Discord", required=True)
    email = discord.ui.TextInput(label="Adresse e-mail", required=True)
    cible = discord.ui.TextInput(label="Pseudo du joueur visé", required=True)
    montant = discord.ui.TextInput(label="Montant de la prime", required=True)
    preuve_paiement = discord.ui.TextInput(label="Preuve de paiement (lien image ou texte)", required=True, style=discord.TextStyle.paragraph)
    commentaire = discord.ui.TextInput(label="Quelque chose à ajouter ?", required=False, style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print("✅ Formulaire soumis")
            embed = discord.Embed(title="Nouvelle demande de prime", color=discord.Color.orange())
            embed.add_field(name="Pseudo Paladium", value=self.pseudo_pala.value, inline=False)
            embed.add_field(name="Pseudo Discord", value=self.pseudo_discord.value, inline=False)
            embed.add_field(name="Email", value=self.email.value, inline=False)
            embed.add_field(name="Cible", value=self.cible.value, inline=False)
            embed.add_field(name="Montant", value=self.montant.value, inline=False)
            embed.add_field(name="Preuve", value=self.preuve_paiement.value, inline=False)
            embed.add_field(name="Commentaire", value=self.commentaire.value or "Aucun", inline=False)

            view = AcceptRefuseView(embed)
            channel = bot.get_channel(ADMIN_CHANNEL_ID)
            if channel is None:
                print("❌ ADMIN_CHANNEL_ID introuvable")
                await interaction.response.send_message("Salon administrateur introuvable.", ephemeral=True)
                return

            await channel.send(embed=embed, view=view)
            await interaction.response.send_message("Demande envoyée aux administrateurs.", ephemeral=True)
        except Exception as e:
            print("❌ Erreur dans on_submit :", e)
            await interaction.response.send_message("Une erreur est survenue lors de la soumission.", ephemeral=True)

# Vue Accepter / Refuser
class AcceptRefuseView(discord.ui.View):
    def __init__(self, original_embed):
        super().__init__(timeout=None)
        self.original_embed = original_embed

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎯 Prime active !", color=discord.Color.red())
        embed.add_field(name="Cible", value=self.original_embed.fields[3].value, inline=False)
        embed.add_field(name="Montant", value=self.original_embed.fields[4].value, inline=False)
        embed.set_footer(text="Cliquez sur le bouton ci-dessous pour réclamer la prime.")

        view = ClaimBountyView(self.original_embed.fields[3].value, self.original_embed.fields[4].value)
        channel = bot.get_channel(PUBLIC_BOUNTY_CHANNEL_ID)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("Prime acceptée et publiée.")

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Prime refusée.")

# Vue "J'ai tué la cible"
class ClaimBountyView(discord.ui.View):
    def __init__(self, cible, montant):
        super().__init__(timeout=None)
        self.cible = cible
        self.montant = montant

    @discord.ui.button(label="J'ai tué la cible", style=discord.ButtonStyle.primary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")
        ticket_channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)

        await ticket_channel.send(f"""Bienvenue {interaction.user.mention} !
Merci de fournir une **preuve de kill** pour la prime sur **{self.cible}**.
Montant : {self.montant}.
Un membre du staff va vous répondre.""")

# Événement on_ready avec logs et synchro
@bot.event
async def on_ready():
    print(f"✅ {bot.user} est bien connecté à Discord")
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"🔁 {len(synced)} commande(s) slash synchronisées pour le serveur {GUILD_ID}")
        synced_global = await bot.tree.sync()
        print(f"🌍 {len(synced_global)} commande(s) slash synchronisées globalement")
    except Exception as e:
        print("❌ Erreur lors de la synchronisation :", e)

# Commande /prime
@bot.tree.command(name="prime", description="Remplir une demande de prime")
async def prime(interaction: discord.Interaction):
    print("📥 Commande /prime reçue")
    await interaction.response.send_modal(BountyForm())

# ✅ Commande /ping pour test rapide
@bot.tree.command(name="ping", description="Teste la connexion avec le bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong ! Je suis en ligne.", ephemeral=True)

# Lancement du bot
bot.run(TOKEN)
