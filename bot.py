import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup,
                           KeyboardButton, InlineKeyboardMarkup,
                           InlineKeyboardButton)

# ====== SOZLAMALAR ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BANK = os.getenv("BANK", "Toss Bank")
ACCOUNT = os.getenv("CARD", "1002-5049-4242")
OWNER = os.getenv("OWNER", "")  # hisob egasining ismi (ixtiyoriy)
DB_PATH = os.getenv("DB_PATH", "shop.db")

# UC: (narx won, bonus UC)  -- narxlarni o'zingiz o'zgartiring
PACKS = {60: (1500, 0), 325: (7500, 10), 660: (15000, 30),
         1800: (37500, 100), 3850: (75000, 300)}
CASHBACK = 2      # har tasdiqlangan xariddan % ball qaytadi
REF_BONUS = 500   # do'st birinchi xarid qilsa, taklif qilganga (won)
MAX_POINTS = 50   # ball bilan narxning maksimal necha % ini to'lash mumkin
# ========================

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN o'rnatilmagan!")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, ref_by INTEGER, points INTEGER DEFAULT 0,
  last_pid TEXT);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, uc INTEGER,
  bonus INTEGER, pid TEXT, pay INTEGER, used INTEGER,
  status TEXT DEFAULT 'pending', created TEXT DEFAULT CURRENT_TIMESTAMP);
