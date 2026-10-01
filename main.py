import os, re, shlex, secrets, asyncio, random, sqlite3, time, datetime, html, ast, operator as op, platform
from collections import deque

import aiohttp
from urllib.parse import urlencode, urlparse
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
        await start_dashboard()
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
    if m.top_role >= i.guild.me.top_role:
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
    st = tts_state.get(msg.guild.id)
    if st and msg.channel.id == st["channel"] and msg.author.id in st["users"] and msg.clean_content:
        tts_enqueue(msg.guild, msg.clean_content, st["users"][msg.author.id])
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
            tts_state.pop(member.guild.id, None)
            await vc.disconnect()


@bot.tree.error
async def on_tree_error(i, e):
    if isinstance(e, app_commands.MissingPermissions):
        msg = "❌ Tumhare paas iski permission nahi hai."
    elif isinstance(e, app_commands.BotMissingPermissions):
        msg = "❌ Bot ke paas permission nahi hai. Bot ko role/permission do."
    elif isinstance(e, app_commands.NoPrivateMessage):
        msg = "❌ Ye command sirf server me chalta hai."
    elif isinstance(e, app_commands.CheckFailure):
        msg = "🔒 Ye command sirf server founder (owner) use kar sakta hai."
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


def owner_only(i: discord.Interaction) -> bool:
    return bool(i.guild) and i.user.id == i.guild.owner_id


# ================== MODERATION ==================
@cmd("kick", "Member ko kick karo (sirf founder)")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.check(owner_only)
async def c_kick(i: discord.Interaction, member: discord.Member, reason: str = "Koi reason nahi"):
    if not can_act(i, member):
        return await i.response.send_message("❌ Action nahi ho sakta. Bot ka role is member ke role se upar hona chahiye (Server Settings → Roles).", ephemeral=True)
    await member.kick(reason=reason)
    await i.response.send_message(embed=emb("👢 Kick", f"{member} ko kick kiya.\n**Reason:** {reason}", 0xFEE75C))


@cmd("ban", "Member ko ban karo (sirf founder)")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.check(owner_only)
async def c_ban(i: discord.Interaction, member: discord.Member, reason: str = "Koi reason nahi"):
    if not can_act(i, member):
        return await i.response.send_message("❌ Action nahi ho sakta. Bot ka role is member ke role se upar hona chahiye (Server Settings → Roles).", ephemeral=True)
    await member.ban(reason=reason)
    await i.response.send_message(embed=emb("🔨 Ban", f"{member} ban ho gaya.\n**Reason:** {reason}", 0xED4245))


@cmd("unban", "User ko unban karo (user ID do) (sirf founder)")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.check(owner_only)
async def c_unban(i: discord.Interaction, user_id: str):
    try:
        await i.guild.unban(discord.Object(id=int(user_id)))
        await i.response.send_message(embed=emb("✅ Unban", f"<@{user_id}> unban ho gaya.", 0x57F287))
    except Exception:
        await i.response.send_message("❌ User ID galat hai ya banned nahi hai.", ephemeral=True)


@cmd("timeout", "Member ko timeout (mute) do (sirf founder)")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.check(owner_only)
async def c_timeout(i: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "Koi reason nahi"):
    if not can_act(i, member):
        return await i.response.send_message("❌ Action nahi ho sakta. Bot ka role is member ke role se upar hona chahiye (Server Settings → Roles).", ephemeral=True)
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    await i.response.send_message(embed=emb("⏳ Timeout", f"{member.mention} **{minutes}** minute ke liye mute.\n**Reason:** {reason}", 0xFEE75C))


