import asyncio
import csv
import io
import logging
import os
from datetime import datetime
from html import escape
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "school_crm.db")
SCHOOL_NAME = os.getenv("SCHOOL_NAME", "Buxoro Qorako‘l xususiy maktabi")
SCHOOL_PHONE = os.getenv("SCHOOL_PHONE", "Administrator orqali aniqlashtiriladi")
SCHOOL_ADDRESS = os.getenv("SCHOOL_ADDRESS", "Administrator orqali aniqlashtiriladi")
GRADES_RAW = os.getenv("GRADES", "1,2,3,4,5,6,7,8,9,10,11")
GRADES = [x.strip() for x in GRADES_RAW.split(",") if x.strip()]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan.")
if not ADMIN_ID_RAW.isdigit():
    raise RuntimeError("ADMIN_ID .env faylida raqam ko'rinishida bo'lishi kerak.")
ADMIN_ID = int(ADMIN_ID_RAW)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("school_crm")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

STATUSES = {
    "new": "Yangi",
    "contacted": "Bog‘lanildi",
    "visit": "Maktabga tashrif belgilandi",
    "documents": "Hujjat topshirdi",
    "admitted": "Qabul qilindi",
    "rejected": "Qabul qilinmadi",
    "followup": "Qayta bog‘lanish kerak",
}

REQUEST_TYPES = {
    "admission": "Farzandini maktabga joylashtirish",
    "about": "Maktab haqida ma'lumot",
    "visit": "Maktabga tashrif",
}

class LeadForm(StatesGroup):
    parent_name = State()
    phone = State()
    child_name = State()
    child_age = State()
    grade = State()
    current_school = State()
    request_type = State()

class AdminNote(StatesGroup):
    waiting_for_note = State()

class AdminSearch(StatesGroup):
    waiting_for_query = State()

def parent_menu():
    return ReplyKeyboardMarkup(
     keyboard=[
    [KeyboardButton(text="🎓 Maktabga qabul")],
    [KeyboardButton(text="📅 Maktabga tashrif")],
    [KeyboardButton(text="📍 Manzil va aloqa")],
],
        resize_keyboard=True,
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Yangi murojaatlar"), KeyboardButton(text="📋 Barcha murojaatlar")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🔎 Mijoz qidirish")],
            [KeyboardButton(text="📤 Excel/CSV eksport"), KeyboardButton(text="ℹ️ Admin yordam")],
        ],
        resize_keyboard=True,
    )

def consent_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Roziman, davom etish", callback_data="consent:yes")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="consent:no")],
    ])

def grade_keyboard():
    rows = []
    for i in range(0, len(GRADES), 3):
        rows.append([
            InlineKeyboardButton(text=f"{g}-sinf", callback_data=f"grade:{g}")
            for g in GRADES[i:i+3]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def request_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"request:{key}")]
        for key, label in REQUEST_TYPES.items()
    ])

def lead_actions_keyboard(lead_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📞 Bog‘lanildi", callback_data=f"status:{lead_id}:contacted"),
            InlineKeyboardButton(text="📅 Tashrif", callback_data=f"status:{lead_id}:visit"),
        ],
        [
            InlineKeyboardButton(text="📄 Hujjat topshirdi", callback_data=f"status:{lead_id}:documents"),
            InlineKeyboardButton(text="✅ Qabul qilindi", callback_data=f"status:{lead_id}:admitted"),
        ],
        [
            InlineKeyboardButton(text="🔁 Qayta bog‘lanish", callback_data=f"status:{lead_id}:followup"),
            InlineKeyboardButton(text="❌ Qabul qilinmadi", callback_data=f"status:{lead_id}:rejected"),
        ],
        [InlineKeyboardButton(text="📝 Izoh qo‘shish", callback_data=f"note:{lead_id}")],
    ])

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def esc(value) -> str:
    return escape(str(value if value is not None else "—"))

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                parent_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                child_name TEXT NOT NULL,
                child_age INTEGER NOT NULL,
                grade TEXT NOT NULL,
                current_school TEXT,
                request_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                admin_note TEXT DEFAULT '',
                consent_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_telegram ON leads(telegram_id)")
        await db.commit()

