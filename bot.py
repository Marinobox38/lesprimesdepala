import discord
from discord.ext import commands
from discord import app_commands
import os
from flask import Flask
from threading import Thread

# ========== Flask pour Render ==========
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# ========== Variables obligatoires ==========
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
STAFF_ROLE_ID = 123456789012345678  # à remplacer

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== Formulaire Prime ==========
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

        view = AcceptRefuseView(embed)
        channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, view=view)
            await interaction.response.send_message("✅ Demande envoyée aux administrateurs.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Salon admin introuvable.", ephemeral=True)

# ========== Accept / Refuse ==========
class AcceptRefuseView(discord.ui.View):
    def __init__(self, original_embed):
        super().__init__(timeout=None)
        self.original_embed = original_embed

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
            await channel.send(embed=embed, view=view)
            await interaction.response.send_message("Prime acceptée et publiée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Salon de publication introuvable.", ephemeral=True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Prime refusée.", ephemeral=True)

# ========== Claim Prime View ==========
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
        await ticket_channel.send(f"<@&{STAFF_ROLE_ID}> — {interaction.user.mention} réclame une prime sur **{self.cible}**.\nMontant : {self.montant}\nMerci d'envoyer la preuve ici !", view=view)
        await interaction.response.send_message(f"✅ Ticket ouvert : {ticket_channel.mention}", ephemeral=True)

# ========== Close Ticket ==========
class CloseTicketView(discord.ui.View):
    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

# ========== Commandes Slash ==========
@bot.tree.command(name="prime", description="Remplir une demande de prime")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def prime(interaction: discord.Interaction):
    await interaction.response.send_modal(BountyForm())

@bot.tree.command(name="ping", description="Vérifie que le bot est en ligne")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong !", ephemeral=True)

@bot.tree.command(name="ticket", description="Ouvre un ticket avec un joueur")
@app_commands.describe(user="Utilisateur à contacter")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction, user: discord.User):
    guild = interaction.guild
    category = discord.utils.get(guild.categories, name="Tickets") or await guild.create_category("Tickets")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    channel = await guild.create_text_channel(name=f"ticket-{user.name}", overwrites=overwrites, category=category)
    await channel.send(f"<@&{STAFF_ROLE_ID}> — Ticket entre {interaction.user.mention} et {user.mention}", view=CloseTicketView())
    await interaction.response.send_message(f"🎫 Ticket créé : {channel.mention}", ephemeral=True)

@bot.tree.command(name="say", description="Fait parler le bot")
@app_commands.describe(message="Message à envoyer")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("✅ Message envoyé.", ephemeral=True)

@bot.tree.command(name="embed", description="Crée un embed")
@app_commands.describe(titre="Titre", description="Contenu")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def embed(interaction: discord.Interaction, titre: str, description: str):
    em = discord.Embed(title=titre, description=description, color=discord.Color.blue())
    await interaction.channel.send(embed=em)
    await interaction.response.send_message("✅ Embed envoyé.", ephemeral=True)

@bot.tree.command(name="afficher", description="Affiche l'aide pour la commande /prime")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def afficher(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💰 Comment fonctionne la commande /prime ?",
        description="Utilisez `/prime` pour poser une prime sur un joueur. Le staff décidera de la valider.",
        color=discord.Color.gold()
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Remplir une prime", style=discord.ButtonStyle.success, custom_id="ouvrir_prime"))
    await interaction.response.send_message(embed=embed, view=view)

# ========== Interaction (bouton /prime) ==========
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "ouvrir_prime":
            await interaction.response.send_modal(BountyForm())
            return
    await bot.tree.process_interaction(interaction)

# ========== On ready ==========
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Connecté en tant que {bot.user}")
if __name__ == "__main__":
    print("Lancement du bot...")
    bot.run(TOKEN)

