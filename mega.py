"""mega.py - 900+ extra slash commands (nested groups). main.py isko khud load karta hai."""
import html, hashlib, zlib, base64, codecs, string, secrets, random, math, statistics, datetime, re, uuid, unicodedata, urllib.parse
import aiohttp
import discord
from discord import app_commands

bot = emb = TriviaView = today = None


def setup(_bot, _emb, _tv, _today):
    global bot, emb, TriviaView, today
    bot, emb, TriviaView, today = _bot, _emb, _tv, _today
    _register()


def _register():
    NO = discord.AllowedMentions.none()
    gf = lambda x: f"{x:,.8g}"
    pi = math.pi

    def top(name, desc):
        g = app_commands.Group(name=name, description=desc)
        bot.tree.add_command(g)
        return g

    def sub(parent, name, desc):
        g = app_commands.Group(name=name, description=desc, parent=parent)
        parent.add_command(g, override=True)
        return g

    async def get_json(url):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as cs:
            async with cs.get(url) as r:
                return await r.json()

    # ============ /unit + /unit2 (186) ============
    UNITS = {
        "length": {"m": 1, "km": 1000, "cm": .01, "mi": 1609.344, "ft": .3048},
        "mass": {"kg": 1, "g": .001, "lb": .45359237, "oz": .028349523125, "t": 1000},
        "volume": {"l": 1, "ml": .001, "gal": 3.785411784, "cup": .2365882365, "floz": .0295735295625},
        "speed": {"kmh": 1 / 3.6, "mph": .44704, "ms": 1, "knot": .514444, "fps": .3048},
        "time": {"s": 1, "min": 60, "hr": 3600, "day": 86400, "week": 604800},
        "data": {"b": 1, "kb": 1024, "mb": 1048576, "gb": 1073741824, "tb": 1099511627776},
        "area": {"m2": 1, "km2": 1e6, "ha": 1e4, "acre": 4046.8564224, "ft2": .09290304},
        "energy": {"j": 1, "kj": 1000, "cal": 4.184, "kcal": 4184, "kwh": 3.6e6},
        "pressure": {"pa": 1, "kpa": 1000, "bar": 1e5, "atm": 101325, "psi": 6894.757293168},
    }

    def mk_unit(g, a, b, fa, fb):
        @g.command(name=f"{a}2{b}", description=f"{a} to {b}")
        async def _(i: discord.Interaction, value: float):
            await i.response.send_message(f"🔁 **{gf(value)} {a}** = **{gf(value * fa / fb)} {b}**")

    u1, u2 = top("unit", "Unit converter: length, mass, volume, speed, time"), top("unit2", "Unit converter: data, area, energy, pressure, temp")
    for cat, grp in [("length", u1), ("mass", u1), ("volume", u1), ("speed", u1), ("time", u1), ("data", u2), ("area", u2), ("energy", u2), ("pressure", u2)]:
        sg = sub(grp, cat, f"{cat} converter")
        for a, fa in UNITS[cat].items():
            for b, fb in UNITS[cat].items():
                if a != b:
                    mk_unit(sg, a, b, fa, fb)
    tg = sub(u2, "temp", "Temperature converter")
    for a, b, f in [("c", "f", lambda v: v * 9 / 5 + 32), ("c", "k", lambda v: v + 273.15), ("f", "c", lambda v: (v - 32) * 5 / 9),
                    ("f", "k", lambda v: (v - 32) * 5 / 9 + 273.15), ("k", "c", lambda v: v - 273.15), ("k", "f", lambda v: (v - 273.15) * 9 / 5 + 32)]:
        def mk_t2(a=a, b=b, f=f):
            @tg.command(name=f"{a}2{b}", description=f"{a.upper()} to {b.upper()}")
            async def _(i: discord.Interaction, value: float):
                await i.response.send_message(f"🌡️ **{gf(value)}°{a.upper()}** = **{gf(f(value))}°{b.upper()}**")
        mk_t2()

    # ============ /quiz (96) ============
    CATS = [(9, "general"), (10, "books"), (11, "film"), (12, "music"), (13, "theatre"), (14, "tv"), (15, "videogames"), (16, "boardgames"),
            (17, "science"), (18, "computers"), (19, "math"), (20, "mythology"), (21, "sports"), (22, "geography"), (23, "history"), (24, "politics"),
            (25, "art"), (26, "celebrities"), (27, "animals"), (28, "vehicles"), (29, "comics"), (30, "gadgets"), (31, "anime"), (32, "cartoons")]

    def mk_quiz(g, cid, name, diff):
        @g.command(name=name, description=f"{name} quiz ({diff or 'any'})")
        async def _(i: discord.Interaction):
            await i.response.defer()
            try:
                d = (await get_json(f"https://opentdb.com/api.php?amount=1&type=multiple&category={cid}" + (f"&difficulty={diff}" if diff else "")))["results"][0]
                correct = html.unescape(d["correct_answer"])
                opts = [html.unescape(x) for x in d["incorrect_answers"]] + [correct]
                random.shuffle(opts)
                await i.followup.send(f"❓ **{html.unescape(d['question'])}**", view=TriviaView(i.user, opts, correct))
            except Exception:
                await i.followup.send("😢 Quiz abhi load nahi hua (thodi der baad try karo).")

    q = top("quiz", "Trivia quiz: 24 categories x 4 levels")
    for diff in ("easy", "medium", "hard", None):
        sg = sub(q, diff or "any", f"{diff or 'any'} difficulty quiz")
        for cid, name in CATS:
            mk_quiz(sg, cid, name, diff)

    # ============ /font (30) ============
    def mmap(U, L, D=None):
        t = {}
        for k in range(26):
            for base, off in ((65, U), (97, L)):
                if unicodedata.name(chr(off + k), None):
                    t[chr(base + k)] = chr(off + k)
        if D:
            for k in range(10):
                t[chr(48 + k)] = chr(D + k)
        return lambda s: "".join(t.get(c, c) for c in s)

    tr = lambda a, b: (lambda s: s.translate(str.maketrans(a, b)))
    comb = lambda ch: (lambda s: "".join(c if c.isspace() else c + ch for c in s))
    az = string.ascii_lowercase
    FONTS = [
        ("bold", mmap(0x1D400, 0x1D41A, 0x1D7CE)), ("italic", mmap(0x1D434, 0x1D44E)), ("bolditalic", mmap(0x1D468, 0x1D482)),
        ("script", mmap(0x1D49C, 0x1D4B6)), ("boldscript", mmap(0x1D4D0, 0x1D4EA)), ("fraktur", mmap(0x1D504, 0x1D51E)),
        ("boldfraktur", mmap(0x1D56C, 0x1D586)), ("doublestruck", mmap(0x1D538, 0x1D552, 0x1D7D8)), ("sans", mmap(0x1D5A0, 0x1D5BA, 0x1D7E2)),
        ("sansbold", mmap(0x1D5D4, 0x1D5EE, 0x1D7EC)), ("sansitalic", mmap(0x1D608, 0x1D622)), ("sansbolditalic", mmap(0x1D63C, 0x1D656)),
        ("mono", mmap(0x1D670, 0x1D68A, 0x1D7F6)), ("circled", mmap(0x24B6, 0x24D0)), ("negcircled", mmap(0x1F150, 0x1F150)),
        ("squared", mmap(0x1F130, 0x1F130)), ("negsquared", mmap(0x1F170, 0x1F170)), ("parenthesized", mmap(0x1F110, 0x249C)),
        ("fullwidth", mmap(0xFF21, 0xFF41, 0xFF10)), ("smallcaps", tr(az, "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ")),
        ("superscript", tr(az, "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵠʳˢᵗᵘᵛʷˣʸᶻ")), ("subscript", tr(az, "ₐbcdₑfgₕᵢⱼₖₗₘₙₒₚqᵣₛₜᵤᵥwₓyz")),
        ("underline", comb("\u0332")), ("dunderline", comb("\u0333")), ("overline", comb("\u0305")), ("slashed", comb("\u0338")),
        ("wavy", comb("\u0330")), ("dotted", comb("\u0323")), ("tilded", comb("\u0334")), ("arrowed", comb("\u20D7")),
    ]
    fg = top("font", "Fancy text fonts (30 styles)")

    def mk_font(g, name, fn):
        @g.command(name=name, description=f"{name} font")
        async def _(i: discord.Interaction, text: str):
            await i.response.send_message(fn(text)[:1900] or "-", allowed_mentions=NO)

    for k_, (lbl, chunk) in enumerate((("Unicode styles", FONTS[:15]), ("More styles", FONTS[15:]))):
        sg = sub(fg, f"set{k_ + 1}", lbl)
        for n_, f_ in chunk:
            mk_font(sg, n_, f_)

    # ============ text helper ============
    def mk_t(g, name, desc, fn):
        @g.command(name=name, description=desc)
        async def _(i: discord.Interaction, text: str):
            try:
                out = fn(text)
            except Exception:
                out = "❌ Galat input."
            await i.response.send_message(str(out)[:1900] or "-", allowed_mentions=NO)

    # ============ /crypto (43) ============
    MORSE = dict(zip("abcdefghijklmnopqrstuvwxyz0123456789", ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --.. ----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.".split()))
    UNMORSE = {v: k for k, v in MORSE.items()}
    r47 = lambda s: "".join(chr(33 + (ord(c) - 33 + 47) % 94) if 33 <= ord(c) <= 126 else c for c in s)
    r5 = lambda s: s.translate(str.maketrans("0123456789", "5678901234"))
    cr = top("crypto", "Encode, decode, hash aur ciphers")
    ce, ch_, ci_ = sub(cr, "encode", "Encoders/decoders"), sub(cr, "hash", "Hash functions"), sub(cr, "cipher", "Classic ciphers")
    for n_, d_, f_ in [
        ("b64e", "Base64 encode", lambda s: base64.b64encode(s.encode()).decode()), ("b64d", "Base64 decode", lambda s: base64.b64decode(s.encode()).decode()),
        ("b32e", "Base32 encode", lambda s: base64.b32encode(s.encode()).decode()), ("b32d", "Base32 decode", lambda s: base64.b32decode(s.encode()).decode()),
        ("hexe", "Text to hex", lambda s: s.encode().hex()), ("hexd", "Hex to text", lambda s: bytes.fromhex(s.replace(" ", "")).decode()),
        ("urle", "URL encode", lambda s: urllib.parse.quote(s, safe="")), ("urld", "URL decode", urllib.parse.unquote),
        ("htmle", "HTML escape", html.escape), ("htmld", "HTML unescape", html.unescape),
        ("asciie", "Text to ASCII codes", lambda s: " ".join(str(ord(c)) for c in s)), ("asciid", "ASCII codes to text", lambda s: "".join(chr(int(x)) for x in s.split())),
        ("unie", "Text to Unicode U+", lambda s: " ".join(f"U+{ord(c):04X}" for c in s)),
        ("bine", "Text to binary", lambda s: " ".join(format(b, "08b") for b in s.encode())), ("bind", "Binary to text", lambda s: bytes(int(x, 2) for x in s.split()).decode()),
        ("octe", "Text to octal", lambda s: " ".join(format(b, "o") for b in s.encode())), ("octd", "Octal to text", lambda s: bytes(int(x, 8) for x in s.split()).decode()),
        ("mors", "Morse to text", lambda s: "".join(" " if t == "/" else UNMORSE.get(t, "?") for t in s.split())),
        ("rot5", "ROT5 (digits)", r5), ("rot13", "ROT13", lambda s: codecs.encode(s, "rot_13")), ("rot18", "ROT18", lambda s: r5(codecs.encode(s, "rot_13"))),
        ("rot47", "ROT47", r47), ("atbash", "Atbash cipher", tr(az + az.upper(), az[::-1] + az.upper()[::-1])),
        ("a1z26", "Letters to numbers (A=1)", lambda s: "-".join(str(ord(c) - 96) for c in s.lower() if c.isalpha())),
        ("a1z26d", "Numbers to letters", lambda s: "".join(chr(int(x) + 96) for x in re.findall(r"\d+", s))),
    ]:
        mk_t(ce, n_, d_, f_)
    for h in ("md5", "sha1", "sha224", "sha256", "sha384", "sha512", "sha3_256", "sha3_512", "blake2b", "blake2s"):
        mk_t(ch_, h, f"{h} hash", lambda s, h=h: hashlib.new(h, s.encode()).hexdigest())
    mk_t(ch_, "crc32", "CRC32 checksum", lambda s: f"{zlib.crc32(s.encode()) & 0xffffffff:08x}")
    mk_t(ch_, "adler32", "Adler32 checksum", lambda s: f"{zlib.adler32(s.encode()) & 0xffffffff:08x}")

    def vig(s, k, d):
        k = [ord(c) - 97 for c in k.lower() if c.isalpha()]
        out, j = "", 0
        for c in s:
            if c.isascii() and c.isalpha():
                b = 65 if c.isupper() else 97
                out += chr((ord(c) - b + (-k[j % len(k)] if d else k[j % len(k)])) % 26 + b)
                j += 1
            else:
                out += c
        return out

    def rail_enc(s, n):
        rows, r, d = [""] * n, 0, 1
        for c in s:
            rows[r] += c
            if n > 1:
                d = 1 if r == 0 else -1 if r == n - 1 else d
                r += d
        return "".join(rows)

    def rail_dec(s, n):
        if n < 2:
            return s
        pat, r, d = [], 0, 1
        for _ in s:
            pat.append(r)
            d = 1 if r == 0 else -1 if r == n - 1 else d
            r += d
        out = [""] * len(s)
        for c, p in zip(s, sorted(range(len(s)), key=lambda x: pat[x])):
            out[p] = c
        return "".join(out)

    def piglatin(s):
        def w(x):
            if not x.isalpha():
                return x
            if x[0].lower() in "aeiou":
                return x + "way"
            m = re.match(r"[^aeiouAEIOU]+", x)
            return x[m.end():] + m.group() + "ay"
        return " ".join(w(x) for x in s.split())

    def mk_t2c(g, name, desc, fn, kname, kt):
        if kt is int:
            @g.command(name=name, description=desc)
            async def _(i: discord.Interaction, text: str, key: app_commands.Range[int, 2, 20] = 3):
                try:
                    out = fn(text, key)
                except Exception:
                    out = "❌ Galat input."
                await i.response.send_message(str(out)[:1900], allowed_mentions=NO)
        else:
            @g.command(name=name, description=desc)
            async def _(i: discord.Interaction, text: str, key: str):
                try:
                    out = fn(text, key)
                except Exception:
                    out = "❌ Galat input."
                await i.response.send_message(str(out)[:1900], allowed_mentions=NO)

    mk_t2c(ci_, "vigenere", "Vigenere encrypt (text, key)", lambda s, k: vig(s, k, 0), "key", str)
    mk_t2c(ci_, "unvigenere", "Vigenere decrypt (text, key)", lambda s, k: vig(s, k, 1), "key", str)
    mk_t2c(ci_, "railfence", "Rail fence encrypt (text, rails)", rail_enc, "key", int)
    mk_t2c(ci_, "unrailfence", "Rail fence decrypt (text, rails)", rail_dec, "key", int)
    mk_t2c(ci_, "xor", "XOR with key, hex output", lambda s, k: bytes(b ^ ord(k[n % len(k)]) for n, b in enumerate(s.encode())).hex(), "key", str)
    mk_t(ci_, "piglatin", "Pig Latin", piglatin)

    # ============ /textx (50) ============
    LN = lambda s: [x for x in re.split(r"\s*\|\s*|\n", s)]
    W = lambda s: re.findall(r"\b\w+\b", s)
    syl = lambda s: max(1, len(re.findall(r"[aeiouy]+", s.lower())))
    tx = top("textx", "Text analyzer aur cleaner (50)")
    ta, tc = sub(tx, "analyze", "Text analysis"), sub(tx, "clean", "Text cleaning (| = nayi line)")
    A = [
        ("charcount", "Characters", lambda s: f"**{len(s)}** characters"), ("letters", "Letters", lambda s: f"**{sum(c.isalpha() for c in s)}** letters"),
        ("sentences", "Sentences", lambda s: f"**{len([x for x in re.split(r'[.!?]+', s) if x.strip()])}** sentences"),
        ("paragraphs", "Paragraphs (| se alag)", lambda s: f"**{len([x for x in LN(s) if x.strip()])}** parts"), ("lines", "Lines (| se alag)", lambda s: f"**{len(LN(s))}** lines"),
        ("longest", "Sabse lamba word", lambda s: max(W(s), key=len)), ("shortest", "Sabse chhota word", lambda s: min(W(s), key=len)),
        ("avglen", "Average word length", lambda s: f"**{sum(map(len, W(s))) / len(W(s)):.2f}**"),
        ("readtime", "Padhne ka time", lambda s: f"~**{len(W(s)) / 200 * 60:.0f}** second"), ("speaktime", "Bolne ka time", lambda s: f"~**{len(W(s)) / 130 * 60:.0f}** second"),
        ("uppercount", "Capital letters", lambda s: f"**{sum(c.isupper() for c in s)}**"), ("lowercount", "Small letters", lambda s: f"**{sum(c.islower() for c in s)}**"),
        ("digits", "Digits count", lambda s: f"**{sum(c.isdigit() for c in s)}**"), ("punct", "Punctuation count", lambda s: f"**{sum(c in string.punctuation for c in s)}**"),
        ("spaces", "Spaces count", lambda s: f"**{s.count(' ')}**"), ("emojis", "Emoji count", lambda s: f"**{len(re.findall(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', s))}**"),
        ("hashtags", "Hashtags nikalo", lambda s: " ".join(re.findall(r"#\w+", s)) or "-"), ("mentions", "@mentions nikalo", lambda s: " ".join(re.findall(r"@\w+", s)) or "-"),
        ("urls", "Links nikalo", lambda s: "\n".join(re.findall(r"https?://\S+", s)) or "-"), ("emails", "Emails nikalo", lambda s: " ".join(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", s)) or "-"),
        ("numbers", "Numbers nikalo", lambda s: " ".join(re.findall(r"-?\d+\.?\d*", s)) or "-"),
        ("consonants", "Consonants count", lambda s: f"**{sum(c.isalpha() and c.lower() not in 'aeiou' for c in s)}**"),
        ("uniquewords", "Unique words", lambda s: f"**{len({x.lower() for x in W(s)})}** unique words"),
        ("freq", "Top 5 words", lambda s: ", ".join(f"{k}: {v}" for k, v in __import__('collections').Counter(x.lower() for x in W(s)).most_common(5))),
        ("flesch", "Reading ease score", lambda s: f"Flesch: **{206.835 - 1.015 * len(W(s)) / max(1, len(re.findall(r'[.!?]+', s))) - 84.6 * sum(map(syl, W(s))) / len(W(s)):.1f}**"),
    ]
    for n_, d_, f_ in A:
        mk_t(ta, n_, d_, f_)
    C = [
        ("nospaces", "Spaces hatao", lambda s: s.replace(" ", "")), ("nodigits", "Digits hatao", lambda s: re.sub(r"\d", "", s)),
        ("novowels", "Vowels hatao", lambda s: re.sub(r"[aeiouAEIOU]", "", s)), ("nopunct", "Punctuation hatao", lambda s: s.translate(str.maketrans("", "", string.punctuation))),
        ("onlyletters", "Sirf letters rakho", lambda s: re.sub(r"[^A-Za-z ]", "", s)), ("onlydigits", "Sirf digits rakho", lambda s: re.sub(r"\D", "", s)),
        ("ascii", "Non-ASCII hatao", lambda s: s.encode("ascii", "ignore").decode()), ("trim", "Aage-peeche ke spaces", str.strip),
        ("squeeze", "Extra spaces ek karo", lambda s: " ".join(s.split())), ("dedupe", "Duplicate words hatao", lambda s: " ".join(dict.fromkeys(s.split()))),
        ("dedupelines", "Duplicate lines hatao", lambda s: " | ".join(dict.fromkeys(LN(s)))), ("sortlines", "Lines A-Z", lambda s: " | ".join(sorted(LN(s)))),
        ("sortlinesrev", "Lines Z-A", lambda s: " | ".join(sorted(LN(s), reverse=True))), ("revlines", "Lines ulti", lambda s: " | ".join(LN(s)[::-1])),
        ("numberlines", "Lines pe number", lambda s: "\n".join(f"{n}. {x}" for n, x in enumerate(LN(s), 1))), ("bullets", "Bullet list", lambda s: "\n".join(f"• {x}" for x in LN(s))),
        ("quote", "Quote block", lambda s: "\n".join(f"> {x}" for x in LN(s))), ("commas", "Words ko comma list", lambda s: ", ".join(s.split())),
        ("oneline", "Ek line me", lambda s: " ".join(LN(s))), ("wordlines", "Har word nayi line", lambda s: "\n".join(s.split())),
        ("sentencecase", "Sentence case", lambda s: ". ".join(x.strip().capitalize() for x in s.split("."))), ("initials", "Initials", lambda s: ".".join(w[0].upper() for w in s.split()) + "."),
        ("acronym", "Acronym", lambda s: "".join(w[0].upper() for w in s.split())), ("shout", "CHILLAO!!!", lambda s: s.upper() + "!!!"), ("whisper", "dheere bolo...", lambda s: s.lower() + "..."),
    ]
    for n_, d_, f_ in C:
        mk_t(tc, n_, d_, f_)

    # ============ /vibe (50) ============
    V = ("sporty artistic musical romantic honest patient creative curious ambitious generous humble polite shy outgoing energetic calm stubborn forgetful punctual messy "
         "organized fashionable adventurous talkative gullible sneaky mysterious wise hardworking optimistic sensitive confident competitive friendly geeky hungry thirsty sassy "
         "mature childish fearless clumsy flirty jolly moody nosy spicy witty zesty cheerful loyal gentle bold").split()
    vb = top("vibe", "50 fun personality meters")

    def mk_vibe(g, name):
        @g.command(name=name, description=f"{name.title()} level")
        async def _(i: discord.Interaction, member: discord.Member = None):
            m = member or i.user
            n = random.Random(f"{m.id}{name}{today()}").randint(0, 100)
            await i.response.send_message(f"✨ **{m.display_name}** ka **{name.title()}** level: **{n}%**\n`{'█' * (n // 10)}{'░' * (10 - n // 10)}`")

    for k, grp_names in enumerate((V[:25], V[25:50])):
        sg = sub(vb, f"set{k + 1}", f"Traits set {k + 1}")
        for n_ in grp_names:
            mk_vibe(sg, n_)

    # ============ /gen (50) ============
    EMO = {
        "faces": "😀 😃 😄 😁 😆 😅 😂 🤣 😊 😇 🙂 😉 😍 🥰 😘 😋 😎 🤩 🥳", "animals": "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🦆 🦉",
        "food": "🍕 🍔 🍟 🌭 🍿 🥓 🍳 🥞 🧇 🍗 🍖 🌮 🌯 🥪 🍜 🍝 🍣 🍤 🍩 🍪", "fruits": "🍎 🍐 🍊 🍋 🍌 🍉 🍇 🍓 🫐 🍈 🍒 🍑 🥭 🍍 🥥 🥝 🍅 🥑",
        "drinks": "☕ 🍵 🥤 🧃 🍺 🍻 🥂 🍷 🍸 🍹 🧋 🥛 🍶 🍾", "sports": "⚽ 🏀 🏈 ⚾ 🥎 🎾 🏐 🏉 🎱 🏓 🏸 🥊 🥋 ⛳ 🏏 🏑 🏒",
        "travel": "✈️ 🚗 🚕 🚌 🚎 🏎️ 🚓 🚑 🚒 🚜 🛵 🚲 🚂 🚁 🚀 🛸 ⛵ 🚢", "weather": "☀️ 🌤️ ⛅ 🌥️ ☁️ 🌦️ 🌧️ ⛈️ 🌩️ 🌨️ ❄️ 🌪️ 🌈 🌫️ 💨 💧",
        "nature": "🌲 🌳 🌴 🌵 🌾 🌿 ☘️ 🍀 🍁 🍂 🍃 🌱 🌻 🌼 🌷 🌹 🍄 🌰", "flowers": "🌸 💮 🏵️ 🌹 🥀 🌺 🌻 🌼 🌷 💐",
        "objects": "⌚ 📱 💻 ⌨️ 🖥️ 🖨️ 🖱️ 💡 🔦 📷 📺 📻 ⏰ 🔑 🔒 🧲 🧰", "tech": "💻 🖥️ ⌨️ 🖱️ 💾 💿 📀 🔌 🔋 📡 🛰️ 🤖 👾 🕹️ 🎮 📱",
        "music": "🎵 🎶 🎤 🎧 🎷 🎸 🎹 🎺 🎻 🥁 🪘 📯 🎼", "hearts": "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💖 💗 💓 💞 💕 💘 💝",
        "symbols": "✅ ❌ ⭕ ❗ ❓ 💯 🔥 ✨ ⚡ 💥 💫 ⭐ 🌟 ✔️ ➕ ➖ ➗ ♾️", "tools": "🔨 ⛏️ 🪓 🔧 🪛 🔩 ⚙️ 🧰 🪚 🗜️ ⚒️ 🛠️ 🧱",
        "clothes": "👕 👖 🧥 🧦 👗 👘 🥻 👔 👟 👞 🥾 👒 🎩 🧢 👓 🕶️", "buildings": "🏠 🏡 🏢 🏣 🏥 🏦 🏨 🏪 🏫 🏬 🏭 🏯 🏰 🗼 🗽 ⛪ 🕌",
        "transport": "🚲 🛴 🛹 🛼 🚃 🚄 🚅 🚆 🚇 🚈 🚉 🚊 🚝 🚞", "space": "🌑 🌒 🌓 🌔 🌕 🌖 🌗 🌘 🌙 🌎 🪐 ⭐ 🌠 ☄️ 🛸 🚀 👽",
        "party": "🎉 🎊 🎈 🎂 🍰 🎁 🎀 🪅 🎆 🎇 🧨 🥳 🍾 🪩", "medical": "💊 💉 🩺 🩹 🩸 🧬 🔬 🌡️ 🏥 🚑 😷 🦠",
        "school": "📚 📖 📝 ✏️ 🖊️ 📏 📐 🎒 🏫 🎓 🔬 🧮 🗂️ 📎", "money": "💰 💵 💴 💶 💷 💸 💳 🪙 🏦 💎 📈 📉 🧾",
        "gestures": "👍 👎 👏 🙌 🤝 🙏 ✌️ 🤞 🤟 🤘 👌 🤌 👋 🤙 💪 🫶",
    }
    gn = top("gen", "Emoji aur random generators (50)")
    ge, gm = sub(gn, "emoji", "Random emojis by category"), sub(gn, "make", "Random generators")

    def mk_emo(name, items):
        @ge.command(name=name, description=f"Random {name} emojis")
        async def _(i: discord.Interaction):
            await i.response.send_message(" ".join(random.sample(items.split(), 5)))

    for k_, v_ in EMO.items():
        mk_emo(k_, v_)
    R = random.SystemRandom()

    def mk_gen(name, desc, fn):
        @gm.command(name=name, description=desc)
        async def _(i: discord.Interaction):
            await i.response.send_message(str(fn())[:1900], allowed_mentions=NO)

    ADJ, NOUN = "Swift Brave Lazy Happy Cool Wild Silent Mighty Cosmic Pixel".split(), "Tiger Panda Ninja Wizard Dragon Falcon Gamer Rocket Shadow Knight".split()
    for n_, d_, f_ in [
        ("uuid", "Random UUID", lambda: uuid.uuid4()), ("hex", "32-char hex key", lambda: secrets.token_hex(16)), ("token", "URL-safe token", lambda: secrets.token_urlsafe(24)),
        ("pin", "6 digit PIN", lambda: "".join(R.choice(string.digits) for _ in range(6))),
        ("username", "Random username", lambda: f"{R.choice(ADJ)}{R.choice(NOUN)}{R.randint(1, 999)}"),
        ("bingo", "Bingo call", lambda: f"{R.choice('BINGO')}-{R.randint(1, 75)}"), ("lottery", "6 lottery numbers (1-49)", lambda: sorted(R.sample(range(1, 50), 6))),
        ("ipv4", "Random private IPv4", lambda: f"192.168.{R.randint(0, 255)}.{R.randint(1, 254)}"),
        ("mac", "Random MAC address", lambda: ":".join(f"{R.randint(0, 255):02x}" for _ in range(6))),
        ("palette", "5 random colors", lambda: " ".join(f"#{R.randint(0, 0xFFFFFF):06X}" for _ in range(5))),
        ("date", "Random date", lambda: datetime.date(2000, 1, 1) + datetime.timedelta(days=R.randint(0, 11000))),
        ("time", "Random time", lambda: f"{R.randint(0, 23):02d}:{R.randint(0, 59):02d}"),
        ("card", "Random playing card", lambda: R.choice("A 2 3 4 5 6 7 8 9 10 J Q K".split()) + R.choice("♠ ♥ ♦ ♣".split())),
    ]:
        mk_gen(n_, d_, f_)

    def mk_die(n):
        @gm.command(name=f"d{n}", description=f"Roll a d{n}")
        async def _(i: discord.Interaction):
            await i.response.send_message(f"🎲 d{n}: **{R.randint(1, n)}**")

    for n_ in (4, 6, 8, 10, 12, 20, 100):
        mk_die(n_)

    @gm.command(name="lorem", description="Lorem ipsum text")
    async def _(i: discord.Interaction, words: app_commands.Range[int, 5, 100] = 20):
        base = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua".split()
        await i.response.send_message(" ".join(R.choice(base) for _ in range(words)).capitalize() + ".")

    def mk_names(name, desc, fn):
        @gm.command(name=name, description=desc)
        async def _(i: discord.Interaction, names: str):
            n = [x for x in re.split(r"[,\s]+", names) if x]
            if len(n) < 2:
                return await i.response.send_message("❌ Kam se kam 2 naam do (comma/space se).", ephemeral=True)
            await i.response.send_message(fn(n)[:1900], allowed_mentions=NO)

    def _team(n):
        R.shuffle(n)
        return f"🔵 **Team A:** {', '.join(n[::2])}\n🔴 **Team B:** {', '.join(n[1::2])}"

    def _order(n):
        R.shuffle(n)
        return "\n".join(f"{k}. {x}" for k, x in enumerate(n, 1))

    mk_names("team", "Naam do teams me baanto", _team)
    mk_names("order", "Naam random order me", _order)
    mk_names("pickone", "Naamo me se ek chuno", lambda n: f"🎯 {R.choice(n)}")

    @gm.command(name="coins", description="Kai sikke uchhalo")
    async def _(i: discord.Interaction, count: app_commands.Range[int, 1, 100] = 10):
        h = sum(R.random() < .5 for _ in range(count))
        await i.response.send_message(f"🪙 {count} sikke: **{h}** heads, **{count - h}** tails")

    # ============ /calc (50) + /phys (45) ============
    GEO = [
        ("circlearea", "Circle area: radius", lambda r: pi * r * r), ("circumference", "Circle circumference: radius", lambda r: 2 * pi * r),
        ("spherevol", "Sphere volume: radius", lambda r: 4 / 3 * pi * r ** 3), ("spherearea", "Sphere surface: radius", lambda r: 4 * pi * r * r),
        ("cubevol", "Cube volume: side", lambda a: a ** 3), ("cubearea", "Cube surface: side", lambda a: 6 * a * a),
        ("cylvol", "Cylinder volume: radius, height", lambda r, h: pi * r * r * h), ("cylarea", "Cylinder surface: radius, height", lambda r, h: 2 * pi * r * (r + h)),
        ("conevol", "Cone volume: radius, height", lambda r, h: pi * r * r * h / 3), ("slant", "Cone slant height: radius, height", lambda r, h: math.hypot(r, h)),
        ("triarea", "Triangle area: base, height", lambda b, h: b * h / 2), ("trapezoid", "Trapezoid area: a, b, height", lambda a, b, h: (a + b) / 2 * h),
        ("parallelogram", "Parallelogram area: base, height", lambda b, h: b * h), ("rhombus", "Rhombus area: diag1, diag2", lambda p, q: p * q / 2),
        ("ellipse", "Ellipse area: a, b", lambda a, b: pi * a * b), ("sector", "Sector area: radius, angle deg", lambda r, d: pi * r * r * d / 360),
        ("arc", "Arc length: radius, angle deg", lambda r, d: 2 * pi * r * d / 360), ("diagonal", "Rectangle diagonal: l, w", lambda l, w: math.hypot(l, w)),
        ("spacediag", "Box diagonal: l, w, h", lambda l, w, h: math.sqrt(l * l + w * w + h * h)), ("cuboidvol", "Cuboid volume: l, w, h", lambda l, w, h: l * w * h),
        ("heron", "Triangle area (Heron): a, b, c", lambda a, b, c: math.sqrt(((a + b + c) / 2) * ((a + b + c) / 2 - a) * ((a + b + c) / 2 - b) * ((a + b + c) / 2 - c))),
        ("polygon", "Regular polygon area: sides, length", lambda n, s: n * s * s / (4 * math.tan(pi / n))),
        ("pyramidvol", "Pyramid volume: base area, height", lambda b, h: b * h / 3), ("prismvol", "Prism volume: base area, height", lambda b, h: b * h),
        ("torusvol", "Torus volume: R, r", lambda R_, r: 2 * pi * pi * R_ * r * r),
    ]
    FIN = [
        ("discount", "Final price, saved: price, discount%", lambda p, d: (p * (1 - d / 100), p * d / 100)), ("markup", "Price after markup: cost, markup%", lambda c, m: c * (1 + m / 100)),
        ("tip", "Tip, total: bill, tip%", lambda b, t: (b * t / 100, b * (1 + t / 100))), ("gst", "GST, total: amount, rate%", lambda a, r: (a * r / 100, a * (1 + r / 100))),
        ("gstremove", "GST, base: total, rate%", lambda t, r: (t - t / (1 + r / 100), t / (1 + r / 100))), ("profit", "Profit, profit%: cost, sell", lambda c, s: (s - c, (s - c) / c * 100)),
        ("margin", "Profit margin%: cost, sell", lambda c, s: (s - c) / s * 100), ("roi", "ROI%: gain, cost", lambda g, c: g / c * 100),
        ("cagr", "CAGR%: start, end, years", lambda a, b, y: ((b / a) ** (1 / y) - 1) * 100), ("ci", "Compound interest, total: principal, rate%, years", lambda p, r, t: (p * (1 + r / 100) ** t - p, p * (1 + r / 100) ** t)),
        ("sip", "SIP future value: monthly, rate%, years", lambda m, r, y: m * (((1 + r / 1200) ** (y * 12) - 1) / (r / 1200)) * (1 + r / 1200)),
        ("rule72", "Years to double: rate%", lambda r: 72 / r), ("inflation", "Future price: price, rate%, years", lambda p, r, y: p * (1 + r / 100) ** y),
        ("tax", "Tax, net: income, rate%", lambda i, r: (i * r / 100, i * (1 - r / 100))), ("ctc2month", "Monthly from yearly: yearly", lambda y: y / 12),
        ("hourly", "Hourly from yearly (2080h): yearly", lambda y: y / 2080), ("splitbill", "Per person: total, people", lambda t, n: t / n),
        ("percentof", "X% of Y: percent, of", lambda p, y: p * y / 100), ("whatpercent", "A is what % of B: a, b", lambda a, b: a / b * 100),
        ("increase", "Increase by %: value, %", lambda v, p: v * (1 + p / 100)), ("decrease", "Decrease by %: value, %", lambda v, p: v * (1 - p / 100)),
        ("ratio", "Simplify ratio: a, b", lambda a, b: f"{int(a) // math.gcd(int(a), int(b))}:{int(b) // math.gcd(int(a), int(b))}"),
        ("unitprice", "Price per unit: price, qty", lambda p, q: p / q), ("breakeven", "Break-even units: fixed, price, var cost", lambda f, p, v: f / (p - v)),
        ("fd", "FD maturity (quarterly): principal, rate%, years", lambda p, r, y: p * (1 + r / 400) ** (4 * y)),
    ]
    PHY = [
        ("speed", "Speed: distance, time", lambda d, t: d / t), ("distance", "Distance: speed, time", lambda v, t: v * t), ("time", "Time: distance, speed", lambda d, v: d / v),
        ("accel", "Acceleration: velocity change, time", lambda v, t: v / t), ("force", "Force F=ma: mass, accel", lambda m, a: m * a), ("weight", "Weight in N: mass kg", lambda m: m * 9.80665),
        ("work", "Work: force, distance", lambda f, d: f * d), ("power", "Power: work, time", lambda w, t: w / t), ("ke", "Kinetic energy: mass, velocity", lambda m, v: m * v * v / 2),
        ("pe", "Potential energy: mass, height", lambda m, h: m * 9.80665 * h), ("momentum", "Momentum: mass, velocity", lambda m, v: m * v), ("impulse", "Impulse: force, time", lambda f, t: f * t),
        ("density", "Density: mass, volume", lambda m, v: m / v), ("pressure", "Pressure: force, area", lambda f, a: f / a), ("ohmv", "Voltage V=IR: current, resistance", lambda i, r: i * r),
        ("ohmi", "Current I=V/R: voltage, resistance", lambda v, r: v / r), ("ohmr", "Resistance R=V/I: voltage, current", lambda v, i: v / i), ("elecpower", "Electric power P=VI: voltage, current", lambda v, i: v * i),
        ("wavelength", "Wavelength: speed, frequency", lambda v, f: v / f), ("period", "Period: frequency", lambda f: 1 / f),
        ("escape", "Escape velocity m/s: mass kg, radius m", lambda M, r: math.sqrt(2 * 6.674e-11 * M / r)), ("gravity", "Gravity force: m1, m2, distance", lambda a, b, r: 6.674e-11 * a * b / r / r),
        ("freefall", "Free fall time, speed: height", lambda h: (math.sqrt(2 * h / 9.80665), math.sqrt(2 * 9.80665 * h))),
        ("projectile", "Projectile range: speed, angle deg", lambda v, a: v * v * math.sin(math.radians(2 * a)) / 9.80665), ("heat", "Heat Q=mc dT: mass, c, dT", lambda m, c, t: m * c * t),
    ]

    def fmt_out(label, v):
        v = v if isinstance(v, tuple) else (v,)
        return f"📐 {label} = " + " | ".join(f"**{x}**" if isinstance(x, str) else f"**{gf(x)}**" for x in v)

    def mk_calc(g, name, desc, fn):
        k, label = fn.__code__.co_argcount, desc.split(":")[0]

        async def run(i, *a):
            try:
                r = fmt_out(label, fn(*a))
            except Exception:
                r = "❌ Calculate nahi ho paya (values check karo)."
            await i.response.send_message(r)
        if k == 1:
            @g.command(name=name, description=desc)
            async def _(i: discord.Interaction, a: float):
                await run(i, a)
        elif k == 2:
            @g.command(name=name, description=desc)
            async def _(i: discord.Interaction, a: float, b: float):
                await run(i, a, b)
        else:
            @g.command(name=name, description=desc)
            async def _(i: discord.Interaction, a: float, b: float, c: float):
                await run(i, a, b, c)

    ca, ph = top("calcx", "Geometry aur finance calculators (50)"), top("phys", "Physics aur statistics (45)")
    for g_, name_, tbl in [(sub(ca, "geometry", "Geometry formulas"), "geo", GEO), (sub(ca, "finance", "Finance formulas"), "fin", FIN), (sub(ph, "physics", "Physics formulas"), "phy", PHY)]:
        for n_, d_, f_ in tbl:
            mk_calc(g_, n_, d_, f_)
    qs = lambda x, k: statistics.quantiles(x, n=4)[k]
    ST = [("mean", statistics.mean), ("median", statistics.median), ("mode", statistics.mode), ("range", lambda x: max(x) - min(x)), ("variance", statistics.variance),
          ("stdev", statistics.stdev), ("pvariance", statistics.pvariance), ("pstdev", statistics.pstdev), ("sum", sum), ("product", math.prod), ("min", min), ("max", max),
          ("count", len), ("sort", sorted), ("q1", lambda x: qs(x, 0)), ("q3", lambda x: qs(x, 2)), ("iqr", lambda x: qs(x, 2) - qs(x, 0)), ("geomean", statistics.geometric_mean),
          ("harmean", statistics.harmonic_mean), ("cumsum", lambda x: [sum(x[:k + 1]) for k in range(len(x))])]
    sg_st = sub(ph, "stats", "Statistics (numbers comma/space se)")

    def mk_stat(name, fn):
        @sg_st.command(name=name, description=f"{name} of numbers")
        async def _(i: discord.Interaction, numbers: str):
            try:
                r = fn([float(x) for x in re.split(r"[,\s]+", numbers.strip()) if x])
                r = ", ".join(gf(x) for x in r) if isinstance(r, list) else gf(r)
            except Exception:
                r = "❌ Numbers comma ya space se alag karke do."
            await i.response.send_message(f"📊 {name} = **{r}**")

    for n_, f_ in ST:
        mk_stat(n_, f_)

    # ============ /clock (50) ============
    CITY = ("delhi:Asia/Kolkata mumbai:Asia/Kolkata kolkata:Asia/Kolkata chennai:Asia/Kolkata hyderabad:Asia/Kolkata karachi:Asia/Karachi dhaka:Asia/Dhaka kathmandu:Asia/Kathmandu "
            "colombo:Asia/Colombo dubai:Asia/Dubai riyadh:Asia/Riyadh tehran:Asia/Tehran istanbul:Europe/Istanbul moscow:Europe/Moscow london:Europe/London paris:Europe/Paris "
            "berlin:Europe/Berlin madrid:Europe/Madrid rome:Europe/Rome amsterdam:Europe/Amsterdam zurich:Europe/Zurich athens:Europe/Athens cairo:Africa/Cairo lagos:Africa/Lagos "
            "nairobi:Africa/Nairobi johannesburg:Africa/Johannesburg newyork:America/New_York chicago:America/Chicago denver:America/Denver losangeles:America/Los_Angeles "
            "toronto:America/Toronto vancouver:America/Vancouver mexico:America/Mexico_City saopaulo:America/Sao_Paulo bogota:America/Bogota tokyo:Asia/Tokyo seoul:Asia/Seoul "
            "beijing:Asia/Shanghai hongkong:Asia/Hong_Kong singapore:Asia/Singapore bangkok:Asia/Bangkok jakarta:Asia/Jakarta manila:Asia/Manila sydney:Australia/Sydney "
            "melbourne:Australia/Melbourne auckland:Pacific/Auckland honolulu:Pacific/Honolulu lahore:Asia/Karachi islamabad:Asia/Karachi doha:Asia/Qatar kabul:Asia/Kabul "
            "baghdad:Asia/Baghdad tashkent:Asia/Tashkent").split()
    ck = top("clock", "Duniya ke 50 shehron ka time")

    def mk_clock(g, name, tz):
        @g.command(name=name, description=f"{name.title()} ka abhi ka time")
        async def _(i: discord.Interaction):
            try:
                from zoneinfo import ZoneInfo
                n = datetime.datetime.now(ZoneInfo(tz))
                await i.response.send_message(f"🕒 **{name.title()}** ({tz}): **{n:%I:%M %p}**, {n:%a %d %b %Y}")
            except Exception:
                await i.response.send_message("❌ Timezone data nahi mila (requirements me `tzdata` zaruri hai).", ephemeral=True)

    for k_ in range(2):
        sg = sub(ck, f"world{k_ + 1}", f"Shehar set {k_ + 1}")
        for c_ in CITY[k_ * 25:(k_ + 1) * 25]:
            mk_clock(sg, *c_.split(":"))

    # ============ /css (100 colors) ============
    COL = ("aliceblue:f0f8ff aqua:00ffff aquamarine:7fffd4 azure:f0ffff beige:f5f5dc bisque:ffe4c4 black:000000 blue:0000ff blueviolet:8a2be2 brown:a52a2a cadetblue:5f9ea0 "
           "chartreuse:7fff00 chocolate:d2691e coral:ff7f50 cornflowerblue:6495ed crimson:dc143c cyan:00ffff darkblue:00008b darkcyan:008b8b darkgray:a9a9a9 darkgreen:006400 "
           "darkmagenta:8b008b darkorange:ff8c00 darkred:8b0000 deeppink:ff1493 deepskyblue:00bfff dimgray:696969 dodgerblue:1e90ff firebrick:b22222 forestgreen:228b22 fuchsia:ff00ff "
           "gold:ffd700 gray:808080 green:008000 greenyellow:adff2f hotpink:ff69b4 indianred:cd5c5c indigo:4b0082 ivory:fffff0 khaki:f0e68c lightblue:add8e6 lightcoral:f08080 "
           "lightgreen:90ee90 lightgray:d3d3d3 lightpink:ffb6c1 lightsalmon:ffa07a lightskyblue:87cefa lime:00ff00 limegreen:32cd32 magenta:ff00ff maroon:800000 "
           "mediumpurple:9370db navy:000080 olive:808000 olivedrab:6b8e23 orange:ffa500 orangered:ff4500 orchid:da70d6 palegreen:98fb98 paleturquoise:afeeee peachpuff:ffdab9 "
           "peru:cd853f pink:ffc0cb plum:dda0dd powderblue:b0e0e6 purple:800080 red:ff0000 rosybrown:bc8f8f royalblue:4169e1 salmon:fa8072 sandybrown:f4a460 seagreen:2e8b57 "
           "sienna:a0522d silver:c0c0c0 skyblue:87ceeb slateblue:6a5acd slategray:708090 snow:fffafa springgreen:00ff7f steelblue:4682b4 tan:d2b48c teal:008080 thistle:d8bfd8 "
           "tomato:ff6347 turquoise:40e0d0 violet:ee82ee wheat:f5deb3 white:ffffff yellow:ffff00 yellowgreen:9acd32 "
           "darkkhaki:bdb76b darkviolet:9400d3 goldenrod:daa520 lavender:e6e6fa lawngreen:7cfc00 linen:faf0e6 midnightblue:191970 moccasin:ffe4b5 mintcream:f5fffa").split()[:100]
    cs_ = top("css", "100 named colors ka preview")

    def mk_col(g, name, hx):
        @g.command(name=name, description=f"{name} color")
        async def _(i: discord.Interaction):
            v = int(hx, 16)
            await i.response.send_message(embed=emb(f"🎨 {name} (#{hx.upper()})", f"RGB: **{v >> 16}, {(v >> 8) & 255}, {v & 255}**", v))

    for k_ in range(4):
        sg = sub(cs_, f"set{k_ + 1}", f"Colors set {k_ + 1}")
        for c_ in COL[k_ * 25:(k_ + 1) * 25]:
            mk_col(sg, *c_.split(":"))

    # ============ /element (118) ============
    EL = ("H,Hydrogen,1.008 He,Helium,4.0026 Li,Lithium,6.94 Be,Beryllium,9.0122 B,Boron,10.81 C,Carbon,12.011 N,Nitrogen,14.007 O,Oxygen,15.999 F,Fluorine,18.998 Ne,Neon,20.18 "
          "Na,Sodium,22.99 Mg,Magnesium,24.305 Al,Aluminium,26.982 Si,Silicon,28.085 P,Phosphorus,30.974 S,Sulfur,32.06 Cl,Chlorine,35.45 Ar,Argon,39.948 K,Potassium,39.098 "
          "Ca,Calcium,40.078 Sc,Scandium,44.956 Ti,Titanium,47.867 V,Vanadium,50.942 Cr,Chromium,51.996 Mn,Manganese,54.938 Fe,Iron,55.845 Co,Cobalt,58.933 Ni,Nickel,58.693 "
          "Cu,Copper,63.546 Zn,Zinc,65.38 Ga,Gallium,69.723 Ge,Germanium,72.63 As,Arsenic,74.922 Se,Selenium,78.971 Br,Bromine,79.904 Kr,Krypton,83.798 Rb,Rubidium,85.468 "
          "Sr,Strontium,87.62 Y,Yttrium,88.906 Zr,Zirconium,91.224 Nb,Niobium,92.906 Mo,Molybdenum,95.95 Tc,Technetium,98 Ru,Ruthenium,101.07 Rh,Rhodium,102.91 Pd,Palladium,106.42 "
          "Ag,Silver,107.87 Cd,Cadmium,112.41 In,Indium,114.82 Sn,Tin,118.71 Sb,Antimony,121.76 Te,Tellurium,127.6 I,Iodine,126.9 Xe,Xenon,131.29 Cs,Caesium,132.91 Ba,Barium,137.33 "
          "La,Lanthanum,138.91 Ce,Cerium,140.12 Pr,Praseodymium,140.91 Nd,Neodymium,144.24 Pm,Promethium,145 Sm,Samarium,150.36 Eu,Europium,151.96 Gd,Gadolinium,157.25 Tb,Terbium,158.93 "
          "Dy,Dysprosium,162.5 Ho,Holmium,164.93 Er,Erbium,167.26 Tm,Thulium,168.93 Yb,Ytterbium,173.05 Lu,Lutetium,174.97 Hf,Hafnium,178.49 Ta,Tantalum,180.95 W,Tungsten,183.84 "
          "Re,Rhenium,186.21 Os,Osmium,190.23 Ir,Iridium,192.22 Pt,Platinum,195.08 Au,Gold,196.97 Hg,Mercury,200.59 Tl,Thallium,204.38 Pb,Lead,207.2 Bi,Bismuth,208.98 Po,Polonium,209 "
          "At,Astatine,210 Rn,Radon,222 Fr,Francium,223 Ra,Radium,226 Ac,Actinium,227 Th,Thorium,232.04 Pa,Protactinium,231.04 U,Uranium,238.03 Np,Neptunium,237 Pu,Plutonium,244 "
          "Am,Americium,243 Cm,Curium,247 Bk,Berkelium,247 Cf,Californium,251 Es,Einsteinium,252 Fm,Fermium,257 Md,Mendelevium,258 No,Nobelium,259 Lr,Lawrencium,266 Rf,Rutherfordium,267 "
          "Db,Dubnium,268 Sg,Seaborgium,269 Bh,Bohrium,270 Hs,Hassium,277 Mt,Meitnerium,278 Ds,Darmstadtium,281 Rg,Roentgenium,282 Cn,Copernicium,285 Nh,Nihonium,286 Fl,Flerovium,289 "
          "Mc,Moscovium,290 Lv,Livermorium,293 Ts,Tennessine,294 Og,Oganesson,294").split()
    el = top("element", "Periodic table: 118 elements")

    def mk_el(g, num, sym, name, mass):
        @g.command(name=name.lower(), description=f"{name} ({sym}) info")
        async def _(i: discord.Interaction):
            per = next(p for p, last in enumerate((2, 10, 18, 36, 54, 86, 118), 1) if num <= last)
            e = emb(f"⚛️ {name} ({sym})", color=0x00D4FF)
            e.add_field(name="Atomic number", value=num)
            e.add_field(name="Atomic mass", value=mass)
            e.add_field(name="Period", value=per)
            await i.response.send_message(embed=e)

    for k_ in range(5):
        sg = sub(el, f"part{k_ + 1}", f"Elements {k_ * 25 + 1}-{min(118, (k_ + 1) * 25)}")
        for n_, c_ in enumerate(EL[k_ * 25:(k_ + 1) * 25], k_ * 25 + 1):
            s_, nm, ms = c_.split(",")
            mk_el(sg, n_, s_, nm, ms)

    # ============ /zodiac (24) ============
    WEST = ("aries|Mar 21-Apr 19|Fire|Brave, bold, energetic;taurus|Apr 20-May 20|Earth|Patient, loyal, stubborn;gemini|May 21-Jun 20|Air|Curious, witty, adaptable;"
            "cancer|Jun 21-Jul 22|Water|Caring, emotional, protective;leo|Jul 23-Aug 22|Fire|Confident, generous, dramatic;virgo|Aug 23-Sep 22|Earth|Practical, analytical, neat;"
            "libra|Sep 23-Oct 22|Air|Fair, social, charming;scorpio|Oct 23-Nov 21|Water|Passionate, intense, loyal;sagittarius|Nov 22-Dec 21|Fire|Free, funny, adventurous;"
            "capricorn|Dec 22-Jan 19|Earth|Ambitious, disciplined, calm;aquarius|Jan 20-Feb 18|Air|Original, friendly, independent;pisces|Feb 19-Mar 20|Water|Dreamy, kind, artistic").split(";")
    FORT = ["Aaj achhi khabar milegi. 🍀", "Kisi purane dost se baat hogi. 📞", "Paisa kharch hoga par khushi milegi. 💸", "Naya mauka darwaze par hai. 🚪", "Dhairya rakho, sab theek hoga. ✨", "Aaj dil ki suno. 💖"]
    zd = top("zodiac", "Rashi aur Chinese zodiac")
    zw, zc = sub(zd, "western", "12 western signs"), sub(zd, "chinese", "12 Chinese animals")

    def mk_west(row):
        name, dates, elem, traits = row.split("|")

        @zw.command(name=name, description=f"{name.title()} info + aaj ka rashifal")
        async def _(i: discord.Interaction):
            e = emb(f"♈ {name.title()}", f"📅 {dates}\n🔥 Element: **{elem}**\n💫 {traits}\n\n**Aaj ka rashifal:** {random.Random(name + today()).choice(FORT)}", 0xFF4FD8)
            await i.response.send_message(embed=e)

    for r_ in WEST:
        mk_west(r_)
    ANI = "rat ox tiger rabbit dragon snake horse goat monkey rooster dog pig".split()
    TRT = "Smart,Strong,Brave,Gentle,Powerful,Wise,Free,Calm,Clever,Honest,Loyal,Generous".split(",")

    def mk_cn(k, name):
        @zc.command(name=name, description=f"{name.title()} years aur gun")
        async def _(i: discord.Interaction):
            ys = [y for y in range(1960, 2036) if (y - 4) % 12 == k]
            await i.response.send_message(embed=emb(f"🐲 {name.title()}", f"Years: {', '.join(map(str, ys))}\nGun: **{TRT[k]}**", 0xFEE75C))

    for k_, n_ in enumerate(ANI):
        mk_cn(k_, n_)
