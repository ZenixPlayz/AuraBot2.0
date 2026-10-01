import os, asyncio, random, sqlite3, time, datetime, html, ast, operator as op, platform
from collections import deque

import aiohttp
import tempfile
from gtts import gTTS
import discord
import yt_dlp
import imageio_ffmpeg
from aiohttp import web
from discord import app_commands
from discord.ext import commands

# ================== SETUP ==================
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
START = time.time()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class Bot(commands.Bot):
    async def setup_hook(self):
        self.add_view(TicketView())
        self.add_view(CloseView())
        if os.getenv("PORT"):  # Web Service ke liye (Background Worker me zarurat nahi)
            app = web.Application()
            app.router.add_get("/", lambda r: web.Response(text="Bot zinda hai!"))
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", int(os.environ["PORT"])).start()
        await self.tree.sync()


bot = Bot(command_prefix="!", intents=intents, help_command=None)
cmd = lambda name, desc: bot.tree.command(name=name, description=desc)


def emb(title, desc=None, color=0x5865F2):
    return discord.Embed(title=title, description=desc, color=color)


def fmt(s):
    s = int(s or 0)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ================== DATABASE ==================
db = sqlite3.connect("bot.db", check_same_thread=False)
db.executescript("""
CREATE TABLE IF NOT EXISTS users(g INT, u INT, coins INT DEFAULT 100, xp INT DEFAULT 0,
  last_daily REAL DEFAULT 0, last_work REAL DEFAULT 0, PRIMARY KEY(g,u));
CREATE TABLE IF NOT EXISTS warns(id INTEGER PRIMARY KEY AUTOINCREMENT, g INT, u INT, mod INT, reason TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS settings(g INT, k TEXT, v TEXT, PRIMARY KEY(g,k));
""")
db.commit()


def getu(g, u):
    db.execute("INSERT OR IGNORE INTO users(g,u) VALUES(?,?)", (g, u))
    return db.execute("SELECT coins,xp,last_daily,last_work FROM users WHERE g=? AND u=?", (g, u)).fetchone()


def addc(g, u, n):
    getu(g, u)
    db.execute("UPDATE users SET coins=MAX(0,coins+?) WHERE g=? AND u=?", (n, g, u))
    db.commit()


def addxp(g, u, n):
    getu(g, u)
    db.execute("UPDATE users SET xp=xp+? WHERE g=? AND u=?", (n, g, u))
    db.commit()


def setcol(g, u, col, val):
    assert col in ("last_daily", "last_work")
    db.execute(f"UPDATE users SET {col}=? WHERE g=? AND u=?", (val, g, u))
    db.commit()


def get_set(g, k):
    r = db.execute("SELECT v FROM settings WHERE g=? AND k=?", (g, k)).fetchone()
    return int(r[0]) if r else None


def set_set(g, k, v):
    db.execute("INSERT OR REPLACE INTO settings(g,k,v) VALUES(?,?,?)", (g, k, str(v)))
    db.commit()


def level_of(xp):
    return int((xp / 100) ** 0.5)


async def send_log(guild, e):
    cid = get_set(guild.id, "log")
    ch = guild.get_channel(cid) if cid else None
    if ch:
        try:
            await ch.send(embed=e)
        except discord.HTTPException:
            pass


def can_act(i, m):
    if m.id == i.guild.owner_id or m == i.guild.me:
        return False
    if i.user.id == i.guild.owner_id:
        return True
    return m.top_role < i.user.top_role


# ================== EVENTS ==================
xp_cd = {}


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help | /play"))
    print(f"{bot.user} online hai! Servers: {len(bot.guilds)}")


@bot.event
async def on_member_join(m):
    rid = get_set(m.guild.id, "autorole")
    role = m.guild.get_role(rid) if rid else None
    if role:
        try:
            await m.add_roles(role)
        except discord.HTTPException:
            pass
    cid = get_set(m.guild.id, "welcome")
    ch = m.guild.get_channel(cid) if cid else None
    if ch:
        e = emb("🎉 Naya member!", f"{m.mention} **{m.guild.name}** me aapka swagat hai!\nAb hum **{m.guild.member_count}** log hain.", 0x57F287)
        e.set_thumbnail(url=m.display_avatar.url)
        await ch.send(embed=e)


@bot.event
async def on_member_remove(m):
    cid = get_set(m.guild.id, "welcome")
    ch = m.guild.get_channel(cid) if cid else None
    if ch:
        await ch.send(embed=emb("👋 Alvida", f"**{m}** server chhod gaya.", 0xED4245))


@bot.event
async def on_message(msg):
    if msg.author.bot or not msg.guild:
        return
    k = (msg.guild.id, msg.author.id)
    if time.time() - xp_cd.get(k, 0) >= 60:
        xp_cd[k] = time.time()
        before = level_of(getu(*k)[1])
        addxp(*k, random.randint(15, 25))
        after = level_of(getu(*k)[1])
        if after > before:
            addc(*k, after * 50)
            await msg.channel.send(f"🆙 {msg.author.mention} level **{after}** pe pahunch gaya! (+{after*50} coins)")


@bot.event
async def on_message_delete(msg):
    if msg.guild and not msg.author.bot:
        e = emb("🗑️ Message delete", f"**User:** {msg.author.mention}\n**Channel:** {msg.channel.mention}\n**Message:** {msg.content[:1000] or '(embed/file)'}", 0xED4245)
        await send_log(msg.guild, e)


@bot.event
async def on_message_edit(a, b):
    if a.guild and not a.author.bot and a.content != b.content:
        e = emb("✏️ Message edit", f"**User:** {a.author.mention}\n**Channel:** {a.channel.mention}\n**Pehle:** {a.content[:500]}\n**Baad me:** {b.content[:500]}", 0xFEE75C)
        await send_log(a.guild, e)


