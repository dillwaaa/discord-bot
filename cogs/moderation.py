import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime, timedelta

WARNS_FILE = "data/warnings.json"

def load_warns():
    if not os.path.exists(WARNS_FILE):
        return {}
    with open(WARNS_FILE, "r") as f:
        return json.load(f)

def save_warns(data):
    os.makedirs("data", exist_ok=True)
    with open(WARNS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def success_embed(title, desc):
    return discord.Embed(title=f"✅ {title}", description=desc, color=0x2ECC71)

def error_embed(title, desc):
    return discord.Embed(title=f"❌ {title}", description=desc, color=0xE74C3C)

def info_embed(title, desc):
    return discord.Embed(title=f"ℹ️ {title}", description=desc, color=0x5865F2)


class Moderation(commands.Cog, name="Modération"):
    """Commandes de modération du serveur."""

    def __init__(self, bot):
        self.bot = bot
        self.muted_users = {}  # {user_id: unmute_time}
        self.check_mutes.start()

    def cog_unload(self):
        self.check_mutes.cancel()

    # ── Vérification des mutes temporaires ──────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_mutes(self):
        now = datetime.utcnow()
        to_remove = []
        for (guild_id, user_id), end_time in self.muted_users.items():
            if now >= end_time:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    member = guild.get_member(user_id)
                    muted_role = discord.utils.get(guild.roles, name="Muted")
                    if member and muted_role and muted_role in member.roles:
                        await member.remove_roles(muted_role, reason="Mute expiré")
                to_remove.append((guild_id, user_id))
        for key in to_remove:
            del self.muted_users[key]

    # ── Kick ─────────────────────────────────────────────────────────────────

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, raison: str = "Aucune raison fournie"):
        """Expulse un membre du serveur.\nUsage : `!kick @membre [raison]`"""
        if member == ctx.author:
            return await ctx.send(embed=error_embed("Erreur", "Tu ne peux pas te kick toi-même."))
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=error_embed("Erreur", "Tu ne peux pas kick quelqu'un avec un rôle supérieur ou égal au tien."))

        try:
            await member.send(embed=info_embed("Expulsé", f"Tu as été expulsé de **{ctx.guild.name}**.\nRaison : {raison}"))
        except discord.Forbidden:
            pass

        await member.kick(reason=raison)
        await ctx.send(embed=success_embed("Kick", f"**{member}** a été expulsé.\nRaison : {raison}"))

    # ── Ban ──────────────────────────────────────────────────────────────────

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, raison: str = "Aucune raison fournie"):
        """Bannit un membre du serveur.\nUsage : `!ban @membre [raison]`"""
        if member == ctx.author:
            return await ctx.send(embed=error_embed("Erreur", "Tu ne peux pas te bannir toi-même."))
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=error_embed("Erreur", "Tu ne peux pas bannir quelqu'un avec un rôle supérieur ou égal au tien."))

        try:
            await member.send(embed=info_embed("Banni", f"Tu as été banni de **{ctx.guild.name}**.\nRaison : {raison}"))
        except discord.Forbidden:
            pass

        await member.ban(reason=raison, delete_message_days=1)
        await ctx.send(embed=success_embed("Ban", f"**{member}** a été banni.\nRaison : {raison}"))

    # ── Unban ────────────────────────────────────────────────────────────────

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int):
        """Débannit un membre via son ID.\nUsage : `!unban <id>`"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user)
            await ctx.send(embed=success_embed("Unban", f"**{user}** a été débanni."))
        except discord.NotFound:
            await ctx.send(embed=error_embed("Erreur", "Utilisateur non trouvé ou pas banni."))

    # ── Mute ─────────────────────────────────────────────────────────────────

    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, durée: str = None, *, raison: str = "Aucune raison fournie"):
        """Mute un membre (optionnel : durée ex. `10m`, `1h`, `2d`).\nUsage : `!mute @membre [durée] [raison]`"""
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        # Création du rôle Muted s'il n'existe pas
        if not muted_role:
            muted_role = await ctx.guild.create_role(name="Muted", reason="Création auto pour mute")
            for channel in ctx.guild.channels:
                await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)

        if muted_role in member.roles:
            return await ctx.send(embed=error_embed("Erreur", f"**{member}** est déjà muté."))

        await member.add_roles(muted_role, reason=raison)

        # Parsing de la durée
        duration_text = "Indéfini"
        if durée:
            seconds = self._parse_duration(durée)
            if seconds:
                end_time = datetime.utcnow() + timedelta(seconds=seconds)
                self.muted_users[(ctx.guild.id, member.id)] = end_time
                duration_text = durée

        try:
            await member.send(embed=info_embed("Muté", f"Tu as été muté sur **{ctx.guild.name}**.\nDurée : {duration_text}\nRaison : {raison}"))
        except discord.Forbidden:
            pass

        await ctx.send(embed=success_embed("Mute", f"**{member}** a été muté.\nDurée : {duration_text}\nRaison : {raison}"))

    @commands.command(name="unmute")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member):
        """Unmute un membre.\nUsage : `!unmute @membre`"""
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not muted_role or muted_role not in member.roles:
            return await ctx.send(embed=error_embed("Erreur", f"**{member}** n'est pas muté."))

        await member.remove_roles(muted_role)
        self.muted_users.pop((ctx.guild.id, member.id), None)
        await ctx.send(embed=success_embed("Unmute", f"**{member}** a été unmuté."))

    def _parse_duration(self, duration_str: str) -> int | None:
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if duration_str[-1] in units:
            try:
                return int(duration_str[:-1]) * units[duration_str[-1]]
            except ValueError:
                return None
        return None

    # ── Clear ─────────────────────────────────────────────────────────────────

    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, nombre: int):
        """Supprime un nombre de messages.\nUsage : `!clear <nombre>`"""
        if nombre < 1 or nombre > 100:
            return await ctx.send(embed=error_embed("Erreur", "Le nombre doit être entre 1 et 100."))
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=nombre)
        msg = await ctx.send(embed=success_embed("Clear", f"**{len(deleted)}** messages supprimés."))
        await asyncio.sleep(3)
        await msg.delete()

    # ── Warn ─────────────────────────────────────────────────────────────────

    @commands.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, raison: str = "Aucune raison fournie"):
        """Avertit un membre.\nUsage : `!warn @membre [raison]`"""
        warns = load_warns()
        guild_id = str(ctx.guild.id)
        user_id = str(member.id)

        warns.setdefault(guild_id, {}).setdefault(user_id, [])
        warns[guild_id][user_id].append({
            "raison": raison,
            "par": str(ctx.author),
            "date": datetime.utcnow().strftime("%d/%m/%Y %H:%M")
        })
        save_warns(warns)

        count = len(warns[guild_id][user_id])
        try:
            await member.send(embed=info_embed("Avertissement", f"Tu as reçu un avertissement sur **{ctx.guild.name}**.\nRaison : {raison}\nTotal warns : {count}"))
        except discord.Forbidden:
            pass

        await ctx.send(embed=success_embed("Warn", f"**{member}** a reçu un avertissement ({count} au total).\nRaison : {raison}"))

    @commands.command(name="warnings", aliases=["warns"])
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        """Affiche les avertissements d'un membre.\nUsage : `!warnings @membre`"""
        warns = load_warns()
        guild_id = str(ctx.guild.id)
        user_id = str(member.id)
        user_warns = warns.get(guild_id, {}).get(user_id, [])

        if not user_warns:
            return await ctx.send(embed=info_embed("Warnings", f"**{member}** n'a aucun avertissement."))

        embed = discord.Embed(title=f"⚠️ Warnings de {member}", color=0xF39C12)
        for i, w in enumerate(user_warns, 1):
            embed.add_field(
                name=f"Warn #{i} — {w['date']}",
                value=f"Raison : {w['raison']}\nPar : {w['par']}",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="clearwarns")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, member: discord.Member):
        """Supprime tous les warns d'un membre.\nUsage : `!clearwarns @membre`"""
        warns = load_warns()
        guild_id = str(ctx.guild.id)
        user_id = str(member.id)
        warns.get(guild_id, {}).pop(user_id, None)
        save_warns(warns)
        await ctx.send(embed=success_embed("Clear Warns", f"Tous les warns de **{member}** ont été supprimés."))

    # ── Slowmode ──────────────────────────────────────────────────────────────

    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, secondes: int):
        """Active le slowmode sur ce salon.\nUsage : `!slowmode <secondes>` (0 pour désactiver)"""
        if secondes < 0 or secondes > 21600:
            return await ctx.send(embed=error_embed("Erreur", "Durée invalide (0 - 21600 secondes)."))
        await ctx.channel.edit(slowmode_delay=secondes)
        if secondes == 0:
            await ctx.send(embed=success_embed("Slowmode", "Slowmode désactivé."))
        else:
            await ctx.send(embed=success_embed("Slowmode", f"Slowmode activé : **{secondes}s** par message."))

    # ── Lock / Unlock ─────────────────────────────────────────────────────────

    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        """Verrouille le salon actuel.\nUsage : `!lock`"""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=success_embed("Lock", f"🔒 Le salon **{ctx.channel.name}** est verrouillé."))

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        """Déverrouille le salon actuel.\nUsage : `!unlock`"""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=success_embed("Unlock", f"🔓 Le salon **{ctx.channel.name}** est déverrouillé."))


async def setup(bot):
    await bot.add_cog(Moderation(bot))
