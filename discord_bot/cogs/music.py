import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque

# ── Options yt-dlp ──────────────────────────────────────────────────────────

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "cookiefile": None,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("webpage_url")
        self.duration = data.get("duration", 0)
        self.thumbnail = data.get("thumbnail")
        self.uploader = data.get("uploader", "Inconnu")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )
        if "entries" in data:
            data = data["entries"][0]
        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

    @staticmethod
    def format_duration(seconds: int) -> str:
        if not seconds:
            return "Live"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ── État de musique par serveur ──────────────────────────────────────────────

class GuildMusicState:
    def __init__(self):
        self.queue: deque = deque()
        self.current: YTDLSource | None = None
        self.volume: float = 0.5
        self.loop: bool = False


# ── Cog Musique ──────────────────────────────────────────────────────────────

class Music(commands.Cog, name="Musique"):
    """Commandes de musique."""

    def __init__(self, bot):
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    def info_embed(self, title, desc, color=0x5865F2):
        return discord.Embed(title=title, description=desc, color=color)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _play_next(self, ctx):
        state = self.get_state(ctx.guild.id)
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return

        if state.loop and state.current:
            # Rejouer la même chanson
            source = await YTDLSource.from_url(state.current.url, loop=self.bot.loop)
            source.volume = state.volume
            state.current = source
        elif state.queue:
            url = state.queue.popleft()
            try:
                source = await YTDLSource.from_url(url, loop=self.bot.loop)
                source.volume = state.volume
                state.current = source
            except Exception as e:
                await ctx.send(f"❌ Erreur lors du chargement : `{e}`")
                return await self._play_next(ctx)
        else:
            state.current = None
            await ctx.send(embed=self.info_embed("🎵 File vide", "La file d'attente est vide. Utilise `!play` pour ajouter une musique."))
            return

        def after_playing(error):
            if error:
                print(f"Erreur lecture : {error}")
            asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop)

        vc.play(state.current, after=after_playing)

        embed = discord.Embed(title="▶️ Lecture en cours", color=0x1DB954)
        embed.add_field(name="🎵 Titre", value=state.current.title, inline=False)
        embed.add_field(name="⏱️ Durée", value=YTDLSource.format_duration(state.current.duration), inline=True)
        embed.add_field(name="👤 Artiste", value=state.current.uploader, inline=True)
        if state.current.thumbnail:
            embed.set_thumbnail(url=state.current.thumbnail)
        embed.set_footer(text=f"Volume : {int(state.volume * 100)}%")
        await ctx.send(embed=embed)

    # ── Join ─────────────────────────────────────────────────────────────────

    @commands.command(name="join")
    async def join(self, ctx):
        """Rejoint ton salon vocal.\nUsage : `!join`"""
        if not ctx.author.voice:
            return await ctx.send("❌ Tu dois être dans un salon vocal.")
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(embed=self.info_embed("✅ Connecté", f"Rejoint **{channel.name}**."))

    # ── Play ─────────────────────────────────────────────────────────────────

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        """Joue une musique depuis YouTube (URL ou recherche).\nUsage : `!play <titre ou URL>`"""
        if not ctx.author.voice:
            return await ctx.send("❌ Tu dois être dans un salon vocal.")

        # Connexion auto
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.voice_client.move_to(ctx.author.voice.channel)

        state = self.get_state(ctx.guild.id)
        vc = ctx.voice_client

        # Recherche YouTube si ce n'est pas une URL
        if not query.startswith("http"):
            query = f"ytsearch:{query}"

        async with ctx.typing():
            try:
                loop = self.bot.loop
                data = await loop.run_in_executor(
                    None, lambda: ytdl.extract_info(query, download=False)
                )
                if "entries" in data:
                    entries = data["entries"]
                else:
                    entries = [data]
            except Exception as e:
                return await ctx.send(f"❌ Impossible de trouver : `{e}`")

        added = []
        for entry in entries:
            url = entry.get("webpage_url") or entry.get("url")
            if url:
                state.queue.append(url)
                added.append(entry.get("title", "Inconnu"))

        if not vc.is_playing() and not vc.is_paused():
            await self._play_next(ctx)
        else:
            if len(added) == 1:
                await ctx.send(embed=self.info_embed("📥 Ajouté à la file", f"**{added[0]}**", color=0xF39C12))
            else:
                await ctx.send(embed=self.info_embed("📥 Playlist ajoutée", f"**{len(added)}** musiques ajoutées à la file.", color=0xF39C12))

    # ── Pause / Resume ────────────────────────────────────────────────────────

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Met la musique en pause.\nUsage : `!pause`"""
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send(embed=self.info_embed("⏸️ Pause", "Musique mise en pause. `!resume` pour reprendre."))
        else:
            await ctx.send("❌ Aucune musique en cours.")

    @commands.command(name="resume")
    async def resume(self, ctx):
        """Reprend la musique après une pause.\nUsage : `!resume`"""
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send(embed=self.info_embed("▶️ Reprise", "Lecture reprise !"))
        else:
            await ctx.send("❌ La musique n'est pas en pause.")

    # ── Skip ─────────────────────────────────────────────────────────────────

    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        """Passe à la musique suivante.\nUsage : `!skip`"""
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await ctx.send(embed=self.info_embed("⏭️ Skip", "Musique passée."))
        else:
            await ctx.send("❌ Aucune musique en cours.")

    # ── Stop ─────────────────────────────────────────────────────────────────

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Arrête la musique et vide la file d'attente.\nUsage : `!stop`"""
        state = self.get_state(ctx.guild.id)
        state.queue.clear()
        state.current = None
        state.loop = False
        vc = ctx.voice_client
        if vc:
            vc.stop()
        await ctx.send(embed=self.info_embed("⏹️ Stop", "Lecture arrêtée et file vidée."))

    # ── Queue ─────────────────────────────────────────────────────────────────

    @commands.command(name="queue", aliases=["q", "file"])
    async def queue(self, ctx):
        """Affiche la file d'attente.\nUsage : `!queue`"""
        state = self.get_state(ctx.guild.id)
        embed = discord.Embed(title="🎶 File d'attente", color=0x5865F2)

        if state.current:
            embed.add_field(name="▶️ En cours", value=state.current.title, inline=False)
        else:
            embed.add_field(name="▶️ En cours", value="Rien", inline=False)

        if state.queue:
            # Résolution des titres depuis yt-dlp si possible (affichage limité)
            queue_list = list(state.queue)[:10]
            desc = "\n".join(f"`{i+1}.` {url}" for i, url in enumerate(queue_list))
            if len(state.queue) > 10:
                desc += f"\n... et {len(state.queue) - 10} autre(s)"
            embed.add_field(name=f"📋 À venir ({len(state.queue)})", value=desc, inline=False)
        else:
            embed.add_field(name="📋 À venir", value="File vide", inline=False)

        embed.set_footer(text=f"Loop : {'✅' if state.loop else '❌'} | Volume : {int(state.volume * 100)}%")
        await ctx.send(embed=embed)

    # ── Volume ────────────────────────────────────────────────────────────────

    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx, vol: int):
        """Règle le volume (0-100).\nUsage : `!volume <0-100>`"""
        if not 0 <= vol <= 100:
            return await ctx.send("❌ Le volume doit être entre 0 et 100.")
        state = self.get_state(ctx.guild.id)
        state.volume = vol / 100
        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = state.volume
        await ctx.send(embed=self.info_embed("🔊 Volume", f"Volume réglé à **{vol}%**."))

    # ── Now Playing ───────────────────────────────────────────────────────────

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Affiche la musique en cours.\nUsage : `!nowplaying`"""
        state = self.get_state(ctx.guild.id)
        if not state.current:
            return await ctx.send("❌ Aucune musique en cours.")
        s = state.current
        embed = discord.Embed(title="🎵 En cours de lecture", color=0x1DB954)
        embed.add_field(name="Titre", value=s.title, inline=False)
        embed.add_field(name="Durée", value=YTDLSource.format_duration(s.duration), inline=True)
        embed.add_field(name="Artiste", value=s.uploader, inline=True)
        embed.add_field(name="URL", value=s.url, inline=False)
        if s.thumbnail:
            embed.set_thumbnail(url=s.thumbnail)
        embed.set_footer(text=f"Volume : {int(state.volume * 100)}% | Loop : {'✅' if state.loop else '❌'}")
        await ctx.send(embed=embed)

    # ── Loop ─────────────────────────────────────────────────────────────────

    @commands.command(name="loop")
    async def loop(self, ctx):
        """Active/désactive la répétition de la musique en cours.\nUsage : `!loop`"""
        state = self.get_state(ctx.guild.id)
        state.loop = not state.loop
        status = "activée ✅" if state.loop else "désactivée ❌"
        await ctx.send(embed=self.info_embed("🔁 Loop", f"Répétition {status}."))

    # ── Leave ─────────────────────────────────────────────────────────────────

    @commands.command(name="leave", aliases=["dc", "disconnect"])
    async def leave(self, ctx):
        """Fait quitter le bot du salon vocal.\nUsage : `!leave`"""
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("❌ Le bot n'est pas dans un salon vocal.")
        state = self.get_state(ctx.guild.id)
        state.queue.clear()
        state.current = None
        await vc.disconnect()
        await ctx.send(embed=self.info_embed("👋 Déconnecté", "Le bot a quitté le salon vocal."))


async def setup(bot):
    await bot.add_cog(Music(bot))