@cmd("untimeout", "Timeout hatao (sirf founder)")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.check(owner_only)
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
        return await i.response.send_message("❌ Action nahi ho sakta. Bot ka role is member ke role se upar hona chahiye (Server Settings → Roles).", ephemeral=True)
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
YDL_OPTS = {"format": "bestaudio[protocol!*=m3u8]/bestaudio/best", "concurrent_fragment_downloads": 4, "noplaylist": True, "quiet": True, "no_warnings": True,
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


async def extract(query, download=False):
    def run(q):
        opts = dict(YDL_OPTS)
        if download:
            opts["outtmpl"] = os.path.join(tempfile.gettempdir(), "song_%(id)s.%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(q, download=download)
            if "entries" in info:
                if not info["entries"]:
                    raise Exception("Kuch nahi mila")
                info = info["entries"][0]
            path = None
            if download:
                rd = info.get("requested_downloads") or []
                path = rd[0]["filepath"] if rd else ydl.prepare_filename(info)
            return {"title": info.get("title", "Unknown"), "url": info.get("url"),
                    "webpage": info.get("webpage_url") or q, "duration": info.get("duration", 0),
                    "thumb": info.get("thumbnail"), "by": None, "file": path}
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, run, query)
    except Exception:
        # YouTube block kare to SoundCloud pe dhundo
        if query.startswith("ytsearch:"):
            return await loop.run_in_executor(None, run, "scsearch:" + query[len("ytsearch:"):])
        raise


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
    data, err = None, ""
    try:
        data = await extract(nxt["webpage"], download=True)
    except Exception as e:
        err = str(e)
        if "youtu" in nxt["webpage"]:
            try:
                data = await extract("scsearch:" + nxt["title"], download=True)
            except Exception:
                pass
    if not data or not data.get("file"):
        p.current = None
        if p.text:
            await p.text.send(f"⚠️ **{nxt['title']}** play nahi ho paya: `{err[:150]}`")
        return await advance(guild)
    data["by"] = nxt.get("by")
    p.current = data
    path = data["file"]
    errf = tempfile.TemporaryFile()
    src = discord.FFmpegOpusAudio(path, executable=FFMPEG, options=f"-vn -filter:a volume={p.volume}", stderr=errf)
    started = time.time()

    def after(err):
        if time.time() - started < 5 and p.text:
            try:
                errf.seek(0)
                tail = errf.read()[-700:].decode(errors="ignore").strip()
            except Exception:
                tail = ""
            if tail:
                asyncio.run_coroutine_threadsafe(p.text.send(f"⚠️ Audio chalu nahi ho paya:\n```{tail[-700:]}```"), bot.loop)
        for f in (errf,):
            try:
                f.close()
            except Exception:
                pass
        try:
            os.remove(path)
        except OSError:
            pass
        asyncio.run_coroutine_threadsafe(advance(guild), bot.loop)

    vc.play(src, after=after)
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
    if tts_state.get(i.guild_id) or tts_busy.get(i.guild_id):
        tts_disable(i.guild)
        await i.channel.send("🔇 Gaana chalu hua, isliye TTS band kar diya.")
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
        tts_state.pop(i.guild_id, None)
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



# ---------- TTS (on / off / say) ----------
LANGS = [app_commands.Choice(name="Hindi", value="hi"), app_commands.Choice(name="English", value="en"),
         app_commands.Choice(name="Urdu", value="ur"), app_commands.Choice(name="Bengali", value="bn"),
         app_commands.Choice(name="Tamil", value="ta"), app_commands.Choice(name="Telugu", value="te"),
         app_commands.Choice(name="Marathi", value="mr"), app_commands.Choice(name="Gujarati", value="gu"),
         app_commands.Choice(name="Punjabi", value="pa")]

tts_state = {}  # guild_id -> {"channel": text_channel_id, "users": {user_id: lang}}
tts_q = {}      # guild_id -> deque[(text, lang)]
tts_busy = {}   # guild_id -> bool

tts_group = app_commands.Group(name="tts", description="TTS: /tts on, /tts off, /tts say", guild_only=True)
bot.tree.add_command(tts_group)


def tts_disable(guild):
    tts_state.pop(guild.id, None)
    tts_q.pop(guild.id, None)
    vc = guild.voice_client
    if vc and tts_busy.get(guild.id):
        vc.stop()


async def tts_pump(guild):
    try:
        while tts_q.get(guild.id):
            text, lang = tts_q[guild.id].popleft()
            vc = guild.voice_client
            if not vc or not vc.is_connected():
                tts_q.pop(guild.id, None)
                break
            for _ in range(20):
                if not (vc.is_playing() or vc.is_paused()):
                    break
                await asyncio.sleep(0.5)
            else:
                continue
            path = os.path.join(tempfile.gettempdir(), f"tts_{guild.id}_{int(time.time()*1000)}.mp3")
            try:
                await asyncio.get_running_loop().run_in_executor(None, lambda: gTTS(text=text, lang=lang).save(path))
            except Exception:
                continue
            loop = asyncio.get_running_loop()
            done = asyncio.Event()
            vc.play(discord.FFmpegOpusAudio(path, executable=FFMPEG, options="-vn"),
                    after=lambda e: loop.call_soon_threadsafe(done.set))
            await done.wait()
            try:
                os.remove(path)
            except OSError:
                pass
    finally:
        tts_busy[guild.id] = False


def tts_enqueue(guild, text, lang):
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"<a?:\w+:\d+>", "", text).strip()
    if not text:
        return
    tts_q.setdefault(guild.id, deque()).append((text[:300], lang))
    if not tts_busy.get(guild.id):
        tts_busy[guild.id] = True
        asyncio.create_task(tts_pump(guild))


