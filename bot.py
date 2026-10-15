import telebot
import os
import json
import time
import random
import datetime
import html
import requests
import threading
from telebot import types

# ---------- Config ----------
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Set BOT_TOKEN environment variable (get a new token from @BotFather)")

SUPER_ADMINS = [6981270107, 5236267396, 8540469832, 8894028392, 5978049970, 8507634727, 8927441295]

bot = telebot.TeleBot(TOKEN)

# ---------- Files ----------
GMUTE_FILE = "gmute.json"
GENDER_FILE = "genders.json"             # manual /setgender overrides
GENDER_CACHE_FILE = "gender_cache.json"  # cached API results per name (saved forever)
MEMBERS_FILE = "members.json"            # group member cache
DAILY_FILE = "daily_waifu.json"          # today's locked pick per user per group

def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return []

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

gmuted_users = load_json(GMUTE_FILE)

genders = load_json(GENDER_FILE)
if not isinstance(genders, dict):
    genders = {}          # {user_id: "male"/"female"}

gender_cache = load_json(GENDER_CACHE_FILE)
if not isinstance(gender_cache, dict):
    gender_cache = {}     # {normalized_name: "male"/"female"}

members_cache = load_json(MEMBERS_FILE)
if not isinstance(members_cache, dict):
    members_cache = {}    # {chat_id: {user_id: {"n": name, "p": photo_file_id}}}

daily_waifu = load_json(DAILY_FILE)
if not isinstance(daily_waifu, dict):
    daily_waifu = {}      # {"chat_id:user_id": {"date", "pid", "bond", "name"}}

def get_user_id(message):
    """Extract user ID from a reply or from command text."""
    if message.reply_to_message:
        return message.reply_to_message.from_user.id
    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return None

