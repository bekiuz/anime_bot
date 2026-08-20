import asyncio
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

DB_PATH = "data/bot.db"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN topilmadi")

if not ADMIN_IDS:
    raise ValueError("❌ ADMIN_IDS topilmadi")

Path("data").mkdir(exist_ok=True)


# =========================================================
# DATABASE
# =========================================================

def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            is_vip INTEGER DEFAULT 0,
            vip_until TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            video_file_id TEXT NOT NULL,
            is_vip INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (anime_id) REFERENCES animes(id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS shorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            video_file_id TEXT NOT NULL,
            is_vip INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


def register_user(user):
    connection = db()

    connection.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            full_name,
            is_admin
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name,
            is_admin=excluded.is_admin
        """,
        (
            user.id,
            user.username,
            user.full_name,
            1 if user.id in ADMIN_IDS else 0,
        ),
    )

    connection.commit()
    connection.close()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================================================
# BOT
# =========================================================

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    ),
)

dp = Dispatcher()


# =========================================================
# STATES
# =========================================================

class AddAnime(StatesGroup):
    title = State()
    description = State()


class EditAnime(StatesGroup):
    anime_id = State()
    title = State()
    description = State()


class AddEpisode(StatesGroup):
    anime_id = State()
    anime_title = State()
    number = State()
    title = State()
    video = State()


class EditEpisode(StatesGroup):
    episode_id = State()
    title = State()
    video = State()


class AddShort(StatesGroup):
    title = State()
    description = State()
    video = State()


class EditShort(StatesGroup):
    short_id = State()
    title = State()
    description = State()
    video = State()


class VipAdd(StatesGroup):
    user_id = State()
    days = State()


class VipRemove(StatesGroup):
    user_id = State()


class Broadcast(StatesGroup):
    message = State()


# =========================================================
# KEYBOARDS
# =========================================================


def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="❌ Bekor qilish"
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def make_kb(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def back_keyboard(callback_data):
    return make_kb([
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data=callback_data
            )
        ]
    ])


def admin_main_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="🎬 Anime",
                callback_data="admin_anime"
            ),
            InlineKeyboardButton(
                text="📺 Qismlar",
                callback_data="admin_episodes"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎞 Shorts",
                callback_data="admin_shorts"
            ),
            InlineKeyboardButton(
                text="⭐ VIP",
                callback_data="admin_vip"
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 Rassilka",
                callback_data="admin_broadcast"
            ),
            InlineKeyboardButton(
                text="👥 Foydalanuvchilar",
                callback_data="admin_users"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Statistika",
                callback_data="admin_stats"
            )
        ]
    ])


def anime_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="➕ Anime qo‘shish",
                callback_data="anime_add"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Anime tahrirlash",
                callback_data="anime_edit"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Anime o‘chirish",
                callback_data="anime_delete"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Anime ro‘yxati",
                callback_data="anime_list"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Admin panel",
                callback_data="admin_back"
            )
        ]
    ])


def episodes_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="➕ Qism qo‘shish",
                callback_data="episode_add"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Qism tahrirlash",
                callback_data="episode_edit"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Qism o‘chirish",
                callback_data="episode_delete"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Qismlar ro‘yxati",
                callback_data="episode_list"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Admin panel",
                callback_data="admin_back"
            )
        ]
    ])


def shorts_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="➕ Shorts qo‘shish",
                callback_data="short_add"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Shorts tahrirlash",
                callback_data="short_edit"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Shorts o‘chirish",
                callback_data="short_delete"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Shorts ro‘yxati",
                callback_data="short_list"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Admin panel",
                callback_data="admin_back"
            )
        ]
    ])


def vip_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="⭐ VIP berish",
                callback_data="vip_add"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ VIPni olib tashlash",
                callback_data="vip_remove"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 VIP ro‘yxati",
                callback_data="vip_list"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Admin panel",
                callback_data="admin_back"
            )
        ]
    ])



def user_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔎 ID qidirish"),
                KeyboardButton(text="🎞 Shorts")
            ],
            [
                KeyboardButton(text="⭐ VIP"),
                KeyboardButton(text="📩 Murojaat")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def admin_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎬 Anime"),
                KeyboardButton(text="📺 Qismlar")
            ],
            [
                KeyboardButton(text="🎞 Shorts"),
                KeyboardButton(text="⭐ VIP")
            ],
            [
                KeyboardButton(text="📢 Rassilka"),
                KeyboardButton(text="👥 Foydalanuvchilar")
            ],
            [
                KeyboardButton(text="📊 Statistika")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def user_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="🔎 ID qidirish",
                callback_data="user_search"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎞 Shorts",
                callback_data="user_shorts"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐ VIP",
                callback_data="user_vip"
            )
        ],
        [
            InlineKeyboardButton(
                text="📩 Murojaat",
                callback_data="user_contact"
            )
        ]
    ])



# =========================================================
# BEKOR QILISH
# =========================================================

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_all(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "❌ <b>Amal bekor qilindi.</b>",
        reply_markup=ReplyKeyboardRemove()
    )

    if is_admin(message.from_user.id):

        await message.answer(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "Kerakli bo‘limni tanlang:",
            reply_markup=admin_reply_keyboard()
        )

    else:

        await message.answer(
            "🎬 <b>Anime Bot</b>\n\n"
            "Anime yoki qism ID raqamini yuboring 🔎",
            reply_markup=user_reply_keyboard()
        )


@dp.message(F.text == "/cancel")
async def cancel_command(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "❌ <b>Amal bekor qilindi.</b>",
        reply_markup=ReplyKeyboardRemove()
    )

    if is_admin(message.from_user.id):

        await message.answer(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "Kerakli bo‘limni tanlang:",
            reply_markup=admin_reply_keyboard()
        )

    else:

        await message.answer(
            "🎬 <b>Anime Bot</b>\n\n"
            "Anime yoki qism ID raqamini yuboring 🔎",
            reply_markup=user_reply_keyboard()
        )


# =========================================================
# STARTUP
# =========================================================

@dp.startup()
async def startup():
    init_db()

    print("========================================")
    print("🤖 ANIME BOT")
    print("========================================")
    print(f"✅ {len(ADMIN_IDS)} ta admin yuklandi")
    print("✅ SQLite database tayyor")
    print("✅ Anime tizimi tayyor")
    print("✅ Qism tizimi tayyor")
    print("✅ Shorts tizimi tayyor")
    print("✅ VIP tizimi tayyor")
    print("✅ Rassilka tizimi tayyor")
    print("🚀 Polling boshlandi")
    print("========================================")


# =========================================================
# START
# =========================================================


@dp.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext
):

    register_user(message.from_user)

    await state.clear()

    if is_admin(message.from_user.id):

        await message.answer(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "Pastki klaviaturadan kerakli bo‘limni tanlang:",
            reply_markup=admin_reply_keyboard()
        )

    else:

        await message.answer(
            "🎬 <b>Anime Bot</b>\n\n"
            "Kerakli bo‘limni pastki klaviaturadan tanlang.",
            reply_markup=user_reply_keyboard()
        )


# =========================================================
# ADMIN MAIN
# =========================================================

@dp.callback_query(F.data == "admin_back")
async def admin_back(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.clear()

    await callback.message.edit_text(
        "👑 <b>ADMIN PANEL</b>\n\n"
        "Kerakli bo‘limni tanlang:",
        reply_markup=admin_main_keyboard()
    )

    await callback.answer()



# =========================================================
# ADMIN REPLY KEYBOARD HANDLERS
# =========================================================

@dp.message(F.text == "🎬 Anime")
async def admin_reply_anime(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    await message.answer(
        "🎬 <b>ANIME BOSHQARUVI</b>\n\n"
        "Quyidagi inline menyudan kerakli amalni tanlang:",
        reply_markup=admin_reply_keyboard()
    )

    await message.answer(
        "🎬 Anime menyusi:",
        reply_markup=anime_keyboard()
    )


@dp.message(F.text == "📺 Qismlar")
async def admin_reply_episodes(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    await message.answer(
        "📺 <b>QISMLAR BOSHQARUVI</b>",
        reply_markup=admin_reply_keyboard()
    )

    await message.answer(
        "📺 Qismlar menyusi:",
        reply_markup=episodes_keyboard()
    )


@dp.message(F.text == "🎞 Shorts")
async def admin_reply_shorts(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    await message.answer(
        "🎞 <b>SHORTS BOSHQARUVI</b>",
        reply_markup=admin_reply_keyboard()
    )

    await message.answer(
        "🎞 Shorts menyusi:",
        reply_markup=shorts_keyboard()
    )


@dp.message(F.text == "⭐ VIP")
async def admin_reply_vip(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    await message.answer(
        "⭐ <b>VIP BOSHQARUVI</b>",
        reply_markup=admin_reply_keyboard()
    )

    await message.answer(
        "⭐ VIP menyusi:",
        reply_markup=vip_keyboard()
    )


@dp.message(F.text == "👥 Foydalanuvchilar")
async def admin_reply_users(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    await message.answer(
        "👥 <b>FOYDALANUVCHILAR</b>",
        reply_markup=admin_reply_keyboard()
    )


@dp.message(F.text == "📊 Statistika")
async def admin_reply_stats(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    connection = db()

    users_count = connection.execute(
        "SELECT COUNT(*) AS n FROM users"
    ).fetchone()["n"]

    anime_count = connection.execute(
        "SELECT COUNT(*) AS n FROM animes"
    ).fetchone()["n"]

    episode_count = connection.execute(
        "SELECT COUNT(*) AS n FROM episodes"
    ).fetchone()["n"]

    shorts_count = connection.execute(
        "SELECT COUNT(*) AS n FROM shorts"
    ).fetchone()["n"]

    vip_count = connection.execute(
        "SELECT COUNT(*) AS n FROM users WHERE is_vip=1"
    ).fetchone()["n"]

    connection.close()

    await message.answer(
        "📊 <b>STATISTIKA</b>\n\n"
        f"👥 Users: <b>{users_count}</b>\n"
        f"🎬 Anime: <b>{anime_count}</b>\n"
        f"📺 Qismlar: <b>{episode_count}</b>\n"
        f"🎞 Shorts: <b>{shorts_count}</b>\n"
        f"⭐ VIP: <b>{vip_count}</b>",
        reply_markup=admin_reply_keyboard()
    )


@dp.message(F.text == "📢 Rassilka")
async def admin_reply_broadcast(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    await state.set_state(
        Broadcast.message
    )

    await message.answer(
        "📢 <b>RASSILKA</b>\n\n"
        "Yuboriladigan xabarni yuboring.",
        reply_markup=admin_reply_keyboard()
    )


# =========================================================
# ANIME MENU
# =========================================================

@dp.callback_query(F.data == "admin_anime")
async def admin_anime(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.clear()

    await callback.message.edit_text(
        "🎬 <b>ANIME BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        reply_markup=anime_keyboard()
    )

    await callback.answer()


# =========================================================
# ANIME ADD
# =========================================================

@dp.callback_query(F.data == "anime_add")
async def anime_add(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.set_state(AddAnime.title)

    await callback.message.edit_text(
        "➕ <b>ANIME QO‘SHISH</b>\n\n"
        "1️⃣ Anime nomini yuboring:"
    )

    await callback.message.answer(
        "❌ Tugma orqali bekor qilishingiz mumkin.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(AddAnime.title)
async def anime_add_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "❌ Anime nomini kiriting."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddAnime.description
    )

    await message.answer(
        "2️⃣ Anime tavsifini yuboring:",
        reply_markup=cancel_keyboard()
    )


@dp.message(AddAnime.description)
async def anime_add_description(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    description = (message.text or "").strip()

    if not description:
        await message.answer(
            "❌ Tavsifni kiriting."
        )
        return

    data = await state.get_data()

    connection = db()

    cursor = connection.execute(
        """
        INSERT INTO animes (
            title,
            description
        )
        VALUES (?, ?)
        """,
        (
            data["title"],
            description
        )
    )

    anime_id = cursor.lastrowid

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ <b>ANIME SAQLANDI</b>\n\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎬 {data['title']}\n"
        f"📝 {description}",
        reply_markup=anime_keyboard()
    )


# =========================================================
# ANIME LIST
# =========================================================

@dp.callback_query(F.data == "anime_list")
async def anime_list(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id, title, description
        FROM animes
        WHERE is_active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    text = "📋 <b>ANIME RO‘YXATI</b>\n\n"

    if not rows:

        text += "Hozircha anime yo‘q."

    else:

        for row in rows:

            text += (
                f"🆔 <code>{row['id']}</code>\n"
                f"🎬 <b>{row['title']}</b>\n"
                f"📝 {row['description']}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard("admin_anime")
    )

    await callback.answer()


# =========================================================
# ANIME EDIT
# =========================================================

@dp.callback_query(F.data == "anime_edit")
async def anime_edit_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:
        await callback.answer(
            "❌ Anime yo‘q.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {row['title']}",
                callback_data=f"anime_edit_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Anime",
            callback_data="admin_anime"
        )
    ])

    await callback.message.edit_text(
        "✏️ <b>ANIME TAHRIRLASH</b>\n\n"
        "Animeni tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("anime_edit_"))
async def anime_edit_select(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    row = connection.execute(
        """
        SELECT title
        FROM animes
        WHERE id = ?
        """,
        (anime_id,)
    ).fetchone()

    connection.close()

    if not row:
        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )
        return

    await state.update_data(
        anime_id=anime_id
    )

    await state.set_state(
        EditAnime.title
    )

    await callback.message.edit_text(
        f"✏️ Hozirgi nom: <b>{row['title']}</b>\n\n"
        "Yangi nomni yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish mumkin.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(EditAnime.title)
async def anime_edit_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "❌ Nom kiriting."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        EditAnime.description
    )

    await message.answer(
        "Yangi tavsifni yuboring:"
    )


@dp.message(EditAnime.description)
async def anime_edit_description(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    description = (message.text or "").strip()

    if not description:
        await message.answer(
            "❌ Tavsif kiriting."
        )
        return

    data = await state.get_data()

    connection = db()

    connection.execute(
        """
        UPDATE animes
        SET title = ?,
            description = ?
        WHERE id = ?
        """,
        (
            data["title"],
            description,
            data["anime_id"]
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ <b>ANIME YANGILANDI</b>\n\n"
        f"🆔 ID: <code>{data['anime_id']}</code>\n"
        f"🎬 {data['title']}\n"
        f"📝 {description}",
        reply_markup=anime_keyboard()
    )


# =========================================================
# ANIME DELETE
# =========================================================

@dp.callback_query(F.data == "anime_delete")
async def anime_delete_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:
        await callback.answer(
            "❌ Anime yo‘q.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {row['title']}",
                callback_data=f"anime_delete_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Anime",
            callback_data="admin_anime"
        )
    ])

    await callback.message.edit_text(
        "🗑 <b>ANIME O‘CHIRISH</b>\n\n"
        "Animeni tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("anime_delete_"))
async def anime_delete_confirm(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    row = connection.execute(
        """
        SELECT title
        FROM animes
        WHERE id = ?
        """,
        (anime_id,)
    ).fetchone()

    connection.close()

    if not row:
        await callback.answer(
            "❌ Topilmadi.",
            show_alert=True
        )
        return

    confirm = make_kb([
        [
            InlineKeyboardButton(
                text="✅ Ha, o‘chirish",
                callback_data=f"anime_del_yes_{anime_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data="anime_delete"
            )
        ]
    ])

    await callback.message.edit_text(
        f"⚠️ <b>{row['title']}</b>\n\n"
        "Unga tegishli barcha qismlar ham o‘chadi.\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=confirm
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("anime_del_yes_"))
async def anime_delete_yes(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    connection.execute(
        """
        DELETE FROM episodes
        WHERE anime_id = ?
        """,
        (anime_id,)
    )

    connection.execute(
        """
        DELETE FROM animes
        WHERE id = ?
        """,
        (anime_id,)
    )

    connection.commit()
    connection.close()

    await callback.message.edit_text(
        "✅ <b>Anime o‘chirildi.</b>",
        reply_markup=anime_keyboard()
    )

    await callback.answer()


# =========================================================
# EPISODES MENU
# =========================================================

@dp.callback_query(F.data == "admin_episodes")
async def admin_episodes(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.clear()

    await callback.message.edit_text(
        "📺 <b>QISMLAR BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        reply_markup=episodes_keyboard()
    )

    await callback.answer()


# =========================================================
# EPISODE ADD
# =========================================================

@dp.callback_query(F.data == "episode_add")
async def episode_add_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:
        await callback.answer(
            "❌ Avval anime qo‘shing.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"🎬 {row['title']}",
                callback_data=f"episode_anime_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Qismlar",
            callback_data="admin_episodes"
        )
    ])

    await callback.message.edit_text(
        "➕ <b>QISM QO‘SHISH</b>\n\n"
        "Anime tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("episode_anime_"))
async def episode_choose_anime(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    row = connection.execute(
        """
        SELECT title
        FROM animes
        WHERE id = ?
        """,
        (anime_id,)
    ).fetchone()

    connection.close()

    if not row:
        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )
        return

    await state.update_data(
        anime_id=anime_id,
        anime_title=row["title"]
    )

    await state.set_state(
        AddEpisode.number
    )

    await callback.message.edit_text(
        f"🎬 <b>{row['title']}</b>\n\n"
        "1️⃣ Qism raqamini yuboring:"
    )

    await callback.answer()


@dp.message(AddEpisode.number)
async def episode_number(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    value = (message.text or "").strip()

    if not value.isdigit() or int(value) < 1:
        await message.answer(
            "❌ Masalan: <code>1</code>"
        )
        return

    await state.update_data(
        number=int(value)
    )

    await state.set_state(
        AddEpisode.title
    )

    await message.answer(
        "2️⃣ Qism nomini yuboring:",
        reply_markup=cancel_keyboard()
    )


@dp.message(AddEpisode.title)
async def episode_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "❌ Nom kiriting."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddEpisode.video
    )

    await message.answer(
        "3️⃣ Qism videosini yuboring 🎥",
        reply_markup=cancel_keyboard()
    )


@dp.message(AddEpisode.video, F.video)
async def episode_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    connection = db()

    cursor = connection.execute(
        """
        INSERT INTO episodes (
            anime_id,
            episode_number,
            title,
            video_file_id
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            data["anime_id"],
            data["number"],
            data["title"],
            message.video.file_id
        )
    )

    episode_id = cursor.lastrowid

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ <b>QISM SAQLANDI</b>\n\n"
        f"🆔 ID: <code>{episode_id}</code>\n"
        f"🎬 {data['anime_title']}\n"
        f"📺 {data['number']}-qism\n"
        f"📝 {data['title']}",
        reply_markup=episodes_keyboard()
    )