@tts_group.command(name="on", description="TTS ON: chat me likhoge to bot voice me bolega")
@app_commands.choices(language=LANGS)
async def tts_on(i: discord.Interaction, language: app_commands.Choice[str] = None):
    if not i.user.voice or not i.user.voice.channel:
        return await i.response.send_message("🎧 Pehle kisi voice channel me join karo!", ephemeral=True)
    await i.response.defer()
    vc = await need_vc(i)
    if not vc:
        return
    p = gp(i.guild_id)
    note = ""
    if p.current or p.queue:
        p.queue.clear()
        p.loop = False
        p.current = None
        vc.stop()
        note = "\n⏹️ TTS chalu hua, isliye gaana band kar diya."
    st = tts_state.setdefault(i.guild_id, {"channel": i.channel_id, "users": {}})
    st["channel"] = i.channel_id
    st["users"][i.user.id] = language.value if language else "hi"
    await i.followup.send(f"🗣️ **TTS ON** ✅\nAb {i.channel.mention} me tum jo likhoge, main voice me bolunga.\nBand karne ke liye `/tts off`.{note}")


@tts_group.command(name="off", description="TTS OFF")
async def tts_off(i: discord.Interaction):
    st = tts_state.get(i.guild_id)
    if not st or i.user.id not in st["users"]:
        return await i.response.send_message("TTS pehle se OFF hai.", ephemeral=True)
    st["users"].pop(i.user.id)
    if not st["users"]:
        tts_disable(i.guild)
    await i.response.send_message("🔇 **TTS OFF** ❌")


@tts_group.command(name="say", description="Ek baar ke liye text bulwao")
@app_commands.choices(language=LANGS)
async def tts_say(i: discord.Interaction, text: app_commands.Range[str, 1, 300], language: app_commands.Choice[str] = None):
    if not i.user.voice or not i.user.voice.channel:
        return await i.response.send_message("🎧 Pehle kisi voice channel me join karo!", ephemeral=True)
    await i.response.defer()
    vc = await need_vc(i)
    if not vc:
        return
    if gp(i.guild_id).current:
        return await i.followup.send("⏳ Gaana chal raha hai. Pehle `/stop` karo.")
    tts_enqueue(i.guild, text, language.value if language else "hi")
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


# ================== DASHBOARD (website) ==================
esc = html.escape
sessions = {}
SECURE = os.getenv("BASE_URL", "").startswith("https")

