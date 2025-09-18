import telebot
import os
import json
import time
import threading
from telebot import types

# Bot config
TOKEN = "8471095733:AAHpBQmvv-Y9csdgpA7NtmfA-pT2gPRiEFw"
OWNER_ID = 8452694781
FRIEND_ID = 5971805747
bot = telebot.TeleBot(TOKEN)

# Files
AUTH_FILE = "auth.json"
EDIT_AUTH_FILE = "auth_edit.json"
PUNISH_FILE = "punish.json"
DELAY_FILE = "delay.json"
DELAY_POWER_FILE = "delay_power.json"

# Utils
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return []

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

def get_user_id(message):
    if message.reply_to_message:
        return message.reply_to_message.from_user.id
    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return None

# Load data
auth_users = load_json(AUTH_FILE)
auth_edit_users = load_json(EDIT_AUTH_FILE)
punished_users = load_json(PUNISH_FILE)
delay_power_users = load_json(DELAY_POWER_FILE)
delay_time = load_json(DELAY_FILE)
delay_time = delay_time if isinstance(delay_time, int) else 10

# Authorizations
AUTHORIZED_PUNISH_USERS = [OWNER_ID, FRIEND_ID]

# Start
@bot.message_handler(commands=["start"])
def send_welcome(message):
    name = message.from_user.first_name
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("📜 Commands", callback_data="show_commands")
    markup.add(btn)
    bot.send_message(message.chat.id, f"Hello 👋 and welcome 🥂 {name}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_commands")
def show_commands(call):
    bot.send_message(call.message.chat.id, """
Available Commands:
/auth /unauth – (Media+sticker+audio+video+gif)
/authedit /unauthedit – edit msg delete control
/punish /unpunish – globally restrict users
/powerdelay – allow user to set delay time
/setdely [10s/1m/30s] – set media delete time
""")

# Auth
@bot.message_handler(commands=["auth", "unauth"])
def handle_auth(message):
    uid = get_user_id(message)
    if uid:
        if message.text.startswith("/auth"):
            if uid not in auth_users:
                auth_users.append(uid)
                save_json(AUTH_FILE, auth_users)
                bot.send_message(message.chat.id, f"✅ User {uid} authorized for media.")
            else:
                bot.send_message(message.chat.id, f"ℹ️ User {uid} is already authorized.")
        else:
            if uid in auth_users:
                auth_users.remove(uid)
                save_json(AUTH_FILE, auth_users)
                bot.send_message(message.chat.id, f"❌ User {uid} removed from media auth.")
            else:
                bot.send_message(message.chat.id, f"ℹ️ User {uid} was not authorized.")
    else:
        bot.reply_to(message, "Reply to a message or use /auth user_id")

# Edit Auth
@bot.message_handler(commands=["authedit", "unauthedit"])
def handle_auth_edit(message):
    uid = get_user_id(message)
    if uid:
        if message.text.startswith("/authedit"):
            if uid not in auth_edit_users:
                auth_edit_users.append(uid)
                save_json(EDIT_AUTH_FILE, auth_edit_users)
                bot.send_message(message.chat.id, f"✅ User {uid} allowed to edit messages.")
            else:
                bot.send_message(message.chat.id, f"ℹ️ User {uid} already allowed.")
        else:
            if uid in auth_edit_users:
                auth_edit_users.remove(uid)
                save_json(EDIT_AUTH_FILE, auth_edit_users)
                bot.send_message(message.chat.id, f"❌ User {uid} no longer allowed to edit.")
            else:
                bot.send_message(message.chat.id, f"ℹ️ User {uid} was not in edit list.")
    else:
        bot.reply_to(message, "Reply to a message or use /authedit user_id")

# Punish
@bot.message_handler(commands=["punish", "unpunish"])
def handle_punish(message):
    if message.from_user.id not in AUTHORIZED_PUNISH_USERS:
        return
    uid = get_user_id(message)
    if uid:
        if message.text.startswith("/punish"):
            if uid not in punished_users:
                punished_users.append(uid)
                save_json(PUNISH_FILE, punished_users)
                bot.send_message(message.chat.id, f"🚫 User {uid} punished globally.")
            else:
                bot.send_message(message.chat.id, f"ℹ️ User {uid} already punished.")
        else:
            if uid in punished_users:
                punished_users.remove(uid)
                save_json(PUNISH_FILE, punished_users)
                bot.send_message(message.chat.id, f"✅ User {uid} unpunished globally.")
            else:
                bot.send_message(message.chat.id, f"ℹ️ User {uid} was not punished.")
    else:
        bot.reply_to(message, "Reply to a message or use /punish user_id")

# Power Delay Access
@bot.message_handler(commands=["powerdelay"])
def grant_delay_power(message):
    uid = get_user_id(message)
    if uid:
        if uid not in delay_power_users:
            delay_power_users.append(uid)
            save_json(DELAY_POWER_FILE, delay_power_users)
            bot.send_message(message.chat.id, f"✅ User {uid} granted /setdely permission.")
        else:
            bot.send_message(message.chat.id, f"ℹ️ User {uid} already has /setdely permission.")
    else:
        bot.reply_to(message, "❌ Reply to a user or give a valid user ID like:\n/powerdelay 12345678", parse_mode="Markdown")

# Set Delay Time
@bot.message_handler(commands=["setdely"])
def set_delay_time(message):
    if message.from_user.id not in delay_power_users + [OWNER_ID, FRIEND_ID]:
        return
    parts = message.text.split()
    if len(parts) >= 2:
        t = parts[1].lower()
        try:
            if t.endswith("s"):
                val = int(t[:-1])
            elif t.endswith("m"):
                val = int(t[:-1]) * 60
            else:
                val = int(t)
            global delay_time
            delay_time = val
            save_json(DELAY_FILE, delay_time)
            bot.send_message(message.chat.id, f"⏳ Media delete delay set to {val} seconds.")
        except:
            bot.send_message(message.chat.id, "❌ Invalid time format. Use: /setdely 10s or /setdely 1m")
    else:
        bot.send_message(message.chat.id, "❌ Please specify time. Example: /setdely 30s")

# Delete edited messages
@bot.edited_message_handler(func=lambda m: True)
def delete_edited(m):
    if m.from_user.id not in auth_edit_users:
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except:
            pass

# Media deletion handler
def media_delete_later(chat_id, msg_id, user_id):
    if user_id in auth_users:
        return
    time.sleep(delay_time)
    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass

# Media handler
@bot.message_handler(content_types=["photo", "video", "audio", "sticker", "voice", "document", "animation"])
def handle_media(message):
    if message.from_user.id in punished_users:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        return
    threading.Thread(target=media_delete_later, args=(message.chat.id, message.message_id, message.from_user.id)).start()

# All message handler - punish check
@bot.message_handler(func=lambda m: True)
def auto_delete_if_punished(message):
    if message.from_user.id in punished_users:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

# Start Flask app for Render port bind
import threading
import main
threading.Thread(target=main.app.run, kwargs={"host": "0.0.0.0", "port": 10000}).start()

print("Bot is running...")
bot.infinity_polling()
