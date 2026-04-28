import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None  # On désactive le help par défaut
)

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="le serveur 👀 | !help"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas la permission d'utiliser cette commande.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Membre introuvable.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilise `!help {ctx.command}` pour plus d'infos.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignorer les commandes inconnues
    else:
        await ctx.send(f"❌ Erreur : `{error}`")

@bot.command(name="help")
async def help_command(ctx, commande: str = None):
    """Affiche l'aide du bot."""
    if commande:
        cmd = bot.get_command(commande)
        if cmd:
            embed = discord.Embed(
                title=f"📖 Aide : !{cmd.name}",
                description=cmd.help or "Pas de description.",
                color=0x5865F2
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Commande `{commande}` inconnue.")
        return

    embed = discord.Embed(
        title="🤖 Aide du Bot",
        description="Voici toutes les commandes disponibles.",
        color=0x5865F2
    )
    embed.add_field(
        name="🔨 Modération",
        value=(
            "`!kick <@user> [raison]` — Expulser un membre\n"
            "`!ban <@user> [raison]` — Bannir un membre\n"
            "`!unban <id>` — Débannir un membre\n"
            "`!mute <@user> [durée] [raison]` — Muter un membre\n"
            "`!unmute <@user>` — Unmuter un membre\n"
            "`!clear <nb>` — Supprimer des messages\n"
            "`!warn <@user> [raison]` — Avertir un membre\n"
            "`!warnings <@user>` — Voir les warns d'un membre\n"
            "`!slowmode <secondes>` — Activer le slowmode\n"
            "`!lock` / `!unlock` — Verrouiller un salon"
        ),
        inline=False
    )
    embed.add_field(
        name="🎵 Musique",
        value=(
            "`!join` — Rejoindre ton salon vocal\n"
            "`!play <titre/url>` — Jouer une musique\n"
            "`!pause` — Mettre en pause\n"
            "`!resume` — Reprendre la lecture\n"
            "`!skip` — Passer la musique\n"
            "`!stop` — Arrêter et vider la file\n"
            "`!queue` — Voir la file d'attente\n"
            "`!volume <0-100>` — Régler le volume\n"
            "`!nowplaying` — Musique en cours\n"
            "`!leave` — Quitter le salon vocal"
        ),
        inline=False
    )
    embed.add_field(
        name="🔐 Vérification",
        value=(
            "`!setupverif @role [emoji] [message]` — Configurer la vérification\n"
            "`!verify @user` — Vérifier manuellement un membre\n"
            "`!verifinfo` — Voir la config de vérification\n"
            "`!resetverif` — Supprimer la config de vérification"
        ),
        inline=False
    )
    embed.set_footer(text="!help <commande> pour plus de détails")
    await ctx.send(embed=embed)

async def setup_hook():
    await bot.load_extension("cogs.moderation")
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.verification")

bot.setup_hook = setup_hook

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN introuvable dans le fichier .env !")
    else:
        bot.run(token)