CSS = """
:root{--bg:#07070d;--card:rgba(255,255,255,.04);--line:rgba(255,255,255,.09);--tx:#eef0ff;--mut:#9ba3c4;--a:#7c5cff;--b:#00d4ff;--c:#ff4fd8;--ok:#57F287}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--tx);overflow-x:hidden}
.bg{position:fixed;inset:0;z-index:-1;overflow:hidden}
.bg i{position:absolute;width:55vmax;height:55vmax;border-radius:50%;filter:blur(90px);opacity:.35;animation:fl 18s ease-in-out infinite alternate}
.bg i:nth-child(1){background:var(--a);top:-20vmax;left:-15vmax}
.bg i:nth-child(2){background:var(--b);bottom:-25vmax;right:-15vmax;animation-delay:-6s}
.bg i:nth-child(3){background:var(--c);top:30%;left:40%;width:30vmax;height:30vmax;opacity:.18;animation-delay:-12s}
@keyframes fl{to{transform:translate(8vmax,6vmax) scale(1.15)}}
.wrap{max-width:1000px;margin:auto;padding:16px}
nav{position:sticky;top:10px;z-index:9;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 14px;margin-bottom:22px;border:1px solid var(--line);border-radius:16px;background:rgba(12,12,22,.65);backdrop-filter:blur(14px)}
.logo{text-decoration:none;font-weight:800;font-size:18px;background:linear-gradient(90deg,var(--b),var(--a),var(--c));-webkit-background-clip:text;background-clip:text;color:transparent}
.links{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
.links a{color:var(--mut);text-decoration:none;padding:7px 12px;border-radius:10px;font-size:14px;transition:.2s}
.links a:hover,.links a.on{color:#fff;background:rgba(255,255,255,.08)}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px;margin-bottom:14px;backdrop-filter:blur(8px);transition:transform .25s,border-color .25s,box-shadow .25s}
.card:hover{border-color:rgba(124,92,255,.5);box-shadow:0 10px 40px -12px rgba(124,92,255,.45)}
.mut{color:var(--mut)}
.btn{display:inline-block;background:linear-gradient(135deg,var(--a),var(--b));color:#fff;text-decoration:none;border:0;border-radius:12px;padding:11px 20px;font-size:15px;font-weight:600;cursor:pointer;transition:.25s;box-shadow:0 8px 24px -8px rgba(124,92,255,.7)}
.btn:hover{transform:translateY(-2px) scale(1.03)}
.btn.alt{background:rgba(255,255,255,.07);box-shadow:none;border:1px solid var(--line)}.btn.sm{padding:7px 13px;font-size:13px}
.hero{text-align:center;padding:46px 6px 26px}
.hero h1{font-size:clamp(34px,8vw,62px);line-height:1.05;margin:0 0 14px;font-weight:900;background:linear-gradient(90deg,#fff,var(--b),var(--a),var(--c),#fff);background-size:300% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:sh 8s linear infinite}
@keyframes sh{to{background-position:300% 0}}
.hero p{max-width:560px;margin:0 auto 24px;font-size:17px}
.pill{display:inline-block;padding:6px 14px;border:1px solid var(--line);border-radius:99px;font-size:13px;color:var(--mut);margin-bottom:18px;background:rgba(255,255,255,.04)}
.pill:before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);margin-right:8px;animation:pu 1.6s infinite}
@keyframes pu{50%{opacity:.3;transform:scale(1.6)}}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:18px 0}
.stats div{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:14px;padding:14px;text-align:center}
.stats b{display:block;font-size:26px;font-weight:800}.stats span{color:var(--mut);font-size:13px}
.grid{display:grid;gap:14px;grid-template-columns:1fr}
.f .ic{font-size:30px;margin-bottom:8px;display:inline-block;animation:bob 3s ease-in-out infinite}
@keyframes bob{50%{transform:translateY(-6px)}}
h2.t{font-size:26px;margin:36px 0 14px}
.rv{opacity:0;transform:translateY(24px);transition:opacity .7s,transform .7s,border-color .25s,box-shadow .25s}.rv.in{opacity:1;transform:none}
.cmd{display:inline-block;margin:3px 8px 3px 0;padding:4px 10px;border-radius:9px;background:rgba(124,92,255,.14);border:1px solid rgba(124,92,255,.3);font-size:13px;font-family:ui-monospace,monospace}
.row{padding:5px 0}
.search{width:100%;padding:13px 16px;border-radius:14px;border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--tx);font-size:16px;margin-bottom:14px}
.g{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--tx)}
.g:hover{transform:translateY(-3px)}
.g img,.ico{width:50px;height:50px;border-radius:50%;background:linear-gradient(135deg,var(--a),var(--c));display:flex;align-items:center;justify-content:center;font-weight:800}
.g div b{display:block}
label{display:block;margin:14px 0 6px;font-weight:600}
select{width:100%;padding:11px;border-radius:12px;border:1px solid var(--line);background:#10101c;color:var(--tx);font-size:15px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left}
.ok{background:rgba(87,242,135,.1);border-color:rgba(87,242,135,.4);color:var(--ok)}
.two{display:grid;gap:14px}
footer{text-align:center;color:var(--mut);font-size:13px;padding:30px 0 10px}
@media(min-width:700px){.stats{grid-template-columns:repeat(4,1fr)}.two{grid-template-columns:1fr 1fr}.grid{grid-template-columns:repeat(3,1fr)}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.rv{opacity:1;transform:none}}
"""

JS = """
const io=new IntersectionObserver(e=>e.forEach(x=>{if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}}),{threshold:.1});
document.querySelectorAll('.rv').forEach(e=>io.observe(e));
document.querySelectorAll('[data-n]').forEach(el=>{const t=+el.dataset.n,s=performance.now();(function f(n){const p=Math.min((n-s)/1200,1);el.textContent=Math.round(t*(1-Math.pow(1-p,3))).toLocaleString();if(p<1)requestAnimationFrame(f)})(s)});
const q=document.getElementById('q');if(q)q.oninput=()=>{const v=q.value.toLowerCase();document.querySelectorAll('.cc').forEach(c=>{let a=0;c.querySelectorAll('.row').forEach(r=>{const m=r.textContent.toLowerCase().includes(v);r.style.display=m?'':'none';if(m)a=1});c.style.display=a?'':'none'})};
"""