# ---------- Fancy font (small caps) ----------
SMALL = {'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ꜰ','g':'ɢ','h':'ʜ','i':'ɪ',
         'j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ',
         's':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ'}
REVERSE = {v: k for k, v in SMALL.items()}

def fancy(text):
    """Convert name to small caps, e.g. Grey -> ɢ ʀ ᴇ ʏ"""
    return "  ".join(" ".join(SMALL.get(c, c) for c in word) for word in text.lower().split())

def normalize_name(name):
    """Convert any fancy-font name back to plain a-z for gender detection."""
    out = []
    for ch in (name or "").lower():
        if ch in REVERSE:
            out.append(REVERSE[ch])
        elif ch.isascii() and (ch.isalpha() or ch == " "):
            out.append(ch)
    return "".join(out).strip()

# ---------- Gender detection (API + cache) ----------
GENDERIZE_URL = "https://api.genderize.io/"
API_DAILY_LIMIT = 90  # stay under Genderize free tier (~100/day)
api_usage = {"date": "", "count": 0}

FEMALE_NAMES = {
    "sana","ayesha","aisha","fatima","khadija","zainab","maryam","maria","mahnoor",
    "hurain","ariba","anaya","samreen","bushra","hira","aliza","noor","eisha","amna",
    "mahira","sara","zara","laiba","minal","aiman","hana","hina","sadia","warda",
    "ifra","kiran","sehar","dua","eman","mishal","shanza","zoya","maha","rabia",
    "nimra","kanwal","jannat","aliya","alina","emaan","iqra","kinza","lubna","mehak",
    "nida","rimsha","saira","sobia","urooj","alice","emma","olivia","sophia","isabella",
    "mia","amelia","ella","ava","grace","chloe","lily","hannah","zoe","nobara","hinata",
    "sakura","nezuko","rem","makima","mitsuri","shinobu","yor","mikasa","annie","emilia",
}

def api_name_lookup(plain_name):
    """Ask genderize.io for one name. Returns 'male'/'female' or None.
    Only trusts results with decent probability + sample count."""
    today = datetime.date.today().isoformat()
    if api_usage["date"] != today:
        api_usage["date"] = today
        api_usage["count"] = 0
    if api_usage["count"] >= API_DAILY_LIMIT:
        return None  # quota over, fall back silently
    try:
        r = requests.get(GENDERIZE_URL, params={"name": plain_name}, timeout=6)
        if r.status_code != 200:
            return None
        data = r.json()
        api_usage["count"] += 1
        g = data.get("gender")
        prob = data.get("probability", 0) or 0
        count = data.get("count", 0) or 0
        if g in ("male", "female") and prob >= 0.75 and count >= 5:
            return g
    except Exception:
        pass
    return None

def detect_gender(uid, name):
    """Priority: manual setting > API cache > local list > API > male."""
    # 1) Manual /setgender override always wins
    g = genders.get(str(uid))
    if g:
        return g

    plain = normalize_name(name)
    if not plain:
        return "male"

    # 2) Cached API result for this name (saved forever, zero API cost)
    if plain in gender_cache:
        return gender_cache[plain]

    # 3) Local female-name list (instant, free)
    if any(fn == plain or fn in plain for fn in FEMALE_NAMES):
        return "female"

    # 4) Genderize.io API — first word works best for multi-word names
    first_word = plain.split()[0]
    result = api_name_lookup(first_word)
    if result:
        gender_cache[plain] = result
        save_json(GENDER_CACHE_FILE, gender_cache)
        return result

    # 5) Unknown / API down / quota over
    return "male"

# ---------- Member cache ----------
def remember_member(chat_id, user):
    """Store every member who sends a message (bots are skipped)."""
    if not user or user.is_bot:
        return
    members_cache.setdefault(str(chat_id), {}).setdefault(str(user.id), {})
    members_cache[str(chat_id)][str(user.id)]["n"] = user.first_name or "User"
    save_json(MEMBERS_FILE, members_cache)

def forget_member(chat_id, user_id):
    """Remove member from cache when they leave the group."""
    c = members_cache.get(str(chat_id), {})
    if str(user_id) in c:
        del c[str(user_id)]
        save_json(MEMBERS_FILE, members_cache)

def seed_admins(chat_id):
    """Fallback: if member pool is empty, add group admins to the cache."""
    try:
        for a in bot.get_chat_administrators(chat_id):
            remember_member(chat_id, a.user)
    except Exception:
        pass

# ---------- Profile picture ----------
def get_dp(user_id, chat_id):
    """Return cached profile photo, or fetch it from Telegram once and cache it."""
    cached = members_cache.get(str(chat_id), {}).get(str(user_id), {}).get("p")
    if cached:
        return cached
    try:
        photos = bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id  # largest size
            members_cache.setdefault(str(chat_id), {}).setdefault(str(user_id), {})["p"] = file_id
            save_json(MEMBERS_FILE, members_cache)
            return file_id
    except Exception:
        pass
    return None

# ---------- Daily waifu (locked for 24h) ----------
def save_daily():
    """Prune old entries — only today's picks are kept, auto reset at midnight."""
    global daily_waifu
    today = datetime.date.today().isoformat()
    daily_waifu = {k: v for k, v in daily_waifu.items() if v.get("date") == today}
    save_json(DAILY_FILE, daily_waifu)

def build_pool(chat_id, uid, target_gender):
    """All cached members of this group matching the target gender, excluding self."""
    pool = []
    for pid, info in members_cache.get(str(chat_id), {}).items():
        pid = int(pid)
        if pid == uid:
            continue
        name = info.get("n", "User")
        if detect_gender(pid, name) == target_gender:
            pool.append((pid, name))
    return pool

def get_daily_pick(chat_id, uid, my_gender):
    """Return (pid, name, bond) locked for today. Creates the pick on first call.
    Returns None if no matching member exists in the group."""
    today = datetime.date.today().isoformat()
    key = f"{chat_id}:{uid}"
    target_gender = "male" if my_gender == "female" else "female"

    saved = daily_waifu.get(key)
    if saved and saved.get("date") == today:
        pid = saved.get("pid")
        # Verify the picked member is still in the group cache
        info = members_cache.get(str(chat_id), {}).get(str(pid))
        if info:
            return pid, info.get("n", saved.get("name", "User")), saved.get("bond", 50)
        # Member left the group — fall through and re-pick

    # First call today (or pick left): build pool and lock a new pick
    pool = build_pool(chat_id, uid, target_gender)
    if not pool:
        seed_admins(chat_id)   # fallback: try admins
        pool = build_pool(chat_id, uid, target_gender)
    if not pool:
        return None

    rng = random.Random(f"{uid}:{today}")   # stable per user per day
    pid, pname = rng.choice(pool)
    bond = rng.randint(5, 100)

    daily_waifu[key] = {"date": today, "pid": pid, "bond": bond, "name": pname}
    save_daily()
    return pid, pname, bond

# ---------- Start ----------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📜 Commands", callback_data="show_commands"))
    bot.send_message(message.chat.id,
        f"Hello 👋 and welcome 🥂 {message.from_user.first_name}",
        reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_commands")
def show_commands(call):
    bot.send_message(call.message.chat.id, """
✨ Waifu:
/waifu — random waifu/husbando from group members (with their profile pic!)
Same result all day — resets at midnight.

/setgender male|female — set your gender (always wins over auto-detect)
/gender — check your current gender

🔒 Admin:
/gmute /ungmute — globally mute a user
""")

# ---------- Waifu ----------
WAIFU_COOLDOWN = 15  # seconds (anti-spam, result is same all day anyway)
last_waifu_time = {}

@bot.message_handler(commands=["waifu"])
def waifu_cmd(m):
    if m.chat.type == "private":
        bot.reply_to(m, "😅 This command works in groups — try it with your friends!")
        return
    user = m.from_user
    remember_member(m.chat.id, user)
    uid = user.id

    # Cooldown check (anti-spam only — the pick itself is locked all day)
    now = time.time()
    if now - last_waifu_time.get(uid, 0) < WAIFU_COOLDOWN:
        bot.reply_to(m, "⏳ You just asked... your waifu is not going anywhere 😄")
        return
    last_waifu_time[uid] = now

    # Gender: male gets female waifu, female gets male husbando
    my_gender = detect_gender(uid, user.first_name)

    pick = get_daily_pick(m.chat.id, uid, my_gender)
    if not pick:
        target_gender = "male" if my_gender == "female" else "female"
        bot.reply_to(m,
            f"😦 No {'male' if target_gender == 'male' else 'female'} member found in this group!\n"
            "Members should use /setgender male or female — then try /waifu again 😉")
        return

    pid, pname, bond = pick
    target_word = "Waifu" if my_gender != "female" else "Husbando"
    emoji = "🌸" if target_word == "Waifu" else "🔥"

    req_mention = f"<a href='tg://user?id={uid}'>{html.escape(user.first_name or 'User')}</a>"
    pick_mention = f"<a href='tg://user?id={pid}'>{fancy(pname)}</a>"

    caption = (f"✨ {req_mention}'s Today's {target_word} ✨\n"
               "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
               f"┠➤ ɴᴀᴍᴇ: {pick_mention}\n"
               f"┠➤ ʙᴏɴᴅ ᴘᴇʀᴄᴇɴᴛᴀɢᴇ: <b>{bond}%</b> {emoji}\n"
               "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈")

    msg = bot.send_message(m.chat.id, f"🔍 Finding your {target_word}...")
    try:
        dp = get_dp(pid, m.chat.id)   # picked member's profile photo (cached)
        if dp:
            try:
                bot.send_photo(m.chat.id, dp, caption=caption, parse_mode="HTML")
            except Exception:
                bot.send_message(m.chat.id, caption, parse_mode="HTML")
        else:
            # No profile photo set — send caption only
            bot.send_message(m.chat.id, caption + "\n🥀 <i>(No profile pic found...)</i>", parse_mode="HTML")
        try:
            bot.delete_message(msg.chat.id, msg.message_id)
        except Exception:
            pass
    except Exception:
        try:
            bot.edit_message_text("❌ Something went wrong, try again later.", msg.chat.id, msg.message_id)
        except Exception:
            pass

# ---------- Gender set / check ----------
@bot.message_handler(commands=["setgender"])
def set_gender(message):
    # Admins can set gender for others via reply
    uid_target = get_user_id(message)
    if message.reply_to_message and message.from_user.id in SUPER_ADMINS and uid_target:
        uid = uid_target
    else:
        uid = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2 or parts[-1].lower() not in ("male", "female", "boy", "girl"):
        bot.reply_to(message, "Use: /setgender male  or  /setgender female")
        return
    g = "male" if parts[-1].lower() in ("male", "boy") else "female"
    genders[str(uid)] = g
    save_json(GENDER_FILE, genders)
    # New gender takes effect from the NEXT pick (today's locked pick stays)
    bot.reply_to(message, f"✅ Gender set to {g}.\n/waifu will use it from your next daily pick.")

@bot.message_handler(commands=["gender"])
def check_gender(message):
    g = genders.get(str(message.from_user.id))
    if g:
        bot.reply_to(message, f"ℹ️ Your saved gender: {g}")
    else:
        g2 = detect_gender(message.from_user.id, message.from_user.first_name)
        bot.reply_to(message, f"ℹ️ Detected gender: {g2}\nWrong? Fix it with /setgender male or female")

# ---------- Group join / leave ----------
@bot.message_handler(content_types=["new_chat_members"])
def on_added(m):
    for u in m.new_chat_members:
        remember_member(m.chat.id, u)
        if u.id == bot.get_me().id:
            bot.send_message(m.chat.id,
                "🥀 Thanks for adding me!\n"
                "✨ Use /waifu — get a random waifu/husbando from group members!\n"
                "ℹ️ Detection is automatic, but /setgender male or female makes it 100% accurate!")

@bot.message_handler(content_types=["left_chat_member"])
def on_left(m):
    forget_member(m.chat.id, m.left_chat_member.id)

# ---------- GMUTE (global mute) ----------
@bot.message_handler(commands=["gmute", "ungmute"])
def handle_gmute(message):
    if message.from_user.id not in SUPER_ADMINS:
        return
    uid = get_user_id(message)
    if not uid:
        bot.reply_to(message, "Reply to a message or use /gmute user_id")
        return
    if message.text.startswith("/gmute") and not message.text.startswith("/ungmute"):
        if uid not in gmuted_users:
            gmuted_users.append(uid)
            save_json(GMUTE_FILE, gmuted_users)
            bot.send_message(message.chat.id, f"🔇 User {uid} gmuted globally.")
        else:
            bot.send_message(message.chat.id, "ℹ️ User is already gmuted.")
    else:
        if uid in gmuted_users:
            gmuted_users.remove(uid)
            save_json(GMUTE_FILE, gmuted_users)
            bot.send_message(message.chat.id, f"🔊 User {uid} ung-muted globally.")
        else:
            bot.send_message(message.chat.id, "ℹ️ User was not gmuted.")

# ---------- Catch-all: track members + delete gmuted users' messages ----------
@bot.message_handler(content_types=["photo", "video", "audio", "sticker", "voice", "document", "animation"])
def handle_media(message):
    remember_member(message.chat.id, message.from_user)
    if message.from_user.id in gmuted_users:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

@bot.message_handler(func=lambda m: True)
def catch_all(message):
    remember_member(message.chat.id, message.from_user)
    if message.from_user.id in gmuted_users:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

@bot.edited_message_handler(func=lambda m: True)
def delete_edited(m):
    if m.from_user.id in gmuted_users:
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except Exception:
            pass

# ---------- Flask keep-alive (for Render) ----------
try:
    import main
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=main.app.run,
                     kwargs={"host": "0.0.0.0", "port": port},
                     daemon=True).start()
except ModuleNotFoundError:
    print("main.py not found — skipping Flask keep-alive (fine for local testing)")

print("Bot is running...")
bot.infinity_polling()