""")


def q(sql, *a):
    cur = db.execute(sql, a)
    db.commit()
    return cur


def won(n):
    return f"₩{n:,}"


def label(uc):
    b = PACKS[uc][1]
    return f"{uc}+{b} UC" if b else f"{uc} UC"


def points(uid):
    r = q("SELECT points FROM users WHERE id=?", uid).fetchone()
    return r["points"] if r else 0


MENU = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text="🛒 UC sotib olish")],
    [KeyboardButton(text="🎁 Bonuslarim"), KeyboardButton(text="📦 Buyurtmalarim")]])


class S(StatesGroup):
    pid = State()
    receipt = State()


async def catalog(m: Message):
    kb = [[InlineKeyboardButton(text=f"{label(uc)} — {won(p)}",
                                callback_data=f"buy:{uc}")]
          for uc, (p, b) in PACKS.items()]
    await m.answer("Paketni tanlang 👇",
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@dp.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    uid = m.from_user.id
    if not q("SELECT 1 FROM users WHERE id=?", uid).fetchone():
        ref = None
        a = command.args or ""
        if a.startswith("ref") and a[3:].isdigit() and int(a[3:]) != uid:
            if q("SELECT 1 FROM users WHERE id=?", int(a[3:])).fetchone():
                ref = int(a[3:])
        q("INSERT INTO users(id, ref_by) VALUES(?,?)", uid, ref)
    await m.answer("🎮 PUBG Mobile UC do'koni\nTez, qulay va bonuslar bilan!",
                   reply_markup=MENU)
    await catalog(m)


@dp.message(F.text == "🛒 UC sotib olish")
async def menu_buy(m: Message, state: FSMContext):
    await state.clear()
    await catalog(m)


@dp.message(F.text == "🎁 Bonuslarim")
async def menu_bonus(m: Message, state: FSMContext):
    await state.clear()
    me = await bot.get_me()
    await m.answer(
        f"🎁 Ballaringiz: {won(points(m.from_user.id))}\n\n"
        f"• Har xariddan {CASHBACK}% ball qaytadi\n"
        f"• Do'stingiz birinchi xarid qilsa, sizga {won(REF_BONUS)}\n"
        f"• Ball bilan keyingi xaridning {MAX_POINTS}% igacha to'lash mumkin\n"
        f"• Katta paketlarda qo'shimcha bonus UC\n\n"
        f"Sizning havolangiz:\nhttps://t.me/{me.username}?start=ref{m.from_user.id}")


@dp.message(F.text == "📦 Buyurtmalarim")
async def menu_orders(m: Message, state: FSMContext):
    await state.clear()
    rows = q("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5",
             m.from_user.id).fetchall()
    if not rows:
        return await m.answer("Hali buyurtma yo'q.")
    st = {"pending": "⏳ Kutilmoqda", "done": "✅ Yetkazildi",
          "rejected": "❌ Rad etildi"}
    await m.answer("\n".join(
        f"#{r['id']} — {r['uc']}+{r['bonus']} UC — {won(r['pay'])} — "
        f"{st[r['status']]}" for r in rows))


@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery, state: FSMContext):
    uc = int(c.data[4:])
    await state.update_data(uc=uc)
    await state.set_state(S.pid)
    r = q("SELECT last_pid FROM users WHERE id=?", c.from_user.id).fetchone()
    kb = None
    if r and r["last_pid"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=f"Saqlangan ID: {r['last_pid']}", callback_data="useid")]])
    await c.message.answer(f"{label(uc)} tanlandi.\nPUBG ID raqamingizni yuboring:",
                           reply_markup=kb)
    await c.answer()


async def after_id(msg: Message, state: FSMContext, uid: int, pid: str):
    await state.update_data(pid=pid)
    q("UPDATE users SET last_pid=? WHERE id=?", pid, uid)
    if points(uid) > 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Ha, ishlataman", callback_data="pts:1"),
            InlineKeyboardButton(text="Yo'q", callback_data="pts:0")]])
        await msg.answer(f"Sizda {won(points(uid))} ball bor. Ishlatasizmi?",
                         reply_markup=kb)
    else:
        await send_pay(msg, state, uid, False)


async def send_pay(msg: Message, state: FSMContext, uid: int, use: bool):
    d = await state.get_data()
    price = PACKS[d["uc"]][0]
    used = min(points(uid), price * MAX_POINTS // 100) if use else 0
    pay = price - used
    await state.update_data(pay=pay, used=used)
    await state.set_state(S.receipt)
    await msg.answer(
        f"🧾 {label(d['uc'])}\nPUBG ID: {d['pid']}\n"
        f"Narx: {won(price)}" + (f"\nBall: -{won(used)}" if used else "") +
        f"\n\n💳 To'lov: {won(pay)}\n{BANK}: {ACCOUNT}" +
        (f"\nEgasi: {OWNER}" if OWNER else "") +
        "\n\nTo'lagach, chek (skrinshot) rasmini shu yerga yuboring 📸")


@dp.callback_query(F.data == "useid")
async def use_id(c: CallbackQuery, state: FSMContext):
    r = q("SELECT last_pid FROM users WHERE id=?", c.from_user.id).fetchone()
    await c.answer()
    await after_id(c.message, state, c.from_user.id, r["last_pid"])


@dp.message(S.pid)
async def get_id(m: Message, state: FSMContext):
    pid = (m.text or "").strip()
    if not pid.isdigit() or not 8 <= len(pid) <= 12:
        return await m.answer("ID noto'g'ri. Faqat raqam yuboring (8-12 ta).")
    await after_id(m, state, m.from_user.id, pid)


@dp.callback_query(F.data.startswith("pts:"))
async def use_pts(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if (await state.get_data()).get("uc") is None:
        return await c.message.answer("Qaytadan /start bosing.")
    await send_pay(c.message, state, c.from_user.id, c.data == "pts:1")


@dp.message(S.receipt, F.photo)
async def get_receipt(m: Message, state: FSMContext):
    d = await state.get_data()
    uid = m.from_user.id
    bonus = PACKS[d["uc"]][1]
    if d["used"]:
        q("UPDATE users SET points=points-? WHERE id=?", d["used"], uid)
    oid = q("INSERT INTO orders(user_id,uc,bonus,pid,pay,used) VALUES(?,?,?,?,?,?)",
            uid, d["uc"], bonus, d["pid"], d["pay"], d["used"]).lastrowid
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ok:{oid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"no:{oid}")]])
    await bot.send_photo(
        ADMIN_ID, m.photo[-1].file_id, reply_markup=kb,
        caption=f"Buyurtma #{oid}\n{d['uc']}+{bonus} UC\nPUBG ID: {d['pid']}\n"
                f"To'lov: {won(d['pay'])}\n"
                f"Mijoz: @{m.from_user.username} ({uid})")
    await m.answer(f"Buyurtma #{oid} qabul qilindi. Admin tekshirmoqda ⏳")
    await state.clear()


@dp.message(S.receipt)
async def need_photo(m: Message):
    await m.answer("Iltimos, to'lov chekining rasmini yuboring.")


@dp.callback_query(F.data.regexp(r"^(ok|no):"))
async def decide(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("Ruxsat yo'q", show_alert=True)
    act, oid = c.data.split(":")
    o = q("SELECT * FROM orders WHERE id=?", oid).fetchone()
    if not o or o["status"] != "pending":
        return await c.answer("Allaqachon ko'rilgan")
    uid = o["user_id"]
    if act == "ok":
        q("UPDATE orders SET status='done' WHERE id=?", oid)
        cb = o["pay"] * CASHBACK // 100
        q("UPDATE users SET points=points+? WHERE id=?", cb, uid)
        await bot.send_message(
            uid, f"✅ Buyurtma #{oid}: {o['uc'] + o['bonus']} UC "
                 f"ID {o['pid']} ga yuborildi!\n🎁 +{won(cb)} ball qaytdi.")
        n = q("SELECT COUNT(*) c FROM orders WHERE user_id=? AND status='done'",
              uid).fetchone()["c"]
        ref = q("SELECT ref_by FROM users WHERE id=?", uid).fetchone()["ref_by"]
        if n == 1 and ref:
            q("UPDATE users SET points=points+? WHERE id=?", REF_BONUS, ref)
            await bot.send_message(ref, f"🎉 Do'stingiz xarid qildi! +{won(REF_BONUS)} ball.")
        status = "TASDIQLANDI ✅"
    else:
        q("UPDATE orders SET status='rejected' WHERE id=?", oid)
        q("UPDATE users SET points=points+? WHERE id=?", o["used"], uid)
        await bot.send_message(uid, f"❌ Buyurtma #{oid} rad etildi. "
                                    f"Ishlatilgan ballar qaytarildi. Admin bilan bog'laning.")
        status = "RAD ETILDI ❌"
    await c.message.edit_caption(caption=f"{c.message.caption}\n\n{status}")
    await c.answer()


@dp.message(Command("stats"))
async def stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    r = q("SELECT COUNT(*) c, COALESCE(SUM(pay),0) s FROM orders WHERE status='done'").fetchone()
    p = q("SELECT COUNT(*) c FROM orders WHERE status='pending'").fetchone()["c"]
    u = q("SELECT COUNT(*) c FROM users").fetchone()["c"]
    await m.answer(f"👥 Foydalanuvchilar: {u}\n✅ Sotuvlar: {r['c']}\n"
                   f"💰 Tushum: {won(r['s'])}\n⏳ Kutilayotgan: {p}")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