async def create_lead(data: dict, user_id: int, username: Optional[str]) -> int:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO leads (
                telegram_id, username, parent_name, phone, child_name, child_age,
                grade, current_school, request_type, status, admin_note,
                consent_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '', ?, ?, ?)
        """, (
            user_id, username, data["parent_name"], data["phone"],
            data["child_name"], data["child_age"], data["grade"],
            data["current_school"], data["request_type"], now, now, now
        ))
        await db.commit()
        return cur.lastrowid

async def fetch_lead(lead_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def update_status(lead_id: int, status: str):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, lead_id),
        )
        await db.commit()
        return cur.rowcount > 0

async def add_admin_note(lead_id: int, note: str):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE leads SET admin_note = ?, updated_at = ? WHERE id = ?",
            (note, now, lead_id),
        )
        await db.commit()
        return cur.rowcount > 0

async def list_leads(status: Optional[str] = None, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            cur = await db.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
            )
        return [dict(row) for row in await cur.fetchall()]

async def search_leads(query: str, limit: int = 10):
    pattern = f"%{query}%"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM leads
            WHERE parent_name LIKE ? OR child_name LIKE ? OR phone LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (pattern, pattern, pattern, limit))
        return [dict(row) for row in await cur.fetchall()]

async def get_statistics():
    async with aiosqlite.connect(DB_PATH) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM leads")).fetchone())[0]
        today = datetime.now().astimezone().date().isoformat()
        today_count = (await (await db.execute(
            "SELECT COUNT(*) FROM leads WHERE substr(created_at, 1, 10) = ?", (today,)
        )).fetchone())[0]
        rows = await (await db.execute(
            "SELECT status, COUNT(*) AS n FROM leads GROUP BY status"
        )).fetchall()
        grade_rows = await (await db.execute(
            "SELECT grade, COUNT(*) AS n FROM leads GROUP BY grade ORDER BY grade"
        )).fetchall()
    return total, today_count, dict(rows), grade_rows

async def export_csv() -> bytes:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, created_at, parent_name, phone, child_name, child_age,
                   grade, current_school, request_type, status, admin_note,
                   telegram_id, username
            FROM leads ORDER BY id DESC
        """)
        rows = await cur.fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "ID", "Created at", "Parent", "Phone", "Child", "Age", "Grade",
        "Current school", "Request", "Status", "Admin note", "Telegram ID", "Username"
    ])
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")