def dpage(title, body, s=None, status=200, active=""):
    name = bot.user.name if bot.user else "Bot"
    nav = "".join(f'<a href="{u}"{" class=on" if k == active else ""}>{t}</a>' for k, u, t in
                  [("home", "/", "Home"), ("cmds", "/commands", "Commands"), ("dash", "/dashboard", "Dashboard")])
    nav += (f'<a href="/logout">Logout ({esc(s["user"].get("username", ""))})</a>' if s else '<a class="btn sm" href="/login" style="color:#fff">Login</a>')
    return web.Response(status=status, content_type="text/html", text=(
        f'<!doctype html><html lang="hi"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | {esc(name)}</title>'
        f'<style>{CSS}</style></head><body><div class="bg"><i></i><i></i><i></i></div><div class="wrap">'
        f'<nav><a class="logo" href="/">✦ {esc(name)}</a><div class="links">{nav}</div></nav>{body}'
        f'<footer>© {esc(name)} • Made with ❤️</footer></div><script>{JS}</script></body></html>'))


def redir(url):
    return web.Response(status=302, headers={"Location": url})


def dsession(request):
    s = sessions.get(request.cookies.get("sid", ""))
    return s if s and s["exp"] > time.time() else None


def manageable(s):
    out = []
    for g in s["guilds"]:
        p = int(g.get("permissions", 0))
        if g.get("owner") or p & 0x20 or p & 0x8:
            gg = bot.get_guild(int(g["id"]))
            if gg:
                out.append(gg)
    return out


def guild_for(request):
    s = dsession(request)
    if not s:
        return None, None
    try:
        gid = int(request.match_info["gid"])
    except ValueError:
        return s, None
    return s, next((x for x in manageable(s) if x.id == gid), None)


def assignable(g):
    return [r for r in reversed(g.roles) if not r.is_default() and not r.managed and r < g.me.top_role]


def name_of(g, uid):
    m = g.get_member(uid)
    return m.display_name if m else f"User {uid}"


def invite_url():
    cid = os.getenv("CLIENT_ID") or (str(bot.user.id) if bot.user else "")
    return f"https://discord.com/oauth2/authorize?client_id={cid}&scope=bot+applications.commands&permissions=8"


async def d_home(request):
    s = dsession(request)
    users = sum(g.member_count or 0 for g in bot.guilds)
    feats = [("🎵", "Music", "YouTube/SoundCloud se gaane, queue, loop, shuffle."), ("🗣️", "TTS", "Chat me likho, bot voice me bolega. Hindi + 8 languages."),
             ("🛡️", "Moderation", "Kick, ban, timeout, warn, lock, slowmode aur logs."), ("💰", "Economy", "Daily, work, slots, gamble aur leaderboard."),
             ("📈", "Levels", "Chat karo, XP kamao, level up pe coins pao."), ("🎫", "Tickets", "Button se private support ticket, welcome aur auto role.")]
    cards = "".join(f'<div class="card f rv"><div class="ic">{i}</div><h3 style="margin:0 0 6px">{t}</h3><div class="mut">{d}</div></div>' for i, t, d in feats)
    body = (f'<div class="hero"><div class="pill">Online 24/7</div><h1>Sabka all-rounder<br>Discord Bot</h1>'
            f'<p class="mut">Music, TTS, moderation, economy, levels aur ek premium dashboard. Sab ek hi bot me.</p>'
            f'<a class="btn" href="{"/dashboard" if s else "/login"}">{"Dashboard kholo" if s else "Discord se Login"}</a> '
            f'<a class="btn alt" href="{esc(invite_url())}">➕ Bot add karo</a></div>'
            f'<div class="stats rv"><div><b data-n="{len(bot.guilds)}">0</b><span>Servers</span></div><div><b data-n="{users}">0</b><span>Users</span></div>'
            f'<div><b data-n="{len(bot.tree.get_commands())}">0</b><span>Commands</span></div><div><b>{fmt(time.time() - START)}</b><span>Uptime</span></div></div>'
            f'<h2 class="t rv">✨ Features</h2><div class="grid">{cards}</div>'
            f'<div class="card rv" style="text-align:center;margin-top:20px"><h2 style="margin-top:0">Taiyaar ho?</h2>'
            f'<p class="mut">Bot ko server me add karo aur dashboard se settings badlo.</p>'
            f'<a class="btn" href="{esc(invite_url())}">➕ Bot add karo</a> <a class="btn alt" href="/commands">📖 Saari commands</a></div>')
    return dpage("Home", body, s, active="home")