@dp.message(AddEpisode.video)
async def episode_video_wrong(
    message: Message
):

    if is_admin(message.from_user.id):
        await message.answer(
            "❌ Video yuboring 🎥"
        )


# =========================================================
# EPISODE LIST
# =========================================================

@dp.callback_query(F.data == "episode_list")
async def episode_list(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            e.title,
            a.title AS anime
        FROM episodes e
        JOIN animes a
            ON a.id = e.anime_id
        ORDER BY e.id DESC
        """
    ).fetchall()

    connection.close()

    text = "📋 <b>QISMLAR RO‘YXATI</b>\n\n"

    if not rows:

        text += "Hozircha qism yo‘q."

    else:

        for row in rows:

            text += (
                f"🆔 <code>{row['id']}</code>\n"
                f"🎬 {row['anime']}\n"
                f"📺 {row['episode_number']}-qism — {row['title']}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard("admin_episodes")
    )

    await callback.answer()


# =========================================================
# EPISODE EDIT
# =========================================================

@dp.callback_query(F.data == "episode_edit")
async def episode_edit_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            a.title AS anime
        FROM episodes e
        JOIN animes a
            ON a.id=e.anime_id
        ORDER BY e.id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:

        await callback.answer(
            "❌ Qism yo‘q.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {row['anime']} — {row['episode_number']}-qism",
                callback_data=f"episode_edit_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Qismlar",
            callback_data="admin_episodes"
        )
    ])

    await callback.message.edit_text(
        "✏️ <b>QISM TAHRIRLASH</b>\n\n"
        "Qismni tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("episode_edit_"))
async def episode_edit_select(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    row = connection.execute(
        """
        SELECT title
        FROM episodes
        WHERE id = ?
        """,
        (episode_id,)
    ).fetchone()

    connection.close()

    if not row:
        await callback.answer(
            "❌ Qism topilmadi.",
            show_alert=True
        )
        return

    await state.update_data(
        episode_id=episode_id
    )

    await state.set_state(
        EditEpisode.title
    )

    await callback.message.edit_text(
        f"✏️ Hozirgi nom: <b>{row['title']}</b>\n\n"
        "Yangi nomni yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish mumkin.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(EditEpisode.title)
async def edit_episode_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "❌ Nom kiriting."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        EditEpisode.video
    )

    await message.answer(
        "Yangi video yuboring yoki <code>skip</code> yozing:"
    )


@dp.message(EditEpisode.video, F.video)
async def edit_episode_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    connection = db()

    connection.execute(
        """
        UPDATE episodes
        SET title=?,
            video_file_id=?
        WHERE id=?
        """,
        (
            data["title"],
            message.video.file_id,
            data["episode_id"]
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ Qism yangilandi.",
        reply_markup=episodes_keyboard()
    )


@dp.message(EditEpisode.video)
async def edit_episode_skip(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if (message.text or "").strip().lower() != "skip":
        await message.answer(
            "❌ Video yuboring yoki <code>skip</code> yozing."
        )
        return

    data = await state.get_data()

    connection = db()

    connection.execute(
        """
        UPDATE episodes
        SET title=?
        WHERE id=?
        """,
        (
            data["title"],
            data["episode_id"]
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ Qism nomi yangilandi.",
        reply_markup=episodes_keyboard()
    )


# =========================================================
# EPISODE DELETE
# =========================================================

@dp.callback_query(F.data == "episode_delete")
async def episode_delete_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            a.title AS anime
        FROM episodes e
        JOIN animes a
            ON a.id=e.anime_id
        ORDER BY e.id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:

        await callback.answer(
            "❌ Qism yo‘q.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {row['anime']} — {row['episode_number']}-qism",
                callback_data=f"episode_delete_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Qismlar",
            callback_data="admin_episodes"
        )
    ])

    await callback.message.edit_text(
        "🗑 <b>QISM O‘CHIRISH</b>\n\n"
        "Qismni tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("episode_delete_"))
async def episode_delete(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    connection.execute(
        """
        DELETE FROM episodes
        WHERE id=?
        """,
        (episode_id,)
    )

    connection.commit()
    connection.close()

    await callback.message.edit_text(
        "✅ Qism o‘chirildi.",
        reply_markup=episodes_keyboard()
    )

    await callback.answer()


# =========================================================
# SHORTS MENU
# =========================================================

@dp.callback_query(F.data == "admin_shorts")
async def admin_shorts(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.clear()

    await callback.message.edit_text(
        "🎞 <b>SHORTS BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        reply_markup=shorts_keyboard()
    )

    await callback.answer()


# =========================================================
# SHORT ADD
# =========================================================

@dp.callback_query(F.data == "short_add")
async def short_add(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.set_state(
        AddShort.title
    )

    await callback.message.edit_text(
        "➕ <b>SHORTS QO‘SHISH</b>\n\n"
        "1️⃣ Shorts nomini yuboring:"
    )

    await callback.message.answer(
        "❌ Tugma orqali bekor qilishingiz mumkin.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(AddShort.title)
async def short_add_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "❌ Nom kiriting."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddShort.description
    )

    await message.answer(
        "2️⃣ Shorts tavsifini yuboring:",
        reply_markup=cancel_keyboard()
    )


@dp.message(AddShort.description)
async def short_add_description(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    description = (message.text or "").strip()

    if not description:
        await message.answer(
            "❌ Tavsif kiriting."
        )
        return

    await state.update_data(
        description=description
    )

    await state.set_state(
        AddShort.video
    )

    await message.answer(
        "3️⃣ Shorts videosini yuboring 🎥",
        reply_markup=cancel_keyboard()
    )


@dp.message(AddShort.video, F.video)
async def short_add_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    connection = db()

    cursor = connection.execute(
        """
        INSERT INTO shorts (
            title,
            description,
            video_file_id
        )
        VALUES (?, ?, ?)
        """,
        (
            data["title"],
            data["description"],
            message.video.file_id
        )
    )

    short_id = cursor.lastrowid

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ <b>SHORTS SAQLANDI</b>\n\n"
        f"🆔 ID: <code>{short_id}</code>\n"
        f"🎞 {data['title']}",
        reply_markup=shorts_keyboard()
    )


@dp.message(AddShort.video)
async def short_video_wrong(
    message: Message
):

    if is_admin(message.from_user.id):
        await message.answer(
            "❌ Video yuboring 🎥"
        )


# =========================================================
# SHORT LIST
# =========================================================

@dp.callback_query(F.data == "short_list")
async def short_list(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id,title,description,is_vip
        FROM shorts
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    text = "📋 <b>SHORTS RO‘YXATI</b>\n\n"

    if not rows:

        text += "Hozircha shorts yo‘q."

    else:

        for row in rows:

            vip = " ⭐ VIP" if row["is_vip"] else ""

            text += (
                f"🆔 <code>{row['id']}</code>\n"
                f"🎞 <b>{row['title']}</b>{vip}\n"
                f"📝 {row['description']}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard("admin_shorts")
    )

    await callback.answer()


# =========================================================
# SHORT EDIT
# =========================================================

@dp.callback_query(F.data == "short_edit")
async def short_edit_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id,title
        FROM shorts
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:
        await callback.answer(
            "❌ Shorts yo‘q.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {row['title']}",
                callback_data=f"short_edit_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Shorts",
            callback_data="admin_shorts"
        )
    ])

    await callback.message.edit_text(
        "✏️ <b>SHORTS TAHRIRLASH</b>\n\n"
        "Shortsni tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("short_edit_"))
async def short_edit_select(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    row = connection.execute(
        """
        SELECT title
        FROM shorts
        WHERE id=?
        """,
        (short_id,)
    ).fetchone()

    connection.close()

    if not row:
        await callback.answer(
            "❌ Shorts topilmadi.",
            show_alert=True
        )
        return

    await state.update_data(
        short_id=short_id
    )

    await state.set_state(
        EditShort.title
    )

    await callback.message.edit_text(
        f"✏️ Hozirgi nom: <b>{row['title']}</b>\n\n"
        "Yangi nomni yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish mumkin.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(EditShort.title)
async def short_edit_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await message.answer(
            "❌ Nom kiriting."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        EditShort.description
    )

    await message.answer(
        "Yangi tavsifni yuboring:"
    )


@dp.message(EditShort.description)
async def short_edit_description(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    description = (message.text or "").strip()

    if not description:
        await message.answer(
            "❌ Tavsif kiriting."
        )
        return

    await state.update_data(
        description=description
    )

    await state.set_state(
        EditShort.video
    )

    await message.answer(
        "Yangi video yuboring yoki <code>skip</code> yozing:"
    )


@dp.message(EditShort.video, F.video)
async def short_edit_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    connection = db()

    connection.execute(
        """
        UPDATE shorts
        SET title=?,
            description=?,
            video_file_id=?
        WHERE id=?
        """,
        (
            data["title"],
            data["description"],
            message.video.file_id,
            data["short_id"]
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ Shorts yangilandi.",
        reply_markup=shorts_keyboard()
    )


@dp.message(EditShort.video)
async def short_edit_skip(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if (message.text or "").strip().lower() != "skip":
        await message.answer(
            "❌ Video yuboring yoki <code>skip</code> yozing."
        )
        return

    data = await state.get_data()

    connection = db()

    connection.execute(
        """
        UPDATE shorts
        SET title=?,
            description=?
        WHERE id=?
        """,
        (
            data["title"],
            data["description"],
            data["short_id"]
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ Shorts ma’lumotlari yangilandi.",
        reply_markup=shorts_keyboard()
    )


# =========================================================
# SHORT DELETE
# =========================================================

@dp.callback_query(F.data == "short_delete")
async def short_delete_menu(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT id,title
        FROM shorts
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    if not rows:
        await callback.answer(
            "❌ Shorts yo‘q.",
            show_alert=True
        )
        return

    buttons = []

    for row in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {row['title']}",
                callback_data=f"short_delete_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Shorts",
            callback_data="admin_shorts"
        )
    ])

    await callback.message.edit_text(
        "🗑 <b>SHORTS O‘CHIRISH</b>\n\n"
        "Shortsni tanlang:",
        reply_markup=make_kb(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("short_delete_"))
async def short_delete(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    connection.execute(
        """
        DELETE FROM shorts
        WHERE id=?
        """,
        (short_id,)
    )

    connection.commit()
    connection.close()

    await callback.message.edit_text(
        "✅ Shorts o‘chirildi.",
        reply_markup=shorts_keyboard()
    )

    await callback.answer()


# =========================================================
# VIP
# =========================================================

@dp.callback_query(F.data == "admin_vip")
async def admin_vip(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.clear()

    await callback.message.edit_text(
        "⭐ <b>VIP BOSHQARUVI</b>\n\n"
        "Amalni tanlang:",
        reply_markup=vip_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "vip_add")
async def vip_add(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.set_state(
        VipAdd.user_id
    )

    await callback.message.edit_text(
        "⭐ <b>VIP BERISH</b>\n\n"
        "Foydalanuvchining Telegram ID sini yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish tugmasi tayyor.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(VipAdd.user_id)
async def vip_add_id(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    value = (message.text or "").strip()

    if not value.isdigit():

        await message.answer(
            "❌ Telegram ID raqam bo‘lishi kerak."
        )
        return

    await state.update_data(
        user_id=int(value)
    )

    await state.set_state(
        VipAdd.days
    )

    await message.answer(
        "Necha kunlik VIP?\n\n"
        "Masalan: <code>30</code>",
        reply_markup=cancel_keyboard()
    )


@dp.message(VipAdd.days)
async def vip_add_days(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    value = (message.text or "").strip()

    if not value.isdigit() or int(value) < 1:

        await message.answer(
            "❌ Kun sonini kiriting."
        )
        return

    days = int(value)

    data = await state.get_data()

    vip_until = (
        datetime.now(timezone.utc)
        + timedelta(days=days)
    ).isoformat()

    connection = db()

    connection.execute(
        """
        INSERT INTO users (
            telegram_id,
            is_vip,
            vip_until
        )
        VALUES (?, 1, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            is_vip=1,
            vip_until=excluded.vip_until
        """,
        (
            data["user_id"],
            vip_until
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ <b>VIP BERILDI</b>\n\n"
        f"👤 ID: <code>{data['user_id']}</code>\n"
        f"⏳ {days} kun",
        reply_markup=vip_keyboard()
    )


@dp.callback_query(F.data == "vip_remove")
async def vip_remove(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.set_state(
        VipRemove.user_id
    )

    await callback.message.edit_text(
        "❌ <b>VIPNI OLIB TASHLASH</b>\n\n"
        "Telegram ID raqamini yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish tugmasi tayyor.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(VipRemove.user_id)
async def vip_remove_id(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    value = (message.text or "").strip()

    if not value.isdigit():

        await message.answer(
            "❌ ID raqam bo‘lishi kerak."
        )
        return

    connection = db()

    connection.execute(
        """
        UPDATE users
        SET is_vip=0,
            vip_until=NULL
        WHERE telegram_id=?
        """,
        (int(value),)
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ VIP olib tashlandi.\n\n"
        f"👤 ID: <code>{value}</code>",
        reply_markup=vip_keyboard()
    )


@dp.callback_query(F.data == "vip_list")
async def vip_list(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT
            telegram_id,
            full_name,
            username,
            vip_until
        FROM users
        WHERE is_vip=1
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    text = "⭐ <b>VIP RO‘YXATI</b>\n\n"

    if not rows:

        text += "Hozircha VIP foydalanuvchi yo‘q."

    else:

        for row in rows:

            text += (
                f"👤 <code>{row['telegram_id']}</code>\n"
                f"📛 {row['full_name'] or '-'}\n"
                f"⏳ {row['vip_until'] or '-'}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard("admin_vip")
    )

    await callback.answer()


# =========================================================
# USERS
# =========================================================

@dp.callback_query(F.data == "admin_users")
async def admin_users(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    rows = connection.execute(
        """
        SELECT
            telegram_id,
            full_name,
            username,
            is_vip
        FROM users
        ORDER BY id DESC
        LIMIT 50
        """
    ).fetchall()

    connection.close()

    text = "👥 <b>FOYDALANUVCHILAR</b>\n\n"

    if not rows:

        text += "Hozircha foydalanuvchi yo‘q."

    else:

        for row in rows:

            vip = " ⭐ VIP" if row["is_vip"] else ""

            text += (
                f"🆔 <code>{row['telegram_id']}</code>\n"
                f"📛 {row['full_name'] or '-'}{vip}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard("admin_back")
    )

    await callback.answer()


# =========================================================
# STATS
# =========================================================

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    connection = db()

    users_count = connection.execute(
        "SELECT COUNT(*) AS n FROM users"
    ).fetchone()["n"]

    anime_count = connection.execute(
        "SELECT COUNT(*) AS n FROM animes"
    ).fetchone()["n"]

    episode_count = connection.execute(
        "SELECT COUNT(*) AS n FROM episodes"
    ).fetchone()["n"]

    shorts_count = connection.execute(
        "SELECT COUNT(*) AS n FROM shorts"
    ).fetchone()["n"]

    vip_count = connection.execute(
        "SELECT COUNT(*) AS n FROM users WHERE is_vip=1"
    ).fetchone()["n"]

    connection.close()

    await callback.message.edit_text(
        "📊 <b>STATISTIKA</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users_count}</b>\n"
        f"🎬 Animelar: <b>{anime_count}</b>\n"
        f"📺 Qismlar: <b>{episode_count}</b>\n"
        f"🎞 Shorts: <b>{shorts_count}</b>\n"
        f"⭐ VIP: <b>{vip_count}</b>",
        reply_markup=back_keyboard("admin_back")
    )

    await callback.answer()


# =========================================================
# BROADCAST
# =========================================================

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    await state.set_state(
        Broadcast.message
    )

    await callback.message.edit_text(
        "📢 <b>RASSILKA</b>\n\n"
        "Yuboriladigan xabarni shu yerga yuboring.\n\n"
        "Matn, rasm, video yoki boshqa Telegram xabari bo‘lishi mumkin."
    )

    await callback.message.answer(
        "❌ Bekor qilish mumkin.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(Broadcast.message)
async def broadcast_message(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    connection = db()

    users = connection.execute(
        "SELECT telegram_id FROM users"
    ).fetchall()

    connection.close()

    sent = 0
    failed = 0

    for user in users:

        try:

            await bot.copy_message(
                chat_id=user["telegram_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            sent += 1

        except Exception:

            failed += 1

        await asyncio.sleep(0.03)

    connection = db()

    connection.execute(
        """
        INSERT INTO broadcasts (
            message_id,
            sent_count,
            failed_count
        )
        VALUES (?, ?, ?)
        """,
        (
            message.message_id,
            sent,
            failed
        )
    )

    connection.commit()
    connection.close()

    await state.clear()

    await message.answer(
        "✅ <b>RASSILKA YAKUNLANDI</b>\n\n"
        f"✅ Yuborildi: <b>{sent}</b>\n"
        f"❌ Xatolik: <b>{failed}</b>",
        reply_markup=admin_main_keyboard()
    )


# =========================================================
# USER MENU
# =========================================================

@dp.callback_query(F.data == "user_search")
async def user_search(
    callback: CallbackQuery
):

    await callback.message.edit_text(
        "🔎 <b>ID ORQALI QIDIRISH</b>\n\n"
        "Anime yoki qism ID raqamini yuboring.\n\n"
        "Masalan: <code>1</code>"
    )

    await callback.answer()


@dp.callback_query(F.data == "user_back")
async def user_back(
    callback: CallbackQuery
):

    await callback.message.edit_text(
        "🎬 <b>Anime Bot</b>\n\n"
        "Anime yoki qism ID raqamini yuboring 🔎",
        reply_markup=user_keyboard()
    )

    await callback.answer()


# =========================================================
# USER SHORTS
# =========================================================


# =========================================================
# USER SHORTS
# =========================================================

def short_view_keyboard(current_id, next_id):

    rows = []

    if next_id is not None:

        rows.append([
            InlineKeyboardButton(
                text="➡️ Keyingisi",
                callback_data=f"next_short_{next_id}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Shorts",
            callback_data="user_shorts"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_back"
        )
    ])

    return make_kb(rows)


async def send_short_to_user(
    chat_id,
    short_id
):

    connection = db()

    short = connection.execute(
        """
        SELECT
            id,
            title,
            description,
            video_file_id,
            is_vip
        FROM shorts
        WHERE id = ?
        """,
        (short_id,)
    ).fetchone()

    user = connection.execute(
        """
        SELECT is_vip
        FROM users
        WHERE telegram_id = ?
        """,
        (chat_id,)
    ).fetchone()

    # Keyingi shortsni olamiz
    next_row = connection.execute(
        """
        SELECT id
        FROM shorts
        WHERE id > ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (short_id,)
    ).fetchone()

    if not next_row:
        next_row = connection.execute(
            """
            SELECT id
            FROM shorts
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()

    connection.close()

    if not short:
        return False

    is_vip = bool(
        user and user["is_vip"]
    )

    if short["is_vip"] and not is_vip:
        return "VIP"

    next_id = (
        next_row["id"]
        if next_row and next_row["id"] != short_id
        else None
    )

    keyboard = short_view_keyboard(
        short_id,
        next_id
    )

    await bot.send_video(
        chat_id=chat_id,
        video=short["video_file_id"],
        caption=(
            f"🎞 <b>{short['title']}</b>\n\n"
            f"{short['description']}"
        ),
        reply_markup=keyboard
    )

    return True


@dp.callback_query(F.data == "user_shorts")
async def user_shorts(
    callback: CallbackQuery
):

    connection = db()

    first = connection.execute(
        """
        SELECT id
        FROM shorts
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()

    connection.close()

    if not first:

        await callback.answer(
            "🎞 Hozircha Shorts yo‘q.",
            show_alert=True
        )
        return

    result = await send_short_to_user(
        callback.from_user.id,
        first["id"]
    )

    if result == "VIP":

        await callback.answer(
            "⭐ Bu Shorts VIP uchun.",
            show_alert=True
        )
        return

    await callback.answer()


@dp.callback_query(F.data.startswith("next_short_"))
async def next_short(
    callback: CallbackQuery
):

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    result = await send_short_to_user(
        callback.from_user.id,
        short_id
    )

    if result == "VIP":

        await callback.answer(
            "⭐ Bu Shorts VIP uchun.",
            show_alert=True
        )
        return

    if result is False:

        await callback.answer(
            "❌ Shorts topilmadi.",
            show_alert=True
        )
        return

    await callback.answer()


# =========================================================
# USER VIP
# =========================================================


# =========================================================
# USER VIP
# =========================================================

@dp.callback_query(F.data == "user_vip")
async def user_vip(
    callback: CallbackQuery
):

    connection = db()

    row = connection.execute(
        """
        SELECT
            is_vip,
            vip_until
        FROM users
        WHERE telegram_id = ?
        """,
        (callback.from_user.id,)
    ).fetchone()

    connection.close()

    if row and row["is_vip"]:

        text = (
            "⭐ <b>SIZ VIPSIZ!</b>\n\n"
            f"⏳ Muddati: "
            f"<code>{row['vip_until'] or '-'}</code>"
        )

        keyboard = make_kb([
            [
                InlineKeyboardButton(
                    text="🏠 Bosh menyu",
                    callback_data="user_back"
                )
            ]
        ])

    else:

        text = (
            "⭐ <b>VIP OLISH</b>\n\n"
            "Maxsus VIP kontent va imkoniyatlardan "
            "foydalanish uchun quyidagi admin bilan bog‘laning:\n\n"
            "👤 <b>@Ichi1010</b>"
        )

        keyboard = make_kb([
            [
                InlineKeyboardButton(
                    text="⭐ VIP olish",
                    url="https://t.me/Ichi1010"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Bosh menyu",
                    callback_data="user_back"
                )
            ]
        ])

    await callback.message.edit_text(
        text,
        reply_markup=keyboard
    )

    await callback.answer()


# =========================================================
# USER CONTACT
# =========================================================


# =========================================================
# USER CONTACT
# =========================================================

@dp.callback_query(F.data == "user_contact")
async def user_contact(
    callback: CallbackQuery
):

    await callback.message.edit_text(
        "📩 <b>MUROJAAT</b>\n\n"
        "Admin bilan bog‘lanish:\n\n"
        "👤 <b>@Ichi1010</b>",
        reply_markup=make_kb([
            [
                InlineKeyboardButton(
                    text="📩 Bog‘lanish",
                    url="https://t.me/Ichi1010"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Bosh menyu",
                    callback_data="user_back"
                )
            ]
        ])
    )

    await callback.answer()



# =========================================================
# USER REPLY KEYBOARD HANDLERS
# =========================================================

@dp.message(F.text == "🔎 ID qidirish")
async def user_reply_id_search(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "🔎 <b>ID QIDIRISH</b>\n\n"
        "Anime yoki qism ID raqamini yuboring.\n\n"
        "Masalan: <code>1</code>"
    )


@dp.message(F.text == "🎞 Shorts")
async def user_reply_shorts(
    message: Message,
    state: FSMContext
):

    await state.clear()

    connection = db()

    first = connection.execute(
        """
        SELECT id
        FROM shorts
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()

    connection.close()

    if not first:

        await message.answer(
            "🎞 Hozircha Shorts yo‘q."
        )
        return

    result = await send_short_to_user(
        message.from_user.id,
        first["id"]
    )

    if result == "VIP":

        await message.answer(
            "⭐ Bu Shorts faqat VIP uchun."
        )


@dp.message(F.text == "⭐ VIP")
async def user_reply_vip(
    message: Message,
    state: FSMContext
):

    await state.clear()

    connection = db()

    row = connection.execute(
        """
        SELECT is_vip, vip_until
        FROM users
        WHERE telegram_id=?
        """,
        (message.from_user.id,)
    ).fetchone()

    connection.close()

    if row and row["is_vip"]:

        await message.answer(
            "⭐ <b>SIZ VIPSIZ!</b>\n\n"
            f"⏳ Muddati:\n"
            f"<code>{row['vip_until'] or '-'}</code>",
            reply_markup=user_reply_keyboard()
        )

    else:

        await message.answer(
            "⭐ <b>VIP OLISH</b>\n\n"
            "VIP kontent va imkoniyatlar uchun "
            "admin bilan bog‘laning:\n\n"
            "👤 <b>@Ichi1010</b>\n\n"
            "🔗 https://t.me/Ichi1010",
            reply_markup=user_reply_keyboard()
        )


@dp.message(F.text == "📩 Murojaat")
async def user_reply_contact(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "📩 <b>MUROJAAT</b>\n\n"
        "Admin bilan bog‘lanish:\n\n"
        "👤 <b>@Ichi1010</b>\n\n"
        "🔗 https://t.me/Ichi1010",
        reply_markup=user_reply_keyboard()
    )


# =========================================================
# DIRECT ID SEARCH
# =========================================================

@dp.message(F.text.regexp(r"^\d+$"))
async def numeric_search(
    message: Message,
    state: FSMContext
):

    current_state = await state.get_state()

    # FSM jarayonida bo‘lsa, state handler ishlaydi.
    if current_state:
        return

    register_user(
        message.from_user
    )

    value = int(
        message.text.strip()
    )

    connection = db()

    episode = connection.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            e.title,
            e.video_file_id,
            e.is_vip,
            a.title AS anime
        FROM episodes e
        JOIN animes a
            ON a.id=e.anime_id
        WHERE e.id=?
        """,
        (value,)
    ).fetchone()

    if episode:

        user = connection.execute(
            """
            SELECT is_vip
            FROM users
            WHERE telegram_id=?
            """,
            (message.from_user.id,)
        ).fetchone()

        connection.close()

        if episode["is_vip"] and not (
            user and user["is_vip"]
        ):

            await message.answer(
                "⭐ Bu qism faqat VIP uchun."
            )
            return

        await message.answer_video(
            episode["video_file_id"],
            caption=(
                f"🎬 <b>{episode['anime']}</b>\n"
                f"📺 {episode['episode_number']}-qism\n"
                f"📝 {episode['title']}\n"
                f"🆔 ID: <code>{episode['id']}</code>"
            )
        )

        return

    anime = connection.execute(
        """
        SELECT
            id,
            title,
            description
        FROM animes
        WHERE id=?
          AND is_active=1
        """,
        (value,)
    ).fetchone()

    if anime:

        episodes = connection.execute(
            """
            SELECT
                id,
                episode_number,
                title,
                is_vip
            FROM episodes
            WHERE anime_id=?
            ORDER BY episode_number
            """,
            (value,)
        ).fetchall()

        connection.close()

        buttons = []

        for episode in episodes:

            vip = " ⭐" if episode["is_vip"] else ""

            buttons.append([
                InlineKeyboardButton(
                    text=f"📺 {episode['episode_number']}-qism{vip}",
                    callback_data=f"user_episode_{episode['id']}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data="user_back"
            )
        ])

        await message.answer(
            f"🎬 <b>{anime['title']}</b>\n\n"
            f"{anime['description']}\n\n"
            "📺 <b>Qismlar:</b>",
            reply_markup=make_kb(buttons)
        )

        return

    connection.close()

    await message.answer(
        "❌ <b>Bunday anime yoki qism ID topilmadi.</b>\n\n"
        f"🔎 ID: <code>{value}</code>"
    )


# =========================================================
# USER EPISODE BUTTON
# =========================================================

@dp.callback_query(F.data.startswith("user_episode_"))
async def user_episode(
    callback: CallbackQuery
):

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    connection = db()

    episode = connection.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            e.title,
            e.video_file_id,
            e.is_vip,
            a.title AS anime
        FROM episodes e
        JOIN animes a
            ON a.id=e.anime_id
        WHERE e.id=?
        """,
        (episode_id,)
    ).fetchone()

    user = connection.execute(
        """
        SELECT is_vip
        FROM users
        WHERE telegram_id=?
        """,
        (callback.from_user.id,)
    ).fetchone()

    connection.close()

    if not episode:

        await callback.answer(
            "❌ Qism topilmadi.",
            show_alert=True
        )
        return

    if episode["is_vip"] and not (
        user and user["is_vip"]
    ):

        await callback.answer(
            "⭐ Bu qism VIP uchun.",
            show_alert=True
        )
        return

    await bot.send_video(
        callback.from_user.id,
        episode["video_file_id"],
        caption=(
            f"🎬 <b>{episode['anime']}</b>\n"
            f"📺 {episode['episode_number']}-qism\n"
            f"📝 {episode['title']}"
        )
    )

    await callback.answer()


# =========================================================
# FALLBACK
# =========================================================

@dp.message()
async def fallback(
    message: Message,
    state: FSMContext
):

    if await state.get_state():
        return

    register_user(
        message.from_user
    )

    if is_admin(message.from_user.id):

        await message.answer(
            "👑 <b>Admin paneldan foydalaning.</b>\n\n"
            "Yoki qism/anime ID yuboring.",
            reply_markup=admin_reply_keyboard()
        )

    else:

        await message.answer(
            "🔎 <b>Anime yoki qism ID raqamini yuboring.</b>",
            reply_markup=user_reply_keyboard()
        )


# =========================================================
# MAIN
# =========================================================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