async def delete_user_data(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM leads WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
        return cur.rowcount

def lead_card(lead: dict) -> str:
    status_label = STATUSES.get(lead["status"], lead["status"])
    return (
        f"🗂 <b>Murojaat №{lead['id']}</b>\n"
        f"📌 <b>Status:</b> {esc(status_label)}\n"
        f"👤 <b>Ota-ona:</b> {esc(lead['parent_name'])}\n"
        f"📞 <b>Telefon:</b> {esc(lead['phone'])}\n"
        f"👦 <b>Farzandi:</b> {esc(lead['child_name'])}\n"
        f"🎂 <b>Yoshi:</b> {lead['child_age']}\n"
        f"🎓 <b>Sinf:</b> {esc(lead['grade'])}\n"
        f"🏫 <b>Hozirgi maktabi:</b> {esc(lead['current_school'])}\n"
        f"📍 <b>Murojaat:</b> {esc(lead['request_type'])}\n"
        f"🗒 <b>Izoh:</b> {esc(lead['admin_note'] or 'Yo‘q')}\n"
        f"📅 <b>Sana:</b> {esc(lead['created_at'])}"
    )

async def begin_parent_flow(message: Message, state: FSMContext, request_hint: Optional[str] = None):
    await state.clear()
    if request_hint:
        await state.update_data(request_hint=request_hint)
    await message.answer(
        f"👋 <b>Assalomu alaykum!</b>\n\n"
        f"<b>{esc(SCHOOL_NAME)}</b> rasmiy qabul botiga xush kelibsiz!\n\n"
        "Siz maktabga qabul, ta'lim, to'lovlar yoki boshqa savollar bo‘yicha "
        "murojaat qoldirishingiz mumkin.\n\n"
        "Davom etish uchun ma'lumotlaringizni murojaatni ko‘rib chiqish va "
        "siz bilan bog‘lanish maqsadida qayta ishlashga rozilik bering.\n\n"
        "Ma'lumotlaringiz maktabning vakolatli administratori tomonidan ko‘riladi.",
        reply_markup=consent_keyboard(),
    )

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await begin_parent_flow(message, state)

@dp.callback_query(F.data == "consent:yes")
async def consent_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(LeadForm.parent_name)
    await callback.message.answer(
        "Iltimos, ism va familiyangizni kiriting.\nMasalan: Aliyev Anvar",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.callback_query(F.data == "consent:no")
async def consent_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.answer("Rozilik berilmadi. Ma'lumotlaringiz saqlanmadi.", reply_markup=parent_menu())

@dp.message(LeadForm.parent_name)
async def parent_name(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if len(value.split()) < 2 or len(value) > 100:
        await message.answer("Ism va familiyangizni to‘liq kiriting. Masalan: Aliyev Anvar")
        return
    await state.update_data(parent_name=value)
    await state.set_state(LeadForm.phone)
    await message.answer(
        "📞 Telefon raqamingizni yuboring. Pastdagi tugma orqali kontaktingizni ulashing.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Kontaktni ulashish", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

@dp.message(LeadForm.phone, F.contact)
async def phone_received(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("Iltimos, o‘zingizning telefon raqamingizni ulashing.")
        return
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(LeadForm.child_name)
    await message.answer("👦 Farzandingizning ism-familiyasini kiriting.", reply_markup=ReplyKeyboardRemove())

@dp.message(LeadForm.phone)
async def phone_invalid(message: Message):
    await message.answer("Telefon raqamingizni 📱 Kontaktni ulashish tugmasi orqali yuboring.")

@dp.message(LeadForm.child_name)
async def child_name(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if len(value) < 3 or len(value) > 100:
        await message.answer("Farzandingizning ism-familiyasini to‘liq kiriting.")
        return
    await state.update_data(child_name=value)
    await state.set_state(LeadForm.child_age)
    await message.answer("Farzandingiz necha yoshda? Yoshini raqam bilan kiriting.")

@dp.message(LeadForm.child_age)
async def child_age(message: Message, state: FSMContext):
    try:
        age = int((message.text or "").strip())
    except ValueError:
        await message.answer("Yoshni raqam bilan kiriting. Masalan: 8")
        return
    if not 3 <= age <= 18:
        await message.answer("Yosh 3 dan 18 gacha bo‘lishi kerak.")
        return
    await state.update_data(child_age=age)
    await state.set_state(LeadForm.grade)
    await message.answer("Farzandingiz qaysi sinfga qabul qilinmoqchi?", reply_markup=grade_keyboard())

@dp.callback_query(LeadForm.grade, F.data.startswith("grade:"))
async def grade_received(callback: CallbackQuery, state: FSMContext):
    grade = callback.data.split(":", 1)[1]
    if grade not in GRADES:
        await callback.answer("Sinf tanlanmadi.")
        return
    await state.update_data(grade=f"{grade}-sinf")
    await state.set_state(LeadForm.current_school)
    await callback.answer()
    await callback.message.answer(
        "Farzandingiz hozir qaysi maktabda o‘qiydi?\n"
        "Maktab nomini yozing yoki bilmasangiz /skip yuboring.",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.message(LeadForm.current_school, Command("skip"))
async def skip_current_school(message: Message, state: FSMContext):
    await state.update_data(current_school="Ko‘rsatilmagan")
    await state.set_state(LeadForm.request_type)
    await message.answer("Sizni qaysi masala qiziqtiradi?", reply_markup=request_keyboard())

@dp.message(LeadForm.current_school)
async def current_school(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value or len(value) > 200:
        await message.answer("Maktab nomini kiriting yoki /skip yuboring.")
        return
    await state.update_data(current_school=value)
    await state.set_state(LeadForm.request_type)
    await message.answer("Sizni qaysi masala qiziqtiradi?", reply_markup=request_keyboard())

@dp.callback_query(LeadForm.request_type, F.data.startswith("request:"))
async def request_received(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    if key not in REQUEST_TYPES:
        await callback.answer("Noto‘g‘ri tanlov.")
        return
    data = await state.get_data()
    request_type = data.get("request_hint") or REQUEST_TYPES[key]
    data["request_type"] = request_type

    try:
        lead_id = await create_lead(data, callback.from_user.id, callback.from_user.username)
    except Exception:
        logger.exception("Murojaat bazaga saqlanmadi")
        await callback.answer("Texnik xatolik", show_alert=True)
        await callback.message.answer("Murojaatni saqlashda xatolik yuz berdi. Iltimos, /start orqali qayta urinib ko‘ring.")
        await state.clear()
        return

    username = f"@{escape(callback.from_user.username)}" if callback.from_user.username else "Ko‘rsatilmagan"
    admin_message = (
        f"🔔 <b>YANGI MUROJAAT №{lead_id}</b>\n\n"
        f"👤 <b>Ota-ona:</b> {esc(data['parent_name'])}\n"
        f"📞 <b>Telefon:</b> {esc(data['phone'])}\n"
        f"👦 <b>Farzandi:</b> {esc(data['child_name'])}\n"
        f"🎂 <b>Yoshi:</b> {data['child_age']}\n"
        f"🎓 <b>Sinf:</b> {esc(data['grade'])}\n"
        f"🏫 <b>Hozirgi maktabi:</b> {esc(data['current_school'])}\n"
        f"📌 <b>Murojaat:</b> {esc(request_type)}\n"
        f"🔗 <b>Telegram:</b> {username}\n"
        f"🆔 <b>Telegram ID:</b> <code>{callback.from_user.id}</code>\n"
        f"📅 <b>Sana:</b> {datetime.now().astimezone().strftime('%d.%m.%Y %H:%M')}"
    )
    admin_notified = True
    try:
        await bot.send_message(ADMIN_ID, admin_message, reply_markup=lead_actions_keyboard(lead_id))
    except Exception:
        admin_notified = False
        logger.exception("Admin xabari yuborilmadi; murojaat bazada saqlandi: %s", lead_id)

    await state.clear()
    text = (
        f"✅ <b>Murojaatingiz qabul qilindi!</b>\n\n"
        f"Murojaat raqami: <b>#{lead_id}</b>\n"
        "Maktab administratorimiz siz bilan bog‘lanadi.\n\n"
        "Buxoro Qorako‘l xususiy maktabiga qiziqish bildirganingiz uchun rahmat!"
    )
    if not admin_notified:
        text += "\n\nAdministratorga bildirishnoma yetkazishda kechikish bo‘lishi mumkin."
    await callback.answer("Murojaat qabul qilindi!")
    await callback.message.answer(text, reply_markup=parent_menu())

# Parent menu entries all open a tracked inquiry, not just a static dead-end.
@dp.message(F.text == "🎓 Maktabga qabul")
async def menu_admission(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, REQUEST_TYPES["admission"])

@dp.message(F.text == "🏫 Maktab haqida")
async def menu_about(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, REQUEST_TYPES["about"])

@dp.message(F.text == "💰 Kontrakt va to‘lovlar")
async def menu_payment(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, REQUEST_TYPES["payment"])

@dp.message(F.text == "📚 Ta’lim yo‘nalishlari")
async def menu_education(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, REQUEST_TYPES["education"])

@dp.message(F.text == "🏆 Olimpiadalar")
async def menu_olympiads(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, REQUEST_TYPES["olympiad"])

@dp.message(F.text == "📅 Maktabga tashrif")
async def menu_visit(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, REQUEST_TYPES["visit"])

@dp.message(F.text == "📍 Manzil va aloqa")
async def menu_location(message: Message, state: FSMContext):
    await message.answer(
        f"📍 <b>Maktab manzili:</b> {esc(SCHOOL_ADDRESS)}\n"
        f"📞 <b>Aloqa:</b> {esc(SCHOOL_PHONE)}\n\n"
        "Aniq ma'lumot olish uchun administratorga murojaat qoldiring.",
        reply_markup=parent_menu(),
    )

@dp.message(F.text == "📞 Administrator bilan bog‘lanish")
async def menu_admin_contact(message: Message, state: FSMContext):
    await begin_parent_flow(message, state, "Administrator bilan bog‘lanish")

@dp.message(Command("privacy"))
async def privacy(message: Message):
    await message.answer(
        "🔐 <b>Maxfiylik haqida</b>\n\n"
        "Siz yuborgan ism-familiya, telefon va farzandingiz haqidagi ma'lumotlar "
        "maktab murojaatingizni ko‘rib chiqishi va siz bilan bog‘lanishi uchun "
        "saqlanadi. Ularga faqat vakolatli administrator kirish huquqiga ega.\n"
        "Ma'lumotlarni o‘chirish bo‘yicha /delete_my_data buyrug‘idan foydalanishingiz mumkin.",
        reply_markup=parent_menu(),
    )

@dp.message(Command("delete_my_data"))
async def delete_my_data(message: Message, state: FSMContext):
    await state.clear()
    deleted = await delete_user_data(message.from_user.id)
    await message.answer(
        f"Ushbu Telegram akkauntingizga bog‘langan {deleted} ta murojaat yozuvi bazadan o‘chirildi.",
        reply_markup=parent_menu(),
    )

@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Joriy jarayon bekor qilindi. Menyudan tanlang.", reply_markup=parent_menu())

# ADMIN PANEL
@dp.message(Command("admin"))
async def admin_home(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "🛠 <b>Buxoro Qorako‘l — Admin CRM</b>\nKerakli bo‘limni tanlang.",
        reply_markup=admin_menu(),
    )

@dp.message(F.text == "ℹ️ Admin yordam")
async def admin_help(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "<b>Admin buyruqlari</b>\n"
        "/admin — bosh menyu\n"
        "/new — yangi murojaatlar\n"
        "/leads — oxirgi murojaatlar\n"
        "/stats — statistika\n"
        "/search — mijoz qidirish\n"
        "/export — CSV faylga eksport\n"
        "/lead 12 — murojaat kartochkasi\n"
        "/cancel — joriy amalni bekor qilish",
        reply_markup=admin_menu(),
    )

async def send_lead_list(message: Message, leads: list[dict], title: str):
    if not leads:
        await message.answer(f"{title}\n\nHozircha murojaatlar topilmadi.")
        return
    await message.answer(f"<b>{title}</b>")
    for lead in leads:
        await message.answer(
            f"№{lead['id']} · {esc(lead['parent_name'])}\n"
            f"📞 {esc(lead['phone'])}\n"
            f"👦 {esc(lead['child_name'])} · {esc(lead['grade'])}\n"
            f"📌 {esc(STATUSES.get(lead['status'], lead['status']))}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Kartochkani ochish", callback_data=f"open:{lead['id']}")
            ]]),
        )

@dp.message(Command("new"))
@dp.message(F.text == "🆕 Yangi murojaatlar")
async def admin_new(message: Message):
    if not is_admin(message.from_user.id):
        return
    await send_lead_list(message, await list_leads("new", 15), "🆕 Yangi murojaatlar")

@dp.message(Command("leads"))
@dp.message(F.text == "📋 Barcha murojaatlar")
async def admin_leads(message: Message):
    if not is_admin(message.from_user.id):
        return
    await send_lead_list(message, await list_leads(None, 15), "📋 Oxirgi murojaatlar")

@dp.message(Command("stats"))
@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    total, today, status_counts, grade_counts = await get_statistics()
    lines = [
        "📊 <b>Qabul statistikasi</b>",
        f"Jami murojaatlar: <b>{total}</b>",
        f"Bugungi murojaatlar: <b>{today}</b>",
        "",
        "<b>Statuslar bo‘yicha:</b>",
    ]
    for key, label in STATUSES.items():
        lines.append(f"• {label}: <b>{status_counts.get(key, 0)}</b>")
    lines.extend(["", "<b>Sinf bo‘yicha:</b>"])
    for grade, count in grade_counts:
        lines.append(f"• {esc(grade)}: <b>{count}</b>")
    await message.answer("\n".join(lines), reply_markup=admin_menu())

@dp.callback_query(F.data.startswith("open:"))
async def open_lead(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    lead_id = int(callback.data.split(":")[1])
    lead = await fetch_lead(lead_id)
    if not lead:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(lead_card(lead), reply_markup=lead_actions_keyboard(lead_id))

@dp.callback_query(F.data.startswith("status:"))
async def change_lead_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    _, lead_id_raw, status = callback.data.split(":")
    if status not in STATUSES:
        await callback.answer("Status noto‘g‘ri.", show_alert=True)
        return
    lead_id = int(lead_id_raw)
    updated = await update_status(lead_id, status)
    if not updated:
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    lead = await fetch_lead(lead_id)
    await callback.answer("Status yangilandi.")
    await callback.message.edit_text(lead_card(lead), reply_markup=lead_actions_keyboard(lead_id))

@dp.callback_query(F.data.startswith("note:"))
async def start_note(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    lead_id = int(callback.data.split(":")[1])
    await state.clear()
    await state.update_data(note_lead_id=lead_id)
    await state.set_state(AdminNote.waiting_for_note)
    await callback.answer()
    await callback.message.answer(f"№{lead_id} murojaat uchun administrator izohini yuboring.")

@dp.message(AdminNote.waiting_for_note)
async def save_note(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    note = (message.text or "").strip()
    if not note or len(note) > 1000:
        await message.answer("Izoh 1–1000 belgi bo‘lsin.")
        return
    data = await state.get_data()
    lead_id = data["note_lead_id"]
    await add_admin_note(lead_id, note)
    await state.clear()
    lead = await fetch_lead(lead_id)
    await message.answer("✅ Izoh saqlandi.\n\n" + lead_card(lead), reply_markup=lead_actions_keyboard(lead_id))

@dp.message(Command("search"))
@dp.message(F.text == "🔎 Mijoz qidirish")
async def start_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminSearch.waiting_for_query)
    await message.answer("Ota-ona ismi, farzand ismi yoki telefon raqamining bir qismini yuboring.")

@dp.message(AdminSearch.waiting_for_query)
async def run_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Kamida 2 ta belgi kiriting.")
        return
    await state.clear()
    await send_lead_list(message, await search_leads(query), f"🔎 Qidiruv natijalari: {esc(query)}")

@dp.message(Command("lead"))
async def admin_single_lead(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /lead 12")
        return
    lead = await fetch_lead(int(parts[1]))
    if not lead:
        await message.answer("Bunday murojaat topilmadi.")
        return
    await message.answer(lead_card(lead), reply_markup=lead_actions_keyboard(lead["id"]))

@dp.message(Command("export"))
@dp.message(F.text == "📤 Excel/CSV eksport")
async def admin_export(message: Message):
    if not is_admin(message.from_user.id):
        return
    data = await export_csv()
    filename = f"school_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    await message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption="📤 Murojaatlar eksporti (CSV). Excel orqali ochishingiz mumkin.",
    )

@dp.message()
async def fallback(message: Message):
    if message.from_user and is_admin(message.from_user.id):
        await message.answer("Admin panel uchun /admin buyrug‘ini yuboring.", reply_markup=admin_menu())
    else:
        await message.answer("Menyudan kerakli bo‘limni tanlang yoki /start buyrug‘ini yuboring.", reply_markup=parent_menu())

async def main():
    await init_db()
    logger.info("School CRM bot ishga tushmoqda.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