async def d_commands(request):
    s = dsession(request)
    cmds, cats = help_cats()
    cards = "".join(
        f'<div class="card cc rv"><h3 style="margin-top:0">{esc(k)}</h3>' +
        "".join(f'<div class="row"><span class="cmd">/{esc(n)}</span><span class="mut">{esc(cmds[n])}</span></div>' for n in v) + '</div>'
        for k, v in cats.items())
    body = f'<h2 class="t">📖 Commands ({len(cmds)})</h2><input id="q" class="search" placeholder="🔎 Command dhundo...">{cards}'
    return dpage("Commands", body, s, active="cmds")


async def d_login(request):
    cid, sec, base = os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"), os.getenv("BASE_URL")
    if not (cid and sec and base):
        return dpage("Setup baaki", '<div class="card">⚠️ Dashboard setup baaki hai. Railway Variables me <b>CLIENT_ID</b>, '
                                    '<b>CLIENT_SECRET</b> aur <b>BASE_URL</b> daalo.</div>')
    st = secrets.token_urlsafe(16)
    url = "https://discord.com/oauth2/authorize?" + urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": base.rstrip("/") + "/callback",
        "scope": "identify guilds", "state": st, "prompt": "none"})
    r = redir(url)
    r.set_cookie("st", st, httponly=True, secure=SECURE, samesite="Lax", max_age=600)
    r.set_cookie("api", "1" if request.query.get("site") else "0", httponly=True, secure=SECURE, samesite="Lax", max_age=600)
    return r


async def d_callback(request):
    code, state = request.query.get("code"), request.query.get("state")
    if not code or not state or state != request.cookies.get("st"):
        return dpage("Error", '<div class="card">❌ Login fail hua. <a href="/login">Dobara try karo</a>.</div>', status=400)
    base = os.getenv("BASE_URL", "").rstrip("/")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as cs:
            async with cs.post("https://discord.com/api/oauth2/token", data={
                    "client_id": os.getenv("CLIENT_ID"), "client_secret": os.getenv("CLIENT_SECRET"),
                    "grant_type": "authorization_code", "code": code, "redirect_uri": base + "/callback"}) as r:
                tok = await r.json()
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            async with cs.get("https://discord.com/api/users/@me", headers=h) as r:
                user = await r.json()
            async with cs.get("https://discord.com/api/users/@me/guilds", headers=h) as r:
                guilds = await r.json()
        if not isinstance(guilds, list) or "id" not in user:
            raise ValueError
    except Exception:
        return dpage("Error", '<div class="card">❌ Discord se login complete nahi hua. '
                              '<a href="/login">Dobara try karo</a>. (Redirect URL Developer Portal me add hai?)</div>', status=400)
    for k in [k for k, v in sessions.items() if v["exp"] < time.time()]:
        del sessions[k]
    sid = secrets.token_urlsafe(32)
    sessions[sid] = {"user": user, "guilds": guilds, "csrf": secrets.token_urlsafe(16), "exp": time.time() + 7 * 86400}
    site = os.getenv("SITE_URL", "").rstrip("/")
    r = redir(f"{site}/#token={sid}" if request.cookies.get("api") == "1" and site else "/dashboard")
    r.del_cookie("api")
    r.set_cookie("sid", sid, httponly=True, secure=SECURE, samesite="Lax", max_age=7 * 86400)
    r.del_cookie("st")
    return r


async def d_logout(request):
    sessions.pop(request.cookies.get("sid", ""), None)
    r = redir("/")
    r.del_cookie("sid")
    return r


async def d_dash(request):
    s = dsession(request)
    if not s:
        return redir("/login")
    cards = ""
    for g in manageable(s):
        icon = f'<img src="{g.icon.url}" alt="">' if g.icon else f'<div class="ico">{esc(g.name[:1])}</div>'
        cards += f'<a class="card g" href="/guild/{g.id}">{icon}<div><b>{esc(g.name)}</b><span class="mut">{g.member_count} members</span></div></a>'
    if not cards:
        cards = (f'<div class="card">Koi server nahi mila jahan tum <b>Manage Server</b> permission wale ho aur bot bhi hai.<br><br>'
                 f'<a class="btn" href="{esc(invite_url())}">➕ Bot add karo</a></div>')
    return dpage("Servers", "<h2 class=\"t\">Tumhare servers</h2>" + cards, s, active="dash")