@bot.event
async def on_voice_state_update(member, before, after):
    vc = member.guild.voice_client
    if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
        await asyncio.sleep(60)
        vc = member.guild.voice_client
        if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
            players.pop(member.guild.id, None)
            await vc.disconnect()


@bot.tree.error
async def on_tree_error(i, e):
    if isinstance(e, app_commands.MissingPermissions):
        msg = "❌ Tumhare paas iski permission nahi hai."
    elif isinstance(e, app_commands.BotMissingPermissions):
        msg = "❌ Bot ke paas permission nahi hai. Bot ko role/permission do."
    else:
        msg = f"⚠️ Error: {e}"
    if i.response.is_done():
        await i.followup.send(msg, ephemeral=True)
    else:
        await i.response.send_message(msg, ephemeral=True)


# ================== HELP ==================
HELP_CATS = {
    "🛡️ Moderation": ["kick", "ban", "unban", "timeout", "untimeout", "clear", "warn", "warnings", "clearwarns", "slowmode", "lock", "unlock", "nick", "addrole", "removerole"],
    "🎵 Music & Voice": ["play", "join", "pause", "resume", "skip", "stop", "queue", "nowplaying", "volume", "loop", "shuffle", "remove", "clearqueue", "leave", "tts"],
    "💰 Economy": ["balance", "daily", "work", "gamble", "slots", "give", "leaderboard"],
    "📈 Level": ["rank", "top"],
    "🎮 Fun": ["8ball", "joke", "dice", "coinflip", "rps", "choose", "ship", "rate", "hug", "slap", "reverse", "meme", "trivia"],
    "🧰 Utility": ["help", "ping", "userinfo", "serverinfo", "avatar", "poll", "remind", "say", "calc", "botinfo"],
    "⚙️ Setup": ["setwelcome", "setautorole", "setlog", "ticketpanel"],
}


def help_cats():
    cmds = {c.name: c.description for c in bot.tree.get_commands()}
    cats = {k: [n for n in v if n in cmds] for k, v in HELP_CATS.items()}
    used = {n for v in cats.values() for n in v}
    rest = [n for n in cmds if n not in used]
    if rest:
        cats["📦 Other"] = rest
    return cmds, cats


def help_embed(key="home"):
    cmds, cats = help_cats()
    if key == "home":
        e = emb("📖 Bot Help", f"Total **{len(cmds)}** commands.\nNeeche menu se category chuno, ya **Sab commands** dekho.")
        for k, v in cats.items():
            e.add_field(name=k, value=f"{len(v)} commands")
        return e
    if key == "all":
        txt = "\n".join(f"**{k}**\n" + " ".join(f"`/{n}`" for n in v) for k, v in cats.items())
        return emb(f"📜 Sab {len(cmds)} commands", txt)
    return emb(key, "\n".join(f"`/{n}` — {cmds[n]}" for n in cats[key]))


class HelpView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=180)
        self.uid = uid
        _, cats = help_cats()
        opts = [discord.SelectOption(label="🏠 Home", value="home"), discord.SelectOption(label="📜 Sab commands", value="all")]
        opts += [discord.SelectOption(label=k, value=k) for k in cats]
        sel = discord.ui.Select(placeholder="Category chuno...", options=opts)
        sel.callback = self.pick
        self.add_item(sel)

    async def pick(self, i: discord.Interaction):
        if i.user.id != self.uid:
            return await i.response.send_message("Apna /help khud kholo 🙂", ephemeral=True)
        await i.response.edit_message(embed=help_embed(i.data["values"][0]), view=self)


@cmd("help", "Saari commands ki list")
async def c_help(i: discord.Interaction):
    await i.response.send_message(embed=help_embed("all"), view=HelpView(i.user.id))


# ================== MODERATION ==================
@cmd("kick", "Member ko kick karo")
@app_commands.guild_only()
@app_commands.default_permissions(kick_members=True)
@app_commands.checks.has_permissions(kick_members=True)
async def c_kick(i: discord.Interaction, member: discord.Member, reason: str = "Koi reason nahi"):
    if not can_act(i, member):
        return await i.response.send_message("❌ Is member pe action nahi le sakte.", ephemeral=True)
    await member.kick(reason=reason)
    await i.response.send_message(embed=emb("👢 Kick", f"{member} ko kick kiya.\n**Reason:** {reason}", 0xFEE75C))


@cmd("ban", "Member ko ban karo")
@app_commands.guild_only()
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.has_permissions(ban_members=True)
async def c_ban(i: discord.Interaction, member: discord.Member, reason: str = "Koi reason nahi"):
    if not can_act(i, member):
        return await i.response.send_message("❌ Is member pe action nahi le sakte.", ephemeral=True)
    await member.ban(reason=reason)
    await i.response.send_message(embed=emb("🔨 Ban", f"{member} ban ho gaya.\n**Reason:** {reason}", 0xED4245))


@cmd("unban", "User ko unban karo (user ID do)")
@app_commands.guild_only()
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.has_permissions(ban_members=True)
async def c_unban(i: discord.Interaction, user_id: str):
    try:
        await i.guild.unban(discord.Object(id=int(user_id)))
        await i.response.send_message(embed=emb("✅ Unban", f"<@{user_id}> unban ho gaya.", 0x57F287))
    except Exception:
        await i.response.send_message("❌ User ID galat hai ya banned nahi hai.", ephemeral=True)


@cmd("timeout", "Member ko timeout (mute) do")
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def c_timeout(i: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "Koi reason nahi"):
    if not can_act(i, member):
        return await i.response.send_message("❌ Is member pe action nahi le sakte.", ephemeral=True)
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    await i.response.send_message(embed=emb("⏳ Timeout", f"{member.mention} **{minutes}** minute ke liye mute.\n**Reason:** {reason}", 0xFEE75C))


