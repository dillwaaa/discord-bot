import discord
from discord.ext import commands
import json
import os

VERIF_FILE = "data/verification.json"

def load_config():
    if not os.path.exists(VERIF_FILE):
        return {}
    with open(VERIF_FILE, "r") as f:
        return json.load(f)

def save_config(data):
    os.makedirs("data", exist_ok=True)
    with open(VERIF_FILE, "w") as f:
        json.dump(data, f, indent=2)


class Verification(commands.Cog, name="Vérification"):
    """Système de vérification par réaction."""

    def __init__(self, bot):
        self.bot = bot

    def get_guild_config(self, guild_id: int) -> dict:
        config = load_config()
        return config.get(str(guild_id), {})

    def set_guild_config(self, guild_id: int, data: dict):
        config = load_config()
        config[str(guild_id)] = data
        save_config(config)

    # ── Setup vérification ────────────────────────────────────────────────────

    @commands.command(name="setupverif")
    @commands.has_permissions(administrator=True)
    async def setupverif(self, ctx, role: discord.Role = None, emoji: str = "✅", *, message_texte: str = None):
        """Configure le système de vérification par réaction.
        
        Usage : `!setupverif @role [emoji] [texte du message]`
        Exemple : `!setupverif @Membre ✅ Clique sur ✅ pour accéder au serveur !`
        """
        if not role:
            return await ctx.send(
                "❌ Tu dois spécifier un rôle.\n"
                "Usage : `!setupverif @role [emoji] [message]`\n"
                "Exemple : `!setupverif @Membre ✅ Réagis pour accéder au serveur !`"
            )

        if not message_texte:
            message_texte = (
                f"👋 **Bienvenue sur {ctx.guild.name} !**\n\n"
                f"Pour accéder au serveur, réagis avec {emoji} ci-dessous.\n\n"
                f"En réagissant, tu acceptes les règles du serveur."
            )

        embed = discord.Embed(
            title="🔐 Vérification",
            description=message_texte,
            color=0x5865F2
        )
        embed.set_footer(text=f"Réagis avec {emoji} pour obtenir le rôle {role.name}")
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)

        # Envoi du message de vérification dans le salon actuel
        verif_msg = await ctx.send(embed=embed)
        await verif_msg.add_reaction(emoji)

        # Sauvegarde config
        self.set_guild_config(ctx.guild.id, {
            "message_id": verif_msg.id,
            "channel_id": ctx.channel.id,
            "role_id": role.id,
            "emoji": emoji
        })

        await ctx.send(
            f"✅ Système de vérification configuré !\n"
            f"📌 Salon : {ctx.channel.mention}\n"
            f"🏷️ Rôle attribué : {role.mention}\n"
            f"👍 Emoji : {emoji}",
            delete_after=10
        )

    # ── Listener réaction ajoutée ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignorer les réactions du bot
        if payload.user_id == self.bot.user.id:
            return

        config = self.get_guild_config(payload.guild_id)
        if not config:
            return

        # Vérifier que c'est bien le bon message et le bon emoji
        if (payload.message_id != config.get("message_id") or
                str(payload.emoji) != config.get("emoji")):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        role = guild.get_role(config["role_id"])
        member = guild.get_member(payload.user_id)

        if role and member:
            if role not in member.roles:
                await member.add_roles(role, reason="Vérification par réaction")
                try:
                    await member.send(
                        embed=discord.Embed(
                            title="✅ Vérification réussie !",
                            description=f"Tu as bien été vérifié sur **{guild.name}** et tu as accès à tous les salons !",
                            color=0x2ECC71
                        )
                    )
                except discord.Forbidden:
                    pass

    # ── Listener réaction retirée ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        config = self.get_guild_config(payload.guild_id)
        if not config:
            return

        if (payload.message_id != config.get("message_id") or
                str(payload.emoji) != config.get("emoji")):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        role = guild.get_role(config["role_id"])
        member = guild.get_member(payload.user_id)

        if role and member and role in member.roles:
            await member.remove_roles(role, reason="Réaction de vérification retirée")

    # ── Vérifier un membre manuellement ──────────────────────────────────────

    @commands.command(name="verify")
    @commands.has_permissions(manage_roles=True)
    async def verify(self, ctx, member: discord.Member):
        """Vérifie manuellement un membre.\nUsage : `!verify @membre`"""
        config = self.get_guild_config(ctx.guild.id)
        if not config:
            return await ctx.send("❌ Aucun système de vérification configuré. Lance `!setupverif` d'abord.")

        role = ctx.guild.get_role(config["role_id"])
        if not role:
            return await ctx.send("❌ Le rôle de vérification est introuvable.")

        if role in member.roles:
            return await ctx.send(f"ℹ️ **{member}** est déjà vérifié.")

        await member.add_roles(role, reason=f"Vérification manuelle par {ctx.author}")
        await ctx.send(
            embed=discord.Embed(
                title="✅ Membre vérifié",
                description=f"**{member.mention}** a été vérifié manuellement.",
                color=0x2ECC71
            )
        )

    # ── Réinitialiser la vérification ────────────────────────────────────────

    @commands.command(name="resetverif")
    @commands.has_permissions(administrator=True)
    async def resetverif(self, ctx):
        """Supprime la configuration de vérification.\nUsage : `!resetverif`"""
        config = load_config()
        config.pop(str(ctx.guild.id), None)
        save_config(config)
        await ctx.send(
            embed=discord.Embed(
                title="🗑️ Vérification réinitialisée",
                description="La configuration de vérification a été supprimée.",
                color=0xE74C3C
            )
        )

    # ── Infos vérification ────────────────────────────────────────────────────

    @commands.command(name="verifinfo")
    @commands.has_permissions(administrator=True)
    async def verifinfo(self, ctx):
        """Affiche la config de vérification en cours.\nUsage : `!verifinfo`"""
        config = self.get_guild_config(ctx.guild.id)
        if not config:
            return await ctx.send("❌ Aucune vérification configurée.")

        role = ctx.guild.get_role(config["role_id"])
        channel = ctx.guild.get_channel(config["channel_id"])

        embed = discord.Embed(title="🔐 Config vérification", color=0x5865F2)
        embed.add_field(name="Salon", value=channel.mention if channel else "Introuvable", inline=True)
        embed.add_field(name="Rôle", value=role.mention if role else "Introuvable", inline=True)
        embed.add_field(name="Emoji", value=config["emoji"], inline=True)
        embed.add_field(name="ID message", value=config["message_id"], inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Verification(bot))