async def d_guild(request):
    s, g = guild_for(request)
    if not s:
        return redir("/login")
    if not g:
        return dpage("404", '<div class="card">❌ Server nahi mila ya permission nahi hai.</div>', s, 404)
    cur = {k: get_set(g.id, k) for k in ("welcome", "autorole", "log")}

    def opts(items, sel):
        o = '<option value="">— koi nahi —</option>'
        for i, n in items:
            o += f'<option value="{i}"{" selected" if i == sel else ""}>{esc(n)}</option>'
        return o

    chans = [(c.id, "#" + c.name) for c in g.text_channels]
    roles = [(r.id, r.name) for r in assignable(g)]

    def table(rows, fmt_val):
        t = "".join(f"<tr><td>{n}</td><td>{esc(name_of(g, u))}</td><td>{fmt_val(v)}</td></tr>" for n, (u, v) in enumerate(rows, 1))
        return t or '<tr><td colspan="3" class="mut">Abhi data nahi</td></tr>'

    coins = db.execute("SELECT u,coins FROM users WHERE g=? ORDER BY coins DESC LIMIT 10", (g.id,)).fetchall()
    xps = db.execute("SELECT u,xp FROM users WHERE g=? ORDER BY xp DESC LIMIT 10", (g.id,)).fetchall()
    warns = db.execute("SELECT COUNT(*) FROM warns WHERE g=?", (g.id,)).fetchone()[0]
    saved = '<div class="card ok">✅ Settings save ho gayi!</div>' if request.query.get("saved") else ""
    body = (
        f'<p><a class="mut" href="/dashboard">← Servers</a></p><h2>{esc(g.name)}</h2>{saved}'
        f'<div class="stats"><div><b>{g.member_count}</b><span>Members</span></div><div><b>{len(g.channels)}</b><span>Channels</span></div>'
        f'<div><b>{len(g.roles)}</b><span>Roles</span></div><div><b>{warns}</b><span>Warnings</span></div></div>'
        f'<div class="card"><h3 style="margin-top:0">⚙️ Settings</h3><form method="post">'
        f'<input type="hidden" name="csrf" value="{esc(s["csrf"])}">'
        f'<label>👋 Welcome / Goodbye channel</label><select name="welcome">{opts(chans, cur["welcome"])}</select>'
        f'<label>🎭 Auto role (naye members ko)</label><select name="autorole">{opts(roles, cur["autorole"])}</select>'
        f'<label>📜 Log channel (delete/edit logs)</label><select name="log">{opts(chans, cur["log"])}</select>'
        f'<p><button class="btn" type="submit">💾 Save</button></p></form>'
        f'<p class="mut" style="font-size:13px">Auto role me sirf wahi roles dikhte hain jo bot ke role se neeche hain.</p></div>'
        f'<div class="two"><div class="card"><h3 style="margin-top:0">💰 Coins Top 10</h3><table>{table(coins, lambda v: f"{v:,}")}</table></div>'
        f'<div class="card"><h3 style="margin-top:0">📈 XP Top 10</h3><table>{table(xps, lambda v: f"Lvl {level_of(v)} ({v} XP)")}</table></div></div>')
    return dpage(g.name, body, s)


async def d_guild_save(request):
    s, g = guild_for(request)
    if not s:
        return redir("/login")
    if not g:
        return dpage("404", '<div class="card">❌ Server nahi mila ya permission nahi hai.</div>', s, 404)
    data = await request.post()
    if str(data.get("csrf", "")) != s["csrf"]:
        return web.Response(status=403, text="Invalid request")
    ids = {c.id for c in g.text_channels}
    valid = {"welcome": ids, "log": ids, "autorole": {r.id for r in assignable(g)}}
    for k, ok in valid.items():
        v = str(data.get(k, ""))
        if v == "":
            db.execute("DELETE FROM settings WHERE g=? AND k=?", (g.id, k))
            db.commit()
        elif v.isdigit() and int(v) in ok:
            set_set(g.id, k, int(v))
    return redir(f"/guild/{g.id}?saved=1")