@cmd("untimeout", "Timeout hatao")
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def c_untimeout(i: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await i.response.send_message(embed=emb("✅ Timeout hata", f"{member.mention} ab bol sakta hai.", 0x57F287))


@cmd("clear", "Messages delete karo")
@app_commands.guild_only()
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
async def c_clear(i: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await i.response.defer(ephemeral=True)
    d = await i.channel.purge(limit=amount)
    await i.followup.send(f"🧹 {len(d)} messages delete hue.", ephemeral=True)


@cmd("warn", "Member ko warning do")
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def c_warn(i: discord.Interaction, member: discord.Member, reason: str = "Koi reason nahi"):
    db.execute("INSERT INTO warns(g,u,mod,reason,ts) VALUES(?,?,?,?,?)", (i.guild_id, member.id, i.user.id, reason, time.time()))
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM warns WHERE g=? AND u=?", (i.guild_id, member.id)).fetchone()[0]
    await i.response.send_message(embed=emb("⚠️ Warning", f"{member.mention} ko warn kiya. (Total: **{n}**)\n**Reason:** {reason}", 0xFEE75C))
    try:
        await member.send(f"⚠️ **{i.guild.name}** me tumhe warning mili: {reason}")
    except discord.HTTPException:
        pass


@cmd("warnings", "Member ki warnings dekho")
@app_commands.guild_only()
async def c_warnings(i: discord.Interaction, member: discord.Member):
    rows = db.execute("SELECT id,reason,ts FROM warns WHERE g=? AND u=? ORDER BY id DESC LIMIT 10", (i.guild_id, member.id)).fetchall()
    if not rows:
        return await i.response.send_message(f"{member} ki koi warning nahi hai. ✅")
    txt = "\n".join(f"`#{r[0]}` <t:{int(r[2])}:R> — {r[1]}" for r in rows)
    await i.response.send_message(embed=emb(f"⚠️ {member} ki warnings", txt))


@cmd("clearwarns", "Member ki saari warnings hatao")
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.has_permissions(moderate_members=True)
async def c_clearwarns(i: discord.Interaction, member: discord.Member):
    db.execute("DELETE FROM warns WHERE g=? AND u=?", (i.guild_id, member.id))
    db.commit()
    await i.response.send_message(f"✅ {member.mention} ki warnings clear.")


@cmd("slowmode", "Channel slowmode set karo (0 = off)")
@app_commands.guild_only()
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def c_slowmode(i: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
    await i.channel.edit(slowmode_delay=seconds)
    await i.response.send_message(f"🐌 Slowmode: **{seconds}s**")


@cmd("lock", "Channel lock karo")
@app_commands.guild_only()
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def c_lock(i: discord.Interaction):
    ow = i.channel.overwrites_for(i.guild.default_role)
    ow.send_messages = False
    await i.channel.set_permissions(i.guild.default_role, overwrite=ow)
    await i.response.send_message("🔒 Channel lock ho gaya.")


@cmd("unlock", "Channel unlock karo")
@app_commands.guild_only()
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
async def c_unlock(i: discord.Interaction):
    ow = i.channel.overwrites_for(i.guild.default_role)
    ow.send_messages = None
    await i.channel.set_permissions(i.guild.default_role, overwrite=ow)
    await i.response.send_message("🔓 Channel unlock ho gaya.")


@cmd("nick", "Member ka nickname badlo")
@app_commands.guild_only()
@app_commands.default_permissions(manage_nicknames=True)
@app_commands.checks.has_permissions(manage_nicknames=True)
async def c_nick(i: discord.Interaction, member: discord.Member, nickname: str = None):
    if not can_act(i, member):
        return await i.response.send_message("❌ Is member pe action nahi le sakte.", ephemeral=True)
    await member.edit(nick=nickname)
    await i.response.send_message(f"✅ Nickname badal gaya: **{nickname or 'reset'}**")


@cmd("addrole", "Member ko role do")
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
@app_commands.checks.has_permissions(manage_roles=True)
async def c_addrole(i: discord.Interaction, member: discord.Member, role: discord.Role):
    if role >= i.guild.me.top_role or (role >= i.user.top_role and i.user.id != i.guild.owner_id):
        return await i.response.send_message("❌ Ye role tum/bot nahi de sakte.", ephemeral=True)
    await member.add_roles(role)
    await i.response.send_message(f"✅ {member.mention} ko {role.mention} mila.", allowed_mentions=discord.AllowedMentions.none())


@cmd("removerole", "Member se role hatao")
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
@app_commands.checks.has_permissions(manage_roles=True)
async def c_removerole(i: discord.Interaction, member: discord.Member, role: discord.Role):
    if role >= i.guild.me.top_role or (role >= i.user.top_role and i.user.id != i.guild.owner_id):
        return await i.response.send_message("❌ Ye role tum/bot nahi hata sakte.", ephemeral=True)
    await member.remove_roles(role)
    await i.response.send_message(f"✅ {member.mention} se {role.mention} hata diya.", allowed_mentions=discord.AllowedMentions.none())


# ================== MUSIC ==================
YDL_OPTS = {"format": "bestaudio/best", "noplaylist": True, "quiet": True, "no_warnings": True,
            "default_search": "ytsearch", "source_address": "0.0.0.0"}


class Player:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.loop = False
        self.volume = 0.5
        self.text = None


players = {}


def gp(gid):
    return players.setdefault(gid, Player())


async def extract(query):
    def run():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = info["entries"][0]
            return {"title": info.get("title", "Unknown"), "url": info["url"],
                    "webpage": info.get("webpage_url") or query, "duration": info.get("duration", 0),
                    "thumb": info.get("thumbnail"), "by": None}
    return await asyncio.get_running_loop().run_in_executor(None, run)


async def advance(guild):
    p = gp(guild.id)
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return
    if p.loop and p.current:
        nxt = p.current
    elif p.queue:
        nxt = p.queue.popleft()
    else:
        p.current = None
        return
    try:
        data = await extract(nxt["webpage"])
        data["by"] = nxt.get("by")
    except Exception as e:
        p.current = None
        if p.text:
            await p.text.send(f"⚠️ **{nxt['title']}** play nahi ho paya: `{str(e)[:150]}`")
        return await advance(guild)
    p.current = data
    src = discord.FFmpegOpusAudio(
        data["url"], executable=FFMPEG,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options=f"-vn -filter:a volume={p.volume}")
    vc.play(src, after=lambda err: asyncio.run_coroutine_threadsafe(advance(guild), bot.loop))
    if p.text:
        e = emb("🎶 Ab chal raha hai", f"**[{data['title']}]({data['webpage']})**\n⏱️ {fmt(data['duration'])}", 0x1DB954)
        if data["thumb"]:
            e.set_thumbnail(url=data["thumb"])
        await p.text.send(embed=e)


async def need_vc(i):
    """User voice me ho to bot ko join karwao, nahi to None."""
    if not i.user.voice or not i.user.voice.channel:
        msg = "🎧 Pehle kisi voice channel me join karo!"
        if i.response.is_done():
            await i.followup.send(msg, ephemeral=True)
        else:
            await i.response.send_message(msg, ephemeral=True)
        return None
    vc = i.guild.voice_client
    if not vc:
        vc = await i.user.voice.channel.connect(self_deaf=True)
    elif vc.channel != i.user.voice.channel:
        await vc.move_to(i.user.voice.channel)
    return vc


@cmd("play", "Gaana chalao (naam ya YouTube/Spotify-title link)")
@app_commands.guild_only()
async def c_play(i: discord.Interaction, song: str):
    if not i.user.voice or not i.user.voice.channel:
        return await i.response.send_message("🎧 Pehle kisi voice channel me join karo!", ephemeral=True)
    await i.response.defer()
    vc = await need_vc(i)
    if not vc:
        return
    p = gp(i.guild_id)
    p.text = i.channel
    q = song if song.startswith("http") else f"ytsearch:{song}"
    try:
        data = await extract(q)
    except Exception as e:
        return await i.followup.send(f"❌ Gaana nahi mila / load nahi hua: `{str(e)[:200]}`")
    p.queue.append({"title": data["title"], "webpage": data["webpage"], "duration": data["duration"], "by": i.user.display_name})
    if vc.is_playing() or vc.is_paused():
        await i.followup.send(embed=emb("➕ Queue me add", f"**[{data['title']}]({data['webpage']})**\nPosition: **{len(p.queue)}**", 0x1DB954))
    else:
        await i.followup.send(f"🔎 Mil gaya: **{data['title']}**")
        await advance(i.guild)


@cmd("join", "Bot ko voice channel me bulao")
@app_commands.guild_only()
async def c_join(i: discord.Interaction):
    vc = await need_vc(i)
    if vc:
        await i.response.send_message(f"✅ **{vc.channel.name}** me aa gaya!")


@cmd("pause", "Gaana pause karo")
@app_commands.guild_only()
async def c_pause(i: discord.Interaction):
    vc = i.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await i.response.send_message("⏸️ Pause")
    else:
        await i.response.send_message("Kuch play nahi ho raha.", ephemeral=True)


@cmd("resume", "Gaana resume karo")
@app_commands.guild_only()
async def c_resume(i: discord.Interaction):
    vc = i.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await i.response.send_message("▶️ Resume")
    else:
        await i.response.send_message("Kuch pause nahi hai.", ephemeral=True)


@cmd("skip", "Agla gaana")
@app_commands.guild_only()
async def c_skip(i: discord.Interaction):
    vc = i.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        gp(i.guild_id).current = None
        vc.stop()
        await i.response.send_message("⏭️ Skip")
    else:
        await i.response.send_message("Kuch play nahi ho raha.", ephemeral=True)


@cmd("stop", "Gaana band + queue clear")
@app_commands.guild_only()
async def c_stop(i: discord.Interaction):
    vc = i.guild.voice_client
    p = gp(i.guild_id)
    p.queue.clear()
    p.loop = False
    p.current = None
    if vc:
        vc.stop()
    await i.response.send_message("⏹️ Band kar diya.")


@cmd("leave", "Bot voice channel chhod de")
@app_commands.guild_only()
async def c_leave(i: discord.Interaction):
    vc = i.guild.voice_client
    if vc:
        players.pop(i.guild_id, None)
        await vc.disconnect()
        await i.response.send_message("👋 Bye!")
    else:
        await i.response.send_message("Main voice me nahi hoon.", ephemeral=True)


@cmd("queue", "Queue dekho")
@app_commands.guild_only()
async def c_queue(i: discord.Interaction):
    p = gp(i.guild_id)
    if not p.current and not p.queue:
        return await i.response.send_message("📭 Queue khaali hai.")
    txt = f"**Abhi:** {p.current['title'] if p.current else '-'}\n\n"
    txt += "\n".join(f"`{n}.` {s['title']}" for n, s in enumerate(list(p.queue)[:15], 1))
    if len(p.queue) > 15:
        txt += f"\n...aur {len(p.queue)-15} gaane"
    await i.response.send_message(embed=emb("📜 Queue", txt, 0x1DB954))


@cmd("nowplaying", "Abhi kaunsa gaana chal raha hai")
@app_commands.guild_only()
async def c_np(i: discord.Interaction):
    p = gp(i.guild_id)
    if not p.current:
        return await i.response.send_message("Kuch play nahi ho raha.", ephemeral=True)
    d = p.current
    e = emb("🎶 Now Playing", f"**[{d['title']}]({d['webpage']})**\n⏱️ {fmt(d['duration'])} | 🔁 Loop: {'ON' if p.loop else 'OFF'}", 0x1DB954)
    if d["thumb"]:
        e.set_thumbnail(url=d["thumb"])
    await i.response.send_message(embed=e)


@cmd("volume", "Volume set karo 1-200 (agle gaane se lagega)")
@app_commands.guild_only()
async def c_volume(i: discord.Interaction, percent: app_commands.Range[int, 1, 200]):
    gp(i.guild_id).volume = percent / 100
    await i.response.send_message(f"🔊 Volume **{percent}%** (agle gaane se).")


@cmd("loop", "Current gaana loop on/off")
@app_commands.guild_only()
async def c_loop(i: discord.Interaction):
    p = gp(i.guild_id)
    p.loop = not p.loop
    await i.response.send_message(f"🔁 Loop: **{'ON' if p.loop else 'OFF'}**")


@cmd("shuffle", "Queue shuffle karo")
@app_commands.guild_only()
async def c_shuffle(i: discord.Interaction):
    p = gp(i.guild_id)
    l = list(p.queue)
    random.shuffle(l)
    p.queue = deque(l)
    await i.response.send_message("🔀 Queue shuffle ho gayi.")


@cmd("remove", "Queue se gaana hatao (number do)")
@app_commands.guild_only()
async def c_remove(i: discord.Interaction, number: int):
    p = gp(i.guild_id)
    if 1 <= number <= len(p.queue):
        l = list(p.queue)
        s = l.pop(number - 1)
        p.queue = deque(l)
        await i.response.send_message(f"🗑️ Hata diya: **{s['title']}**")
    else:
        await i.response.send_message("❌ Galat number.", ephemeral=True)


@cmd("clearqueue", "Poori queue clear karo")
@app_commands.guild_only()
async def c_clearqueue(i: discord.Interaction):
    gp(i.guild_id).queue.clear()
    await i.response.send_message("🧹 Queue clear.")



@cmd("tts", "Bot voice channel me tumhara text bolega")
@app_commands.guild_only()
@app_commands.choices(language=[
    app_commands.Choice(name="Hindi", value="hi"), app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Urdu", value="ur"), app_commands.Choice(name="Bengali", value="bn"),
    app_commands.Choice(name="Tamil", value="ta"), app_commands.Choice(name="Telugu", value="te"),
    app_commands.Choice(name="Marathi", value="mr"), app_commands.Choice(name="Gujarati", value="gu"),
    app_commands.Choice(name="Punjabi", value="pa")])
async def c_tts(i: discord.Interaction, text: app_commands.Range[str, 1, 300], language: app_commands.Choice[str] = None):
    if not i.user.voice or not i.user.voice.channel:
        return await i.response.send_message("🎧 Pehle kisi voice channel me join karo!", ephemeral=True)
    await i.response.defer()
    vc = await need_vc(i)
    if not vc:
        return
    if vc.is_playing() or vc.is_paused():
        return await i.followup.send("⏳ Abhi gaana chal raha hai. Pehle `/stop` karo ya khatam hone do.")
    lang = language.value if language else "hi"
    path = os.path.join(tempfile.gettempdir(), f"tts_{i.id}.mp3")
    try:
        await asyncio.get_running_loop().run_in_executor(None, lambda: gTTS(text=text, lang=lang).save(path))
    except Exception as e:
        return await i.followup.send(f"❌ TTS nahi bana: `{str(e)[:150]}`")

    def done(err):
        try:
            os.remove(path)
        except OSError:
            pass
        asyncio.run_coroutine_threadsafe(advance(i.guild), bot.loop)

    vc.play(discord.FFmpegOpusAudio(path, executable=FFMPEG, options="-vn"), after=done)
    await i.followup.send(f"🗣️ **{i.user.display_name}** bola: {text}", allowed_mentions=discord.AllowedMentions.none())


# ================== ECONOMY ==================
@cmd("balance", "Coins dekho")
@app_commands.guild_only()
async def c_balance(i: discord.Interaction, member: discord.Member = None):
    m = member or i.user
    await i.response.send_message(embed=emb("💰 Balance", f"{m.mention} ke paas **{getu(i.guild_id, m.id)[0]:,}** coins hain."))


@cmd("daily", "Roz ke coins lo")
@app_commands.guild_only()
async def c_daily(i: discord.Interaction):
    g, u = i.guild_id, i.user.id
    last = getu(g, u)[2]
    if time.time() - last < 86400:
        return await i.response.send_message(f"⏳ Dobara <t:{int(last+86400)}:R> aana.", ephemeral=True)
    amt = random.randint(200, 500)
    addc(g, u, amt)
    setcol(g, u, "last_daily", time.time())
    await i.response.send_message(f"🎁 Daily me **{amt}** coins mile!")


@cmd("work", "Kaam karke coins kamao")
@app_commands.guild_only()
async def c_work(i: discord.Interaction):
    g, u = i.guild_id, i.user.id
    last = getu(g, u)[3]
    if time.time() - last < 3600:
        return await i.response.send_message(f"⏳ Thak gaye! <t:{int(last+3600)}:R> aana.", ephemeral=True)
    amt = random.randint(50, 200)
    job = random.choice(["chai bechi", "code likha", "delivery ki", "video edit kiya", "gaadi chalayi"])
    addc(g, u, amt)
    setcol(g, u, "last_work", time.time())
    await i.response.send_message(f"💼 Tumne {job} aur **{amt}** coins kamaye!")


@cmd("gamble", "Coins ka jua khelo")
@app_commands.guild_only()
async def c_gamble(i: discord.Interaction, amount: app_commands.Range[int, 1, 1000000]):
    g, u = i.guild_id, i.user.id
    if amount > getu(g, u)[0]:
        return await i.response.send_message("❌ Itne coins nahi hain.", ephemeral=True)
    if random.random() < 0.45:
        addc(g, u, amount)
        await i.response.send_message(f"🎉 Jeet gaye! **+{amount}** coins.")
    else:
        addc(g, u, -amount)
        await i.response.send_message(f"💀 Haar gaye! **-{amount}** coins.")


@cmd("slots", "Slot machine")
@app_commands.guild_only()
async def c_slots(i: discord.Interaction, bet: app_commands.Range[int, 1, 100000]):
    g, u = i.guild_id, i.user.id
    if bet > getu(g, u)[0]:
        return await i.response.send_message("❌ Itne coins nahi hain.", ephemeral=True)
    s = [random.choice("🍒🍋🍉⭐💎7️⃣") for _ in range(3)]
    if len(set(s)) == 1:
        win, t = bet * 5, "🎰 JACKPOT!"
    elif len(set(s)) == 2:
        win, t = bet, "😎 Do match!"
    else:
        win, t = -bet, "😢 Haar gaye."
    addc(g, u, win)
    await i.response.send_message(f"{' | '.join(s)}\n{t} **{win:+}** coins")


@cmd("give", "Kisi ko coins do")
@app_commands.guild_only()
async def c_give(i: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 1000000]):
    if member.bot or member.id == i.user.id:
        return await i.response.send_message("❌ Galat target.", ephemeral=True)
    if amount > getu(i.guild_id, i.user.id)[0]:
        return await i.response.send_message("❌ Itne coins nahi hain.", ephemeral=True)
    addc(i.guild_id, i.user.id, -amount)
    addc(i.guild_id, member.id, amount)
    await i.response.send_message(f"🤝 {i.user.mention} ne {member.mention} ko **{amount}** coins diye.")


@cmd("leaderboard", "Sabse ameer log")
@app_commands.guild_only()
async def c_lb(i: discord.Interaction):
    rows = db.execute("SELECT u,coins FROM users WHERE g=? ORDER BY coins DESC LIMIT 10", (i.guild_id,)).fetchall()
    txt = "\n".join(f"**{n}.** <@{u}> — {c:,} 💰" for n, (u, c) in enumerate(rows, 1)) or "Koi data nahi."
    await i.response.send_message(embed=emb("🏆 Coins Leaderboard", txt, 0xFEE75C), allowed_mentions=discord.AllowedMentions.none())


# ================== LEVELS ==================
@cmd("rank", "Apna level dekho")
@app_commands.guild_only()
async def c_rank(i: discord.Interaction, member: discord.Member = None):
    m = member or i.user
    xp = getu(i.guild_id, m.id)[1]
    lv = level_of(xp)
    lo, hi = lv * lv * 100, (lv + 1) ** 2 * 100
    pct = int((xp - lo) / (hi - lo) * 10)
    bar = "🟩" * pct + "⬜" * (10 - pct)
    e = emb(f"📈 {m.display_name} ka Rank", f"**Level:** {lv}\n**XP:** {xp} / {hi}\n{bar}")
    e.set_thumbnail(url=m.display_avatar.url)
    await i.response.send_message(embed=e)


@cmd("top", "XP leaderboard")
@app_commands.guild_only()
async def c_top(i: discord.Interaction):
    rows = db.execute("SELECT u,xp FROM users WHERE g=? ORDER BY xp DESC LIMIT 10", (i.guild_id,)).fetchall()
    txt = "\n".join(f"**{n}.** <@{u}> — Level {level_of(x)} ({x} XP)" for n, (u, x) in enumerate(rows, 1)) or "Koi data nahi."
    await i.response.send_message(embed=emb("🏆 XP Leaderboard", txt, 0xFEE75C), allowed_mentions=discord.AllowedMentions.none())


# ================== FUN ==================
JOKES = [
    "Teacher: Tum late kyun aaye? Student: Sir, board pe likha tha 'School Ahead, Go Slow'! 😂",
    "Pappu: Mere paas 2 gaaye hain. Dost: Ek do na. Pappu: Nahi, wo dono mere hain. 🐄",
    "Programmer ki biwi: Dudh le aao, agar ande dikhe to 6 le aana. Wo 6 dudh le aaya, kyunki ande the. 🥛",
    "Doctor: Aapko aaram ki zarurat hai. Patient: Par doctor, mera to WiFi hi slow hai! 😅",
    "Bug nahi hai, ye feature hai! 🐛",
    "Exam me Ctrl+C Ctrl+V nahi chalta, par life me chalta hai. 😎",
]
BALL = ["Haan bilkul! ✅", "Pakka nahi, dobara pooch 🤔", "Bilkul nahi ❌", "Lagta hai haan 👍", "Mat pooch yaar 🙈",
        "Sitare haan bol rahe hain ⭐", "Mushkil hai 😕", "100% haan 💯"]


@cmd("8ball", "Magic 8ball se sawal pucho")
async def c_8ball(i: discord.Interaction, question: str):
    await i.response.send_message(f"🎱 **{question}**\n{random.choice(BALL)}")


@cmd("joke", "Ek joke suno")
async def c_joke(i: discord.Interaction):
    await i.response.send_message(random.choice(JOKES))


@cmd("dice", "Pasa phenko")
async def c_dice(i: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6):
    await i.response.send_message(f"🎲 **{random.randint(1, sides)}** (1-{sides})")


@cmd("coinflip", "Sikka uchhalo")
async def c_coin(i: discord.Interaction):
    await i.response.send_message(f"🪙 **{random.choice(['Heads (chhaap)', 'Tails (patt)'])}**")


@cmd("rps", "Rock Paper Scissors")
@app_commands.choices(choice=[app_commands.Choice(name="Rock 🪨", value="rock"),
                              app_commands.Choice(name="Paper 📄", value="paper"),
                              app_commands.Choice(name="Scissors ✂️", value="scissors")])
async def c_rps(i: discord.Interaction, choice: app_commands.Choice[str]):
    b = random.choice(["rock", "paper", "scissors"])
    win = {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
    r = "Draw 🤝" if choice.value == b else ("Tum jeete 🎉" if (choice.value, b) in win else "Bot jeeta 🤖")
    await i.response.send_message(f"Tum: **{choice.value}** | Bot: **{b}**\n{r}")


@cmd("choose", "Options me se chuno (comma se alag karo)")
async def c_choose(i: discord.Interaction, options: str):
    o = [x.strip() for x in options.split(",") if x.strip()]
    if len(o) < 2:
        return await i.response.send_message("❌ Kam se kam 2 options do (comma se).", ephemeral=True)
    await i.response.send_message(f"🤔 Mera pick: **{random.choice(o)}**")


@cmd("ship", "Do logon ka love meter")
async def c_ship(i: discord.Interaction, a: discord.Member, b: discord.Member = None):
    b = b or i.user
    pct = (a.id + b.id) % 101
    bar = "❤️" * (pct // 10) + "🖤" * (10 - pct // 10)
    await i.response.send_message(f"💘 **{a.display_name}** x **{b.display_name}**\n{bar} **{pct}%**")


@cmd("rate", "Kisi cheez ko rate karo")
async def c_rate(i: discord.Interaction, thing: str):
    await i.response.send_message(f"⭐ **{thing}** ko main deta hoon **{random.randint(0, 10)}/10**")


@cmd("hug", "Kisi ko hug do")
async def c_hug(i: discord.Interaction, member: discord.Member):
    await i.response.send_message(f"🤗 {i.user.mention} ne {member.mention} ko tight hug diya!")


@cmd("slap", "Kisi ko thappad maaro")
async def c_slap(i: discord.Interaction, member: discord.Member):
    await i.response.send_message(f"👋 {i.user.mention} ne {member.mention} ko thappad maara! Chhapaak!")


@cmd("reverse", "Text ulta karo")
async def c_reverse(i: discord.Interaction, text: str):
    await i.response.send_message(text[::-1][:1900], allowed_mentions=discord.AllowedMentions.none())


@cmd("meme", "Random meme")
async def c_meme(i: discord.Interaction):
    await i.response.defer()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://meme-api.com/gimme", timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
        e = emb(d["title"][:250])
        e.set_image(url=d["url"])
        await i.followup.send(embed=e)
    except Exception:
        await i.followup.send("😢 Meme abhi nahi mila, baad me try karo.")


class TriviaView(discord.ui.View):
    def __init__(self, user, options, correct):
        super().__init__(timeout=25)
        self.user, self.correct = user, correct
        for o in options:
            b = discord.ui.Button(label=o[:80], style=discord.ButtonStyle.primary)
            b.callback = self.make(o)
            self.add_item(b)

    def make(self, o):
        async def cb(i: discord.Interaction):
            if i.user.id != self.user.id:
                return await i.response.send_message("Ye tumhara sawal nahi hai!", ephemeral=True)
            ok = o == self.correct
            if ok:
                addc(i.guild_id, i.user.id, 50)
            for c in self.children:
                c.disabled = True
            await i.response.edit_message(content=("✅ Sahi jawab! **+50** coins" if ok else f"❌ Galat! Sahi jawab: **{self.correct}**"), view=self)
            self.stop()
        return cb


@cmd("trivia", "Quiz khelo, sahi pe 50 coins")
@app_commands.guild_only()
async def c_trivia(i: discord.Interaction):
    await i.response.defer()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://opentdb.com/api.php?amount=1&type=multiple", timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = (await r.json())["results"][0]
        q = html.unescape(d["question"])
        correct = html.unescape(d["correct_answer"])
        opts = [html.unescape(x) for x in d["incorrect_answers"]] + [correct]
        random.shuffle(opts)
        await i.followup.send(f"❓ **{q}**", view=TriviaView(i.user, opts, correct))
    except Exception:
        await i.followup.send("😢 Quiz abhi load nahi hua.")


# ================== UTILITY ==================
OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow,
       ast.Mod: op.mod, ast.USub: op.neg, ast.FloorDiv: op.floordiv}


def safe(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp):
        if isinstance(n.op, ast.Pow) and abs(safe(n.right)) > 100:
            raise ValueError
        return OPS[type(n.op)](safe(n.left), safe(n.right))
    if isinstance(n, ast.UnaryOp):
        return OPS[type(n.op)](safe(n.operand))
    raise ValueError


@cmd("ping", "Bot ki speed")
async def c_ping(i: discord.Interaction):
    await i.response.send_message(f"🏓 Pong! **{round(bot.latency*1000)}ms**")


@cmd("userinfo", "User ki info")
@app_commands.guild_only()
async def c_userinfo(i: discord.Interaction, member: discord.Member = None):
    m = member or i.user
    e = emb(f"👤 {m}", color=m.color.value or 0x5865F2)
    e.set_thumbnail(url=m.display_avatar.url)
    e.add_field(name="ID", value=m.id)
    e.add_field(name="Account bana", value=f"<t:{int(m.created_at.timestamp())}:R>")
    e.add_field(name="Server join", value=f"<t:{int(m.joined_at.timestamp())}:R>")
    e.add_field(name="Top role", value=m.top_role.mention)
    await i.response.send_message(embed=e)


@cmd("serverinfo", "Server ki info")
@app_commands.guild_only()
async def c_serverinfo(i: discord.Interaction):
    g = i.guild
    e = emb(f"🏠 {g.name}")
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="Owner", value=f"<@{g.owner_id}>")
    e.add_field(name="Members", value=g.member_count)
    e.add_field(name="Channels", value=len(g.channels))
    e.add_field(name="Roles", value=len(g.roles))
    e.add_field(name="Boosts", value=g.premium_subscription_count)
    e.add_field(name="Bana", value=f"<t:{int(g.created_at.timestamp())}:R>")
    await i.response.send_message(embed=e)


@cmd("avatar", "Profile photo dekho")
async def c_avatar(i: discord.Interaction, member: discord.Member = None):
    m = member or i.user
    e = emb(f"🖼️ {m.display_name}")
    e.set_image(url=m.display_avatar.url)
    await i.response.send_message(embed=e)


@cmd("poll", "Poll banao (options comma se alag, max 10)")
@app_commands.guild_only()
async def c_poll(i: discord.Interaction, question: str, options: str):
    o = [x.strip() for x in options.split(",") if x.strip()][:10]
    if len(o) < 2:
        return await i.response.send_message("❌ Kam se kam 2 options do (comma se).", ephemeral=True)
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    await i.response.send_message(embed=emb(f"📊 {question}", "\n".join(f"{nums[n]} {t}" for n, t in enumerate(o))))
    m = await i.original_response()
    for n in range(len(o)):
        await m.add_reaction(nums[n])


@cmd("remind", "Yaad dilao (minutes me)")
async def c_remind(i: discord.Interaction, minutes: app_commands.Range[int, 1, 1440], text: str):
    await i.response.send_message(f"⏰ Theek hai, **{minutes}** minute baad yaad dilaunga.")

    async def later():
        await asyncio.sleep(minutes * 60)
        await i.channel.send(f"⏰ {i.user.mention} yaad dilaya: **{text}**")
    asyncio.create_task(later())


@cmd("say", "Bot se kuch bulwao")
@app_commands.guild_only()
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
async def c_say(i: discord.Interaction, text: str):
    await i.response.send_message("✅", ephemeral=True)
    await i.channel.send(text, allowed_mentions=discord.AllowedMentions.none())


@cmd("calc", "Calculator")
async def c_calc(i: discord.Interaction, expression: str):
    try:
        r = safe(ast.parse(expression, mode="eval").body)
        await i.response.send_message(f"🧮 `{expression}` = **{r}**")
    except Exception:
        await i.response.send_message("❌ Galat expression. Example: `(5+3)*2`", ephemeral=True)


@cmd("botinfo", "Bot ki info")
async def c_botinfo(i: discord.Interaction):
    up = int(time.time() - START)
    e = emb("🤖 Bot Info")
    e.add_field(name="Servers", value=len(bot.guilds))
    e.add_field(name="Users", value=sum(g.member_count or 0 for g in bot.guilds))
    e.add_field(name="Uptime", value=fmt(up))
    e.add_field(name="Ping", value=f"{round(bot.latency*1000)}ms")
    e.add_field(name="Python", value=platform.python_version())
    e.add_field(name="discord.py", value=discord.__version__)
    await i.response.send_message(embed=e)


# ================== SETUP / TICKETS ==================
@cmd("setwelcome", "Welcome/goodbye channel set karo")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def c_setwelcome(i: discord.Interaction, channel: discord.TextChannel):
    set_set(i.guild_id, "welcome", channel.id)
    await i.response.send_message(f"✅ Welcome channel: {channel.mention}")


@cmd("setautorole", "Naye members ko auto role do")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def c_setautorole(i: discord.Interaction, role: discord.Role):
    set_set(i.guild_id, "autorole", role.id)
    await i.response.send_message(f"✅ Auto role: {role.mention}", allowed_mentions=discord.AllowedMentions.none())


@cmd("setlog", "Log channel set karo (delete/edit logs)")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def c_setlog(i: discord.Interaction, channel: discord.TextChannel):
    set_set(i.guild_id, "log", channel.id)
    await i.response.send_message(f"✅ Log channel: {channel.mention}")


class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket band karo", emoji="🔒", style=discord.ButtonStyle.red, custom_id="ticket_close")
    async def close(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_message("🔒 5 second me ticket delete hoga...")
        await asyncio.sleep(5)
        await i.channel.delete()


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket kholo", emoji="🎫", style=discord.ButtonStyle.green, custom_id="ticket_open")
    async def open(self, i: discord.Interaction, b: discord.ui.Button):
        g = i.guild
        name = f"ticket-{i.user.id}"
        if discord.utils.get(g.text_channels, name=name):
            return await i.response.send_message("❌ Tumhara ticket pehle se khula hai.", ephemeral=True)
        ow = {g.default_role: discord.PermissionOverwrite(view_channel=False),
              i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
              g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)}
        ch = await g.create_text_channel(name, overwrites=ow, category=i.channel.category)
        await ch.send(f"{i.user.mention} apni problem likho, staff jaldi aayega.", view=CloseView())
        await i.response.send_message(f"✅ Ticket bana: {ch.mention}", ephemeral=True)


@cmd("ticketpanel", "Ticket panel bhejo")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def c_ticketpanel(i: discord.Interaction):
    await i.response.send_message("✅ Panel bhej diya.", ephemeral=True)
    await i.channel.send(embed=emb("🎫 Support", "Madad chahiye? Neeche button dabao, private ticket khulega."), view=TicketView())


# ================== RUN ==================
bot.run(os.environ["TOKEN"])
