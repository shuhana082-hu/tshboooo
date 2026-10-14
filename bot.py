import os, sqlite3, html
from datetime import datetime
import telebot
from telebot import types

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB = os.getenv("DB_PATH", "bot.db")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
state = {}

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=conn()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
        wallet TEXT DEFAULT '', balance INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0,
        referred_by INTEGER, joined_at TEXT, total_cashout INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT UNIQUE,
        title TEXT, invite_link TEXT, enabled INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS cashouts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,
        wallet TEXT,created_at TEXT,status TEXT DEFAULT 'Pending')""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,
        kind TEXT,reason TEXT,created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bans(
        user_id INTEGER PRIMARY KEY, reason TEXT DEFAULT '', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS photo_settings(
        id INTEGER PRIMARY KEY CHECK(id=1),
        photo_file_id TEXT DEFAULT '',
        caption TEXT DEFAULT '',
        button_text TEXT DEFAULT '📢 Channel Open',
        channel_link TEXT DEFAULT ''
    )""")
    c.execute("INSERT OR IGNORE INTO photo_settings(id) VALUES(1)")
    c.commit(); c.close()

def getset(k,d=""):
    c=conn(); r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone(); c.close()
    return r["value"] if r else d

def setset(k,v):
    c=conn(); c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v))); c.commit(); c.close()

def reg(m, ref=None):
    u=m.from_user; c=conn(); old=c.execute("SELECT * FROM users WHERE user_id=?",(u.id,)).fetchone()
    if old: c.execute("UPDATE users SET first_name=?,username=? WHERE user_id=?",(u.first_name or "",u.username or "",u.id))
    else:
        valid=ref if ref and ref!=u.id and c.execute("SELECT 1 FROM users WHERE user_id=?",(ref,)).fetchone() else None
        c.execute("INSERT INTO users(user_id,first_name,username,referred_by,joined_at) VALUES(?,?,?,?,?)",
                  (u.id,u.first_name or "",u.username or "",valid,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        if valid:
            reward=int(getset("referral_reward","10"))
            c.execute("UPDATE users SET referrals=referrals+1,balance=balance+? WHERE user_id=?",(reward,valid))
            c.execute(
                "INSERT INTO transactions(user_id,amount,kind,reason,created_at) VALUES(?,?,?,?,?)",
                (valid,reward,"Credit","Referral Reward",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
    c.commit(); c.close()

def user_kb():
    k=types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row(types.KeyboardButton("👤 Pʀᴏғɪʟᴇ",style="primary"),types.KeyboardButton("💸 Cᴀsʜᴏᴜᴛ",style="success"))
    k.row(types.KeyboardButton("💳 Sᴇᴛ Wᴀʟʟᴇᴛ",style="success"),types.KeyboardButton("🔗 Rᴇғᴇʀ",style="primary"))
    k.row(types.KeyboardButton("📸 Pʜᴏᴛᴏ",style="success"),types.KeyboardButton("📊 Sᴛᴀᴛɪsᴛɪᴄs",style="primary"))
    k.row(types.KeyboardButton("📜 Hɪsᴛᴏʀʏ",style="primary"),types.KeyboardButton("🏆 Tᴏᴘ Rᴇғᴇʀʀᴇʀ",style="success"))
    return k

def admin_kb():
    k=types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row(types.KeyboardButton("📊 Bot Statistics",style="primary"),types.KeyboardButton("📢 Broadcast",style="success"))
    k.row(types.KeyboardButton("📢 Force Join",style="success"),types.KeyboardButton("💸 Cashout Settings",style="primary"))
    k.row(types.KeyboardButton("📸 Photo Settings",style="success"),types.KeyboardButton("💰 Referral Settings",style="primary"))
    k.row(types.KeyboardButton("💳 Cashout Channel",style="success"),types.KeyboardButton("🔎 User Search",style="primary"))
    k.row(types.KeyboardButton("💰 Balance Control",style="success"),types.KeyboardButton("🚫 Ban / Unban",style="danger"))
    k.row(types.KeyboardButton("🔧 Maintenance",style="danger"))
    k.row(types.KeyboardButton("🏠 User Menu",style="danger"))
    return k

def back_kb():
    k=types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row(types.KeyboardButton("🔙 Back",style="danger")); return k

def channels():
    c=conn(); r=c.execute("SELECT * FROM channels WHERE enabled=1 ORDER BY id").fetchall(); c.close(); return r

def joined(uid):
    for x in channels():
        try:
            if bot.get_chat_member(x["chat_id"],uid).status in ("left","kicked"): return False
        except: return False
    return True

def is_banned(uid):
    c=conn(); r=c.execute("SELECT 1 FROM bans WHERE user_id=?",(uid,)).fetchone(); c.close()
    return bool(r)

def add_transaction(uid, amount, kind, reason):
    c=conn()
    c.execute(
        "INSERT INTO transactions(user_id,amount,kind,reason,created_at) VALUES(?,?,?,?,?)",
        (uid, amount, kind, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    c.commit(); c.close()

def access(m):
    if m.from_user.id==ADMIN_ID: return True
    if is_banned(m.from_user.id):
        bot.send_message(m.chat.id,"🚫 <b>আপনি এই Bot থেকে Banned।</b>")
        return False
    if getset("maintenance","0")=="1":
        bot.send_message(m.chat.id,"🔴 <b>Bot Maintenance Mode</b>"); return False
    if channels() and not joined(m.from_user.id): force_join(m.chat.id); return False
    return True

def force_join(cid):
    k=types.InlineKeyboardMarkup(row_width=1)
    for x in channels():
        if x["invite_link"]: k.add(types.InlineKeyboardButton("📢 "+(x["title"] or "Channel"),url=x["invite_link"]))
    k.add(types.InlineKeyboardButton("✅ Verify",callback_data="verify"))
    bot.send_message(cid,"🔐 <b>Channel Join Required</b>\n\nনিচের Channel-গুলোতে Join করে Verify চাপুন।",reply_markup=k)

@bot.message_handler(commands=["start"])
def start(m):
    ref=None
    p=m.text.split(maxsplit=1)
    if len(p)>1 and p[1].isdigit(): ref=int(p[1])
    reg(m,ref)
    if m.from_user.id!=ADMIN_ID and getset("maintenance","0")=="1":
        bot.send_message(m.chat.id,"🔴 <b>Bot Maintenance Mode</b>"); return
    if m.from_user.id!=ADMIN_ID and channels() and not joined(m.from_user.id):
        force_join(m.chat.id); return
    bot.send_message(m.chat.id,f"👋 <b>স্বাগতম, {html.escape(m.from_user.first_name or '')}!</b>\n\n🎁 Referral করে Point আয় করুন।\n💸 Balance থেকে Cashout করুন।\n\n👇 Menu থেকে অপশন নির্বাচন করুন।",reply_markup=user_kb())

@bot.callback_query_handler(func=lambda x:x.data=="verify")
def verify(c):
    if joined(c.from_user.id):
        bot.answer_callback_query(c.id,"✅ Verification সফল!",show_alert=True)
        bot.send_message(c.message.chat.id,"🎉 <b>Verification সফল!</b>",reply_markup=user_kb())
    else: bot.answer_callback_query(c.id,"❌ সব Channel-এ Join করুন!",show_alert=True)

@bot.message_handler(func=lambda m:m.text=="📜 Hɪsᴛᴏʀʏ")
def history(m):
    if not access(m): return
    c=conn()
    rows=c.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 15",
        (m.from_user.id,)
    ).fetchall()
    c.close()
    if not rows:
        text="📜 <b>Hɪsᴛᴏʀʏ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n📭 কোনো transaction নেই।"
    else:
        text="📜 <b>Hɪsᴛᴏʀʏ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for r in rows:
            sign="+" if r["kind"]=="Credit" else "-"
            text += f"▫️ <b>{r['reason']}</b>\n   {sign}{r['amount']} Point • <code>{r['created_at']}</code>\n\n"
    bot.send_message(m.chat.id,text,reply_markup=user_kb())

@bot.message_handler(func=lambda m:m.text=="🏆 Tᴏᴘ Rᴇғᴇʀʀᴇʀ")
def top_referrers(m):
    if not access(m): return
    c=conn()
    rows=c.execute(
        "SELECT first_name,username,referrals FROM users ORDER BY referrals DESC LIMIT 10"
    ).fetchall()
    c.close()
    text="🏆 <b>Tᴏᴘ Rᴇғᴇʀʀᴇʀs</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not rows: text += "📭 এখনো কোনো referral নেই।"
    else:
        medals=["🥇","🥈","🥉"]
        for i,r in enumerate(rows,1):
            icon=medals[i-1] if i<=3 else f"{i}."
            name=("@" + r["username"]) if r["username"] else (r["first_name"] or "User")
            text += f"{icon} <b>{html.escape(name)}</b> — <code>{r['referrals']}</code>\n"
    bot.send_message(m.chat.id,text,reply_markup=user_kb())

@bot.message_handler(func=lambda m:m.text=="👤 Pʀᴏғɪʟᴇ")
def profile(m):
    if not access(m): return
    c=conn(); u=c.execute("SELECT * FROM users WHERE user_id=?",(m.from_user.id,)).fetchone(); c.close()
    bot.send_message(m.chat.id,f"👤 <b>Pʀᴏғɪʟᴇ</b>\n━━━━━━━━━━━━━━━━━━━━\n🆔 ID: <code>{u['user_id']}</code>\n👤 Name: {html.escape(u['first_name'])}\n💰 Balance: <code>{u['balance']} Point</code>\n👥 Referrals: <code>{u['referrals']}</code>\n💳 Wallet: <code>{html.escape(u['wallet']) if u['wallet'] else 'Not Set'}</code>",reply_markup=user_kb())

@bot.message_handler(func=lambda m:m.text=="💳 Sᴇᴛ Wᴀʟʟᴇᴛ")
def wallet(m):
    if not access(m): return
    state[m.from_user.id]="wallet"; bot.send_message(m.chat.id,"💳 <b>Sᴇᴛ Wᴀʟʟᴇᴛ</b>\n\nআপনার Username/Wallet ID পাঠান:",reply_markup=back_kb())

@bot.message_handler(func=lambda m:m.text=="🔗 Rᴇғᴇʀ")
def refer(m):
    if not access(m): return
    c=conn(); u=c.execute("SELECT * FROM users WHERE user_id=?",(m.from_user.id,)).fetchone(); c.close()
    link=f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton("🔗 Refer Link Open",url=link))
    bot.send_message(m.chat.id,f"🔗 <b>Rᴇғᴇʀ Sʏsᴛᴇᴍ</b>\n━━━━━━━━━━━━━━━━━━━━\n👥 Referrals: <code>{u['referrals']}</code>\n💰 Per Referral: <code>{getset('referral_reward','10')} Point</code>\n\n🔗 <code>{html.escape(link)}</code>",reply_markup=k)

@bot.message_handler(func=lambda m:m.text=="📸 Pʜᴏᴛᴏ")
def photo_menu(m):
    if not access(m): return
    c=conn()
    p=c.execute("SELECT * FROM photo_settings WHERE id=1").fetchone()
    c.close()

    if not p or not p["channel_link"]:
        bot.send_message(
            m.chat.id,
            "📸 <b>Pʜᴏᴛᴏ</b>\n\n"
            "⚠️ Photo/Channel Link এখনো Admin সেট করেনি।",
            reply_markup=user_kb()
        )
        return

    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        p["button_text"] or "📢 Channel Open",
        url=p["channel_link"]
    ))
    caption=p["caption"] or "📸 <b>আমাদের Photo</b>\n\nনিচের Button-এ ক্লিক করে Channel-এ যান।"

    try:
        if p["photo_file_id"]:
            bot.send_photo(m.chat.id,p["photo_file_id"],caption=caption,reply_markup=kb)
        else:
            bot.send_message(m.chat.id,caption,reply_markup=kb)
    except Exception as e:
        print("photo send:",e)
        bot.send_message(m.chat.id,caption,reply_markup=kb)

@bot.message_handler(func=lambda m:m.text=="📊 Sᴛᴀᴛɪsᴛɪᴄs")
def stats(m):
    if not access(m): return
    c=conn(); u=c.execute("SELECT * FROM users WHERE user_id=?",(m.from_user.id,)).fetchone(); c.close()
    bot.send_message(m.chat.id,f"📊 <b>Sᴛᴀᴛɪsᴛɪᴄs</b>\n━━━━━━━━━━━━━━━━━━━━\n👥 Referrals: <code>{u['referrals']}</code>\n💰 Balance: <code>{u['balance']} Point</code>\n💸 Total Cashout: <code>{u['total_cashout']} Point</code>",reply_markup=user_kb())

@bot.message_handler(func=lambda m:m.text=="💸 Cᴀsʜᴏᴜᴛ")
def cashout(m):
    if not access(m): return
    c=conn(); u=c.execute("SELECT * FROM users WHERE user_id=?",(m.from_user.id,)).fetchone(); c.close()
    minimum=int(getset("minimum_cashout","100"))
    if not u["wallet"]: bot.send_message(m.chat.id,"💳 আগে <b>Sᴇᴛ Wᴀʟʟᴇᴛ</b> করুন।",reply_markup=user_kb()); return
    if u["balance"]<minimum: bot.send_message(m.chat.id,f"❌ Minimum Cashout <code>{minimum} Point</code>।",reply_markup=user_kb()); return
    state[m.from_user.id]="cashout"
    bot.send_message(m.chat.id,f"💸 <b>Cᴀsʜᴏᴜᴛ</b>\n\n💰 Balance: <code>{u['balance']} Point</code>\n🔻 Minimum: <code>{minimum} Point</code>\n\nকত Point Cashout করবেন লিখুন:",reply_markup=back_kb())

def post_cashout(uid,amount,wallet,username,name):
    ch=getset("cashout_channel","")
    if not ch:return
    link=f"https://t.me/{bot.get_me().username}"
    text=f"💸 <b>NEW CASHOUT REQUEST</b>\n━━━━━━━━━━━━━━━━━━━━\n👤 User: {('@'+html.escape(username)) if username else html.escape(name or 'N/A')}\n🆔 ID: <code>{uid}</code>\n💰 Amount: <code>{amount} Point</code>\n💳 Wallet: <code>{html.escape(wallet)}</code>\n📅 Date: <code>{datetime.now().strftime('%d-%m-%Y %I:%M %p')}</code>\n🟡 Status: Pending\n━━━━━━━━━━━━━━━━━━━━\n🔥 <i>Cashout request received successfully.</i>"
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton("🤖 Open Bot",url=link))
    try: bot.send_message(ch,text,reply_markup=k)
    except Exception as e: print("cashout channel:",e)

@bot.message_handler(content_types=["text"],func=lambda m:m.from_user.id in state)
def states(m):
    uid=m.from_user.id
    if m.text=="🔙 Back":
        state.pop(uid,None); bot.send_message(m.chat.id,"🏠 <b>Main Menu</b>",reply_markup=user_kb()); return
    s=state.get(uid)
    if uid==ADMIN_ID and s=="cash_channel":
        ch=m.text.strip()
        if not ch:
            bot.send_message(m.chat.id,"❌ Channel দিন।"); return
        setset("cashout_channel",ch)
        state.pop(uid,None)
        bot.send_message(m.chat.id,f"✅ Cashout Channel Set: <code>{html.escape(ch)}</code>",reply_markup=admin_kb())
        return
    if uid==ADMIN_ID and s=="search":
        try: target=int(m.text.strip())
        except:
            bot.send_message(m.chat.id,"❌ Valid User ID দিন।"); return
        c=conn(); u=c.execute("SELECT * FROM users WHERE user_id=?",(target,)).fetchone(); c.close()
        state.pop(uid,None)
        if not u:
            bot.send_message(m.chat.id,"❌ User পাওয়া যায়নি।",reply_markup=admin_kb()); return
        bot.send_message(
            m.chat.id,
            f"🔎 <b>User Found</b>\n\n🆔 <code>{u['user_id']}</code>\n👤 {html.escape(u['first_name'])}\n🔗 @{html.escape(u['username']) if u['username'] else 'N/A'}\n💰 <code>{u['balance']} Point</code>\n👥 Referrals: <code>{u['referrals']}</code>\n💳 Wallet: <code>{html.escape(u['wallet']) if u['wallet'] else 'Not Set'}</code>",
            reply_markup=admin_kb()
        )
        return
    if uid==ADMIN_ID and s=="balance":
        p=[x.strip() for x in m.text.split("|")]
        if len(p)!=2:
            bot.send_message(m.chat.id,"❌ Format: <code>UserID | Amount</code>"); return
        try: target=int(p[0]); amount=int(p[1])
        except:
            bot.send_message(m.chat.id,"❌ সঠিক সংখ্যা দিন।"); return
        c=conn(); u=c.execute("SELECT balance FROM users WHERE user_id=?",(target,)).fetchone()
        if not u:
            c.close(); bot.send_message(m.chat.id,"❌ User পাওয়া যায়নি।"); return
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(amount,target))
        c.commit(); c.close()
        add_transaction(target,abs(amount),"Credit" if amount>=0 else "Debit","Admin Balance Control")
        state.pop(uid,None)
        bot.send_message(m.chat.id,f"✅ Balance Updated: <code>{amount:+d} Point</code>",reply_markup=admin_kb())
        return
    if uid==ADMIN_ID and s=="ban":
        p=[x.strip() for x in m.text.split("|")]
        if len(p)!=2 or p[0].lower() not in ("ban","unban"):
            bot.send_message(m.chat.id,"❌ Format: <code>ban | UserID</code>"); return
        try: target=int(p[1])
        except:
            bot.send_message(m.chat.id,"❌ Valid User ID দিন।"); return
        c=conn()
        if p[0].lower()=="ban":
            c.execute("INSERT OR REPLACE INTO bans(user_id,reason,created_at) VALUES(?,?,?)",(target,"Admin",datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        else:
            c.execute("DELETE FROM bans WHERE user_id=?",(target,))
        c.commit(); c.close(); state.pop(uid,None)
        bot.send_message(m.chat.id,f"✅ User {p[0].upper()} করা হয়েছে।",reply_markup=admin_kb())
        return

    if uid==ADMIN_ID and s=="min":
        try:v=int(m.text); assert v>0
        except:bot.send_message(m.chat.id,"❌ Valid Point দিন।");return
        setset("minimum_cashout",v); state.pop(uid); bot.send_message(m.chat.id,f"✅ Minimum Cashout: <code>{v} Point</code>",reply_markup=admin_kb()); return
    if uid==ADMIN_ID and s=="reward":
        try:v=int(m.text); assert v>=0
        except:bot.send_message(m.chat.id,"❌ Valid Point দিন।");return
        setset("referral_reward",v); state.pop(uid); bot.send_message(m.chat.id,f"✅ Referral Reward: <code>{v} Point</code>",reply_markup=admin_kb()); return
    if uid==ADMIN_ID and s=="channel":
        p=[x.strip() for x in m.text.split("|")]
        if len(p)!=3: bot.send_message(m.chat.id,"❌ Format: <code>chat_id | name | invite_link</code>"); return
        try:bot.get_chat(p[0])
        except:bot.send_message(m.chat.id,"❌ Bot-কে Channel Admin করুন এবং সঠিক ID দিন।");return
        c=conn();c.execute("INSERT OR REPLACE INTO channels(chat_id,title,invite_link,enabled) VALUES(?,?,?,1)",p);c.commit();c.close();state.pop(uid)
        bot.send_message(m.chat.id,"✅ <b>Channel Added!</b>",reply_markup=admin_kb());return
    if uid==ADMIN_ID and s=="broadcast":
        c=conn(); us=c.execute("SELECT user_id FROM users").fetchall();c.close();ok=bad=0
        for x in us:
            try:bot.send_message(x["user_id"],m.text);ok+=1
            except:bad+=1
        state.pop(uid);bot.send_message(m.chat.id,f"📢 <b>Broadcast Complete</b>\n\n✅ Sent: <code>{ok}</code>\n❌ Failed: <code>{bad}</code>",reply_markup=admin_kb());return
    if s=="wallet":
        w=m.text.strip()
        if not 2<=len(w)<=100:bot.send_message(m.chat.id,"❌ সঠিক Wallet দিন।");return
        c=conn();c.execute("UPDATE users SET wallet=? WHERE user_id=?",(w,uid));c.commit();c.close();state.pop(uid)
        bot.send_message(m.chat.id,f"✅ <b>Wallet Set!</b>\n\n💳 <code>{html.escape(w)}</code>",reply_markup=user_kb());return
    if s=="cashout":
        try:a=int(m.text);assert a>0
        except:bot.send_message(m.chat.id,"❌ শুধু Point-এর সংখ্যা লিখুন।");return
        minimum=int(getset("minimum_cashout","100"));c=conn();u=c.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
        if a<minimum or a>u["balance"]:
            c.close();bot.send_message(m.chat.id,f"❌ Amount সঠিক নয়। Minimum <code>{minimum}</code>, Balance <code>{u['balance']}</code>।");return
        c.execute("UPDATE users SET balance=balance-?,total_cashout=total_cashout+? WHERE user_id=?",(a,a,uid))
        c.execute("INSERT INTO cashouts(user_id,amount,wallet,created_at) VALUES(?,?,?,?)",(uid,a,u["wallet"],datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        c.execute(
            "INSERT INTO transactions(user_id,amount,kind,reason,created_at) VALUES(?,?,?,?,?)",
            (uid,a,"Debit","Cashout Request",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        c.commit();c.close();state.pop(uid)
        post_cashout(uid,a,u["wallet"],u["username"],u["first_name"])
        bot.send_message(m.chat.id,f"✅ <b>Cashout Request Sent!</b>\n\n💰 <code>{a} Point</code>\n💳 <code>{html.escape(u['wallet'])}</code>",reply_markup=user_kb())

# ---------------- ADMIN ----------------

def admin_only(m):
    if m.from_user.id!=ADMIN_ID:bot.send_message(m.chat.id,"❌ Admin Access নেই।");return False
    return True

@bot.message_handler(commands=["admin"])
def admin(m):
    if admin_only(m):bot.send_message(m.chat.id,"👑 <b>Aᴅᴍɪɴ Pᴀɴᴇʟ</b>\n━━━━━━━━━━━━━━━━━━━━\nসব Settings এখান থেকে Control করুন।",reply_markup=admin_kb())

@bot.message_handler(func=lambda m:m.text=="📊 Bot Statistics")
def astats(m):
    if not admin_only(m):return
    c=conn();u=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"];r=c.execute("SELECT COALESCE(SUM(referrals),0) n FROM users").fetchone()["n"];q=c.execute("SELECT COUNT(*) n FROM cashouts").fetchone()["n"];c.close()
    bot.send_message(m.chat.id,f"📊 <b>BOT STATISTICS</b>\n\n👥 Users: <code>{u}</code>\n👥 Referrals: <code>{r}</code>\n💸 Cashouts: <code>{q}</code>",reply_markup=admin_kb())

@bot.message_handler(func=lambda m:m.text=="📸 Photo Settings")
def photo_settings(m):
    if not admin_only(m): return
    state[ADMIN_ID]="photo"
    bot.send_message(
        m.chat.id,
        "📸 <b>Photo Settings</b>\n\n"
        "একটি Photo পাঠান। Photo-এর Caption-এ নিচের Format ব্যবহার করুন:\n"
        "<code>Button Text | Channel Link</code>\n\n"
        "উদাহরণ:\n"
        "<code>📢 Join Channel | https://t.me/example</code>\n\n"
        "Photo পাঠালে সেটি User-এর 📸 Photo Button-এ দেখাবে।",
        reply_markup=back_kb()
    )

@bot.message_handler(content_types=["photo"], func=lambda m:m.from_user.id==ADMIN_ID and state.get(ADMIN_ID)=="photo")
def save_photo_settings(m):
    caption=m.caption or ""
    parts=[x.strip() for x in caption.split("|",1)]
    button_text=parts[0] if parts and parts[0] else "📢 Channel Open"
    channel_link=parts[1] if len(parts)>1 else ""

    if not channel_link.startswith(("https://t.me/","https://telegram.me/","http://t.me/")):
        bot.send_message(
            m.chat.id,
            "❌ Caption-এ সঠিক Channel Link দিন।\n\n"
            "<code>Button Text | https://t.me/yourchannel</code>"
        )
        return

    file_id=m.photo[-1].file_id
    c=conn()
    c.execute(
        "UPDATE photo_settings SET photo_file_id=?,caption=?,button_text=?,channel_link=? WHERE id=1",
        (file_id,"📸 <b>Pʜᴏᴛᴏ</b>\n\nনিচের Button-এ ক্লিক করে Channel-এ যান।",button_text,channel_link)
    )
    c.commit(); c.close()
    state.pop(ADMIN_ID,None)

    bot.send_message(
        m.chat.id,
        "✅ <b>Photo System Updated!</b>\n\n"
        f"🔘 Button: <code>{html.escape(button_text)}</code>\n"
        f"🔗 Link: <code>{html.escape(channel_link)}</code>",
        reply_markup=admin_kb()
    )

@bot.message_handler(func=lambda m:m.text=="💳 Cashout Channel")
def cashout_channel_admin(m):
    if not admin_only(m): return
    state[ADMIN_ID]="cash_channel"
    current=getset("cashout_channel","Not Set")
    bot.send_message(
        m.chat.id,
        f"💳 <b>Cᴀsʜᴏᴜᴛ Cʜᴀɴɴᴇʟ</b>\n\nবর্তমান: <code>{html.escape(current)}</code>\n\n"
        "Channel @username অথবা numeric Chat ID পাঠান।",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m:m.text=="🔎 User Search")
def user_search_admin(m):
    if not admin_only(m): return
    state[ADMIN_ID]="search"
    bot.send_message(m.chat.id,"🔎 <b>Uѕᴇʀ Sᴇᴀʀᴄʜ</b>\n\nUser ID পাঠান:",reply_markup=back_kb())

@bot.message_handler(func=lambda m:m.text=="💰 Balance Control")
def balance_control_admin(m):
    if not admin_only(m): return
    state[ADMIN_ID]="balance"
    bot.send_message(
        m.chat.id,
        "💰 <b>Bᴀʟᴀɴᴄᴇ Cᴏɴᴛʀᴏʟ</b>\n\n"
        "Format:\n<code>UserID | Amount</code>\n\n"
        "Amount positive হলে Add, negative হলে Remove।",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m:m.text=="🚫 Ban / Unban")
def ban_admin(m):
    if not admin_only(m): return
    state[ADMIN_ID]="ban"
    bot.send_message(
        m.chat.id,
        "🚫 <b>Bᴀɴ / Uɴʙᴀɴ</b>\n\n"
        "Format:\n<code>ban | UserID</code>\nঅথবা\n<code>unban | UserID</code>",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m:m.text=="💸 Cashout Settings")
def aset(m):
    if admin_only(m):state[ADMIN_ID]="min";bot.send_message(m.chat.id,f"💸 Current Minimum: <code>{getset('minimum_cashout','100')}</code>\n\nনতুন Minimum Point দিন:",reply_markup=back_kb())

@bot.message_handler(func=lambda m:m.text=="💰 Referral Settings")
def rset(m):
    if admin_only(m):state[ADMIN_ID]="reward";bot.send_message(m.chat.id,f"💰 Current Reward: <code>{getset('referral_reward','10')}</code>\n\nনতুন Referral Reward দিন:",reply_markup=back_kb())

@bot.message_handler(func=lambda m:m.text=="📢 Force Join")
def fj(m):
    if not admin_only(m):return
    k=types.InlineKeyboardMarkup();k.row(types.InlineKeyboardButton("➕ Add",callback_data="addch"),types.InlineKeyboardButton("📋 List",callback_data="listch"));k.add(types.InlineKeyboardButton("🗑 Remove All",callback_data="delch"))
    bot.send_message(m.chat.id,"📢 <b>Force Join Manager</b>\n\nBot-কে Channel Admin করে Add করুন।",reply_markup=k)

@bot.callback_query_handler(func=lambda c:c.data in ("addch","listch","delch"))
def fjcb(c):
    if c.from_user.id!=ADMIN_ID:return
    if c.data=="addch":
        state[ADMIN_ID]="channel";bot.send_message(c.message.chat.id,"📢 Format:\n<code>chat_id | channel_name | invite_link</code>",reply_markup=back_kb())
    elif c.data=="listch":
        r=channels();bot.send_message(c.message.chat.id,"📋 <b>Channels</b>\n\n"+("\n".join(f"{i}. {html.escape(x['title'])}" for i,x in enumerate(r,1)) if r else "📭 None"))
    else:
        c2=conn();c2.execute("DELETE FROM channels");c2.commit();c2.close();bot.answer_callback_query(c.id,"✅ Removed",show_alert=True)

@bot.message_handler(func=lambda m:m.text=="📢 Broadcast")
def broad(m):
    if admin_only(m):state[ADMIN_ID]="broadcast";bot.send_message(m.chat.id,"📢 Message পাঠান:",reply_markup=back_kb())

@bot.message_handler(func=lambda m:m.text=="🔧 Maintenance")
def maint(m):
    if not admin_only(m):return
    k=types.InlineKeyboardMarkup();k.row(types.InlineKeyboardButton("🟢 ON",callback_data="mt1"),types.InlineKeyboardButton("🔴 OFF",callback_data="mt0"))
    bot.send_message(m.chat.id,f"🔧 Current: <code>{'ON' if getset('maintenance','0')=='1' else 'OFF'}</code>",reply_markup=k)

@bot.callback_query_handler(func=lambda c:c.data in ("mt1","mt0"))
def mt(c):
    if c.from_user.id==ADMIN_ID:setset("maintenance","1" if c.data=="mt1" else "0");bot.answer_callback_query(c.id,"✅ Updated")

@bot.message_handler(func=lambda m:m.text=="🏠 User Menu")
def um(m):
    if admin_only(m):state.pop(ADMIN_ID,None);bot.send_message(m.chat.id,"🏠 <b>User Menu</b>",reply_markup=user_kb())

@bot.message_handler(func=lambda m:True)
def fallback(m):
    if m.from_user.id==ADMIN_ID and not state.get(ADMIN_ID):bot.send_message(m.chat.id,"👑 <b>Admin Panel</b>",reply_markup=admin_kb())
    elif m.from_user.id!=ADMIN_ID:bot.send_message(m.chat.id,"❓ Menu থেকে একটি অপশন নির্বাচন করুন।",reply_markup=user_kb())

if __name__=="__main__":
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN environment variable সেট করুন।")
    init_db(); print("Bot started"); bot.infinity_polling(skip_pending=True)