@web.middleware
async def secure_headers(request, handler):
    resp = await handler(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' https://cdn.discordapp.com data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"
    return resp


# ---------- JSON API (separate website ke liye) ----------
def asession(request):
    s = sessions.get(request.headers.get("Authorization", "")[7:])
    return s if s and s["exp"] > time.time() else None


def jr(data, status=200):
    return web.json_response(data, status=status)


def aguild(request):
    s = asession(request)
    if not s:
        return None, None
    try:
        gid = int(request.match_info["gid"])
    except ValueError:
        return s, None
    return s, next((x for x in manageable(s) if x.id == gid), None)


async def a_stats(request):
    return jr({"name": bot.user.name if bot.user else "Bot", "servers": len(bot.guilds),
               "users": sum(g.member_count or 0 for g in bot.guilds), "commands": len(bot.tree.get_commands()),
               "uptime": int(time.time() - START), "invite": invite_url()})


async def a_commands(request):
    cmds, cats = help_cats()
    return jr({k: [{"n": n, "d": cmds[n]} for n in v] for k, v in cats.items()})


async def a_me(request):
    s = asession(request)
    if not s:
        return jr({"error": "login"}, 401)
    u = s["user"]
    return jr({"user": {"name": u.get("global_name") or u.get("username")},
               "guilds": [{"id": str(g.id), "name": g.name, "icon": g.icon.url if g.icon else None, "members": g.member_count}
                          for g in manageable(s)]})


async def a_guild(request):
    s, g = aguild(request)
    if not s:
        return jr({"error": "login"}, 401)
    if not g:
        return jr({"error": "notfound"}, 404)

    def top(col):
        return [{"name": name_of(g, u), "v": v, "lvl": level_of(v)} for u, v in
                db.execute(f"SELECT u,{col} FROM users WHERE g=? ORDER BY {col} DESC LIMIT 10", (g.id,)).fetchall()]
    return jr({"name": g.name, "members": g.member_count,
               "channels": [{"id": str(c.id), "name": c.name} for c in g.text_channels],
               "roles": [{"id": str(r.id), "name": r.name} for r in assignable(g)],
               "settings": {k: str(get_set(g.id, k) or "") for k in ("welcome", "autorole", "log")},
               "coins": top("coins"), "xp": top("xp"),
               "warns": db.execute("SELECT COUNT(*) FROM warns WHERE g=?", (g.id,)).fetchone()[0]})


async def a_guild_save(request):
    s, g = aguild(request)
    if not s:
        return jr({"error": "login"}, 401)
    if not g:
        return jr({"error": "notfound"}, 404)
    try:
        data = await request.json()
    except Exception:
        return jr({"error": "bad"}, 400)
    ids = {c.id for c in g.text_channels}
    valid = {"welcome": ids, "log": ids, "autorole": {r.id for r in assignable(g)}}
    for k, ok in valid.items():
        v = str(data.get(k, ""))
        if v == "":
            db.execute("DELETE FROM settings WHERE g=? AND k=?", (g.id, k))
            db.commit()
        elif v.isdigit() and int(v) in ok:
            set_set(g.id, k, int(v))
    return jr({"ok": True})


@web.middleware
async def cors(request, handler):
    p = urlparse(os.getenv("SITE_URL", ""))
    allowed_origin = f"{p.scheme}://{p.netloc}" if p.netloc else None
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as e:
            resp = e
    if allowed_origin and request.headers.get("Origin") == allowed_origin:
        resp.headers.update({"Access-Control-Allow-Origin": allowed_origin, "Vary": "Origin",
                             "Access-Control-Allow-Headers": "Authorization, Content-Type",
                             "Access-Control-Allow-Methods": "GET, POST, OPTIONS"})
    return resp


async def start_dashboard():
    app = web.Application(middlewares=[cors, secure_headers])
    app.router.add_get("/", d_home)
    app.router.add_get("/commands", d_commands)
    app.router.add_get("/api/stats", a_stats)
    app.router.add_get("/api/commands", a_commands)
    app.router.add_get("/api/me", a_me)
    app.router.add_get("/api/guild/{gid}", a_guild)
    app.router.add_post("/api/guild/{gid}", a_guild_save)
    app.router.add_get("/login", d_login)
    app.router.add_get("/callback", d_callback)
    app.router.add_get("/logout", d_logout)
    app.router.add_get("/dashboard", d_dash)
    app.router.add_get("/guild/{gid}", d_guild)
    app.router.add_post("/guild/{gid}", d_guild_save)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8080"))).start()


# ================== RUN ==================
bot.run(os.environ["TOKEN"])
