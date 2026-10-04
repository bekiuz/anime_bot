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
    FSInputFile,
)
from dotenv import load_dotenv
from backup_db import make_backup


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

DB_PATH = "data/bot.db"
BACKUP_INTERVAL_SECONDS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24")) * 60 * 60

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env faylida topilmadi.")

if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS .env faylida topilmadi.")

Path("data").mkdir(exist_ok=True)


# =========================================================
# BOT
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():

    conn = connect_db()

    conn.execute("""
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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            video_file_id TEXT NOT NULL,
            is_vip INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (anime_id)
            REFERENCES animes(id)
            ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS shorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            video_file_id TEXT NOT NULL,
            is_vip INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def update_episode_vip_status():

    conn = connect_db()

    animes = conn.execute(
        """
        SELECT id
        FROM animes
        WHERE is_active=1
        ORDER BY id ASC
        """
    ).fetchall()

    for anime in animes:

        episodes = conn.execute(
            """
            SELECT id
            FROM episodes
            WHERE anime_id=?
            ORDER BY episode_number ASC, id ASC
            """,
            (anime["id"],)
        ).fetchall()

        for index, episode in enumerate(episodes, start=1):

            is_vip = 1 if index > 3 else 0

            conn.execute(
                """
                UPDATE episodes
                SET is_vip=?
                WHERE id=?
                """,
                (
                    is_vip,
                    episode["id"]
                )
            )

    conn.commit()
    conn.close()


def register_user(user):

    conn = connect_db()

    conn.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            full_name,
            is_admin
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name,
            is_admin=excluded.is_admin
        """,
        (
            user.id,
            user.username,
            user.full_name,
            1 if user.id in ADMIN_IDS else 0
        )
    )

    conn.commit()
    conn.close()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def user_is_vip(user_id: int) -> bool:

    conn = connect_db()

    row = conn.execute(
        """
        SELECT is_vip, vip_until
        FROM users
        WHERE telegram_id=?
        """,
        (user_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False

    is_vip = bool(row["is_vip"])
    vip_until = row["vip_until"]

    if is_vip and vip_until:

        try:

            expiry = datetime.fromisoformat(vip_until)

            if expiry < datetime.now(timezone.utc):

                conn.execute(
                    """
                    UPDATE users
                    SET is_vip=0,
                        vip_until=NULL
                    WHERE telegram_id=?
                    """,
                    (user_id,)
                )

                conn.commit()

                is_vip = False

        except ValueError:
            pass

    conn.close()

    return is_vip


# =========================================================
# USER FEATURES / SAFETY
# =========================================================

def user_is_banned(user_id: int) -> bool:

    if is_admin(user_id):
        return False

    conn = connect_db()

    row = conn.execute(
        """
        SELECT is_banned
        FROM users
        WHERE telegram_id=?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return bool(row and row["is_banned"])


def record_watch(
    telegram_id: int,
    anime_id: int,
    episode_id: int
):
    conn = connect_db()

    conn.execute(
        """
        INSERT INTO watch_history (
            telegram_id,
            anime_id,
            episode_id,
            watched_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id, episode_id)
        DO UPDATE SET
            watched_at=excluded.watched_at
        """,
        (
            telegram_id,
            anime_id,
            episode_id,
            datetime.now(timezone.utc).isoformat()
        )
    )

    conn.execute(
        """
        UPDATE episodes
        SET view_count = COALESCE(view_count, 0) + 1
        WHERE id=?
        """,
        (episode_id,)
    )

    conn.execute(
        """
        UPDATE animes
        SET view_count = COALESCE(view_count, 0) + 1
        WHERE id=?
        """,
        (anime_id,)
    )

    conn.commit()
    conn.close()


def record_short_view(short_id: int):
    conn = connect_db()
    conn.execute(
        """
        UPDATE shorts
        SET view_count = COALESCE(view_count, 0) + 1
        WHERE id=?
        """,
        (short_id,)
    )
    conn.commit()
    conn.close()


def is_favorite(
    telegram_id: int,
    anime_id: int
) -> bool:

    conn = connect_db()

    row = conn.execute(
        """
        SELECT id
        FROM favorites
        WHERE telegram_id=?
        AND anime_id=?
        """,
        (telegram_id, anime_id)
    ).fetchone()

    conn.close()

    return bool(row)


def toggle_favorite(
    telegram_id: int,
    anime_id: int
) -> bool:

    conn = connect_db()

    row = conn.execute(
        """
        SELECT id
        FROM favorites
        WHERE telegram_id=?
        AND anime_id=?
        """,
        (telegram_id, anime_id)
    ).fetchone()

    if row:
        conn.execute(
            """
            DELETE FROM favorites
            WHERE telegram_id=?
            AND anime_id=?
            """,
            (telegram_id, anime_id)
        )
        result = False
    else:
        conn.execute(
            """
            INSERT INTO favorites (
                telegram_id,
                anime_id
            )
            VALUES (?, ?)
            """,
            (telegram_id, anime_id)
        )
        result = True

    conn.commit()
    conn.close()

    return result


async def notify_favorited_users(
    anime_id: int,
    anime_title: str,
    episode_number: int
):

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT telegram_id
        FROM favorites
        WHERE anime_id=?
        """,
        (anime_id,)
    ).fetchall()

    conn.close()

    for row in rows:

        user_id = row["telegram_id"]

        if user_is_banned(user_id):
            continue

        try:
            await bot.send_message(
                user_id,
                "🔔 <b>Yangi qism chiqdi!</b>\n\n"
                f"🎬 <b>{anime_title}</b>\n"
                f"📺 {episode_number}-qism\n\n"
                "Botga kirib tomosha qilishingiz mumkin."
            )
        except Exception as exc:
            print(
                f"⚠️ Notification failed for {user_id}: "
                f"{type(exc).__name__}: {exc}",
                flush=True
            )


# =========================================================
# MESSAGE ANIMATION HELPER
# =========================================================

async def delete_message_safe(
    chat_id: int,
    message_id: int
):

    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
    except Exception:
        pass


async def send_loading_messages(
    chat_id: int,
    loading_text: str,
    opening_text: str,
    delay: float = 0.35
):

    loading_message = await bot.send_message(
        chat_id,
        loading_text
    )

    await asyncio.sleep(delay)

    opening_message = await bot.send_message(
        chat_id,
        opening_text
    )

    await asyncio.sleep(delay)

    return loading_message, opening_message


# =========================================================
# SHORTS ENGINE
# =========================================================

async def send_short_video(
    chat_id: int,
    short_id: int
):

    conn = connect_db()

    shorts = conn.execute(
        """
        SELECT
            id,
            title,
            description,
            video_file_id,
            is_vip
        FROM shorts
        ORDER BY id ASC
        """
    ).fetchall()

    conn.close()

    if not shorts:
        return False

    current_index = -1

    for index, item in enumerate(shorts):

        if item["id"] == short_id:
            current_index = index
            break

    if current_index == -1:
        return False

    current = shorts[current_index]

    if current["is_vip"]:

        if not user_is_vip(chat_id):
            return "VIP"

    next_index = (
        current_index + 1
    ) % len(shorts)

    next_id = shorts[next_index]["id"]

    buttons = [
        [
            InlineKeyboardButton(
                text="➡️ Keyingi video",
                callback_data=f"shortnext_{next_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Bosh menyu",
                callback_data="user_home"
            )
        ]
    ]

    loading_message, opening_message = (
        await send_loading_messages(
            chat_id,
            "⏳ <b>Shorts tayyorlanmoqda...</b>",
            "🎬 <b>Shorts ochilmoqda...</b>"
        )
    )

    record_short_view(current["id"])

    try:

        video_message = await bot.send_video(
            chat_id=chat_id,
            video=current["video_file_id"],
            caption=(
                f"🎞 <b>{current['title']}</b>\n\n"
                f"{current['description']}\n\n"
                f"📱 Shorts "
                f"{current_index + 1}/{len(shorts)}"
            ),
            reply_markup=inline(buttons),
            protect_content=True
        )

    finally:

        await delete_message_safe(
            chat_id,
            loading_message.message_id
        )

        await delete_message_safe(
            chat_id,
            opening_message.message_id
        )

    return True


@dp.callback_query(
    F.data.startswith("shortnext_")
)
async def short_next_video(
    callback: CallbackQuery
):

    short_id_text = callback.data.replace(
        "shortnext_",
        "",
        1
    )

    if not short_id_text.isdigit():

        await callback.answer(
            "❌ Shorts ID noto‘g‘ri.",
            show_alert=True
        )

        return

    short_id = int(short_id_text)

    result = await send_short_video(
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
# STATES
# =========================================================

class AddAnime(StatesGroup):
    title = State()
    description = State()
    genre = State()
    poster = State()


class EditAnime(StatesGroup):
    anime_id = State()
    title = State()
    description = State()
    genre = State()
    poster = State()


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


class AnimeRequest(StatesGroup):
    title = State()


# =========================================================
# MENU ANIMATION
# =========================================================

async def animate_menu(
    message: Message,
    final_text: str,
    reply_markup=None,
    loading_text: str = "⏳ <b>Yuklanmoqda...</b>",
    opening_text: str = "🎬 <b>Menyu ochilmoqda...</b>",
):
    try:

        await message.edit_text(
            loading_text,
            reply_markup=None
        )

        await asyncio.sleep(0.35)

        await message.edit_text(
            opening_text,
            reply_markup=None
        )

        await asyncio.sleep(0.35)

        await message.edit_text(
            final_text,
            reply_markup=reply_markup
        )

    except Exception as e:

        print(
            f"⚠️ Menu animation error: {e}"
        )


async def ask_text(
    message: Message,
    text: str
):

    await message.answer(
        text,
        reply_markup=cancel_keyboard()
    )


# =========================================================
# KEYBOARDS
# =========================================================

def inline(rows):

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


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
        is_persistent=True
    )


def user_keyboard():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔎 ID qidirish"),
                KeyboardButton(text="🆕 Yangi")
            ],
            [
                KeyboardButton(text="🔥 Mashhur"),
                KeyboardButton(text="🏆 Top 10")
            ],
            [
                KeyboardButton(text="🎞 Shorts"),
                KeyboardButton(text="❤️ Sevimlilar")
            ],
            [
                KeyboardButton(text="🕘 Tarix")
            ],
            [
                KeyboardButton(text="📚 Janrlar"),
                KeyboardButton(text="⭐ VIP")
            ],
            [
                KeyboardButton(text="📩 Anime so‘rash"),
                KeyboardButton(text="📢 Reklama")
            ],
            [
                KeyboardButton(text="📩 Murojaat")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def admin_keyboard():

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
                KeyboardButton(text="📊 Statistika"),
                KeyboardButton(text="🏆 Top 10")
            ],
            [
                KeyboardButton(text="💾 Backup"),
                KeyboardButton(text="📈 Dashboard")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def anime_keyboard():

    return inline([
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

    return inline([
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
                callback_data="admin_episodes"
            )
        ]
    ])


def shorts_keyboard():

    return inline([
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
                callback_data="admin_shorts"
            )
        ]
    ])


def vip_keyboard():

    return inline([
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
                callback_data="admin_vip"
            )
        ]
    ])


def admin_inline():

    return inline([
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
            ),
            InlineKeyboardButton(
                text="🏆 Top 10",
                callback_data="admin_top10"
            )
        ],
        [
            InlineKeyboardButton(
                text="💾 Backup",
                callback_data="admin_backup"
            ),
            InlineKeyboardButton(
                text="📈 Dashboard",
                callback_data="admin_dashboard"
            )
        ]
    ])


# =========================================================
# STARTUP
# =========================================================

@dp.startup()
async def startup():

    print("🚀 Bot startup boshlandi...", flush=True)

    try:
        init_db()
        update_episode_vip_status()
    except Exception as e:
        print(
            f"❌ DATABASE STARTUP ERROR: {type(e).__name__}: {e}",
            flush=True
        )
        raise

    print("========================================", flush=True)
    print("🤖 ANIME BOT", flush=True)
    print("========================================", flush=True)
    print(f"✅ {len(ADMIN_IDS)} ta admin", flush=True)
    print("✅ Supabase PostgreSQL database", flush=True)
    print("✅ Anime", flush=True)
    print("✅ Qismlar", flush=True)
    print("✅ Shorts", flush=True)
    print("✅ VIP", flush=True)
    print("✅ Rassilka", flush=True)
    print("✅ Reklama", flush=True)
    print("✅ Client keyboard", flush=True)
    print("✅ Bekor qilish", flush=True)
    print("✅ 1-3 qism bepul", flush=True)
    print("✅ 4-qismdan VIP", flush=True)
    print("✅ Loading xabarlari avtomatik o‘chadi", flush=True)
    print("✅ Poster catalog + real views + Top 10", flush=True)
    print("✅ Automatic backup enabled", flush=True)
    asyncio.create_task(auto_backup_loop())
    print("🚀 Polling boshlanishiga tayyor", flush=True)
    print("========================================", flush=True)


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext
):

    register_user(
        message.from_user
    )

    if user_is_banned(message.from_user.id):
        await state.clear()
        await message.answer(
            "🚫 <b>SIZ BLOKLANGANSIZ</b>\n\n"
            "Botdan foydalanish huquqingiz vaqtincha cheklangan."
        )
        return

    await state.clear()

    command_parts = (message.text or "").split(maxsplit=1)

    if (
        len(command_parts) == 2
        and command_parts[1].startswith("anime_")
    ):
        anime_id_text = command_parts[1].replace("anime_", "", 1)

        if anime_id_text.isdigit():
            if await send_anime_card(
                message,
                int(anime_id_text)
            ):
                return

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "Pastki klaviaturadan kerakli bo‘limni tanlang.",
            reply_markup=admin_keyboard()
        )

    else:

        await message.answer(
            "🎬 <b>Anime Bot</b>\n\n"
            "Pastki klaviaturadan kerakli bo‘limni tanlang.",
            reply_markup=user_keyboard()
        )


# =========================================================
# CANCEL
# =========================================================

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_handler(
    message: Message,
    state: FSMContext
):

    await state.clear()

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "❌ <b>Amal bekor qilindi.</b>",
            reply_markup=admin_keyboard()
        )

    else:

        await message.answer(
            "❌ <b>Amal bekor qilindi.</b>",
            reply_markup=user_keyboard()
        )


@dp.message(F.text == "/cancel")
async def cancel_command(
    message: Message,
    state: FSMContext
):

    await cancel_handler(
        message,
        state
    )


# =========================================================
# ADMIN REPLY KEYBOARD
# =========================================================

@dp.message(F.text == "🎬 Anime")
async def admin_anime_reply(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    await state.clear()

    await message.answer(
        "🎬 <b>ANIME BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        reply_markup=anime_keyboard()
    )


@dp.message(F.text == "📺 Qismlar")
async def admin_episode_reply(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    await state.clear()

    await message.answer(
        "📺 <b>QISMLAR BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        reply_markup=episodes_keyboard()
    )


@dp.message(F.text == "⭐ VIP")
async def vip_reply(
    message: Message,
    state: FSMContext
):

    await state.clear()

    register_user(
        message.from_user
    )

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "⭐ <b>VIP BOSHQARUVI</b>\n\n"
            "Kerakli amalni tanlang:",
            reply_markup=vip_keyboard()
        )

        return

    if user_is_vip(
        message.from_user.id
    ):

        conn = connect_db()

        row = conn.execute(
            """
            SELECT vip_until
            FROM users
            WHERE telegram_id=?
            """,
            (message.from_user.id,)
        ).fetchone()

        conn.close()

        await message.answer(
            "⭐ <b>SIZ VIPSIZ!</b>\n\n"
            f"⏳ Muddati:\n"
            f"<code>{row['vip_until'] if row else '-'}</code>",
            reply_markup=user_keyboard()
        )

        return

    await message.answer(
        "⭐ <b>VIP OLISH</b>\n\n"
        "4-qismdan boshlab premium qismlarni ko‘rish "
        "uchun VIP kerak.\n\n"
        "VIP olish uchun admin bilan bog‘laning:\n"
        "👤 <b>@Ichi1010</b>",
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="⭐ VIP olish",
                    url="https://t.me/Ichi1010"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Bosh menyu",
                    callback_data="user_home"
                )
            ]
        ])
    )


@dp.message(F.text == "📢 Rassilka")
async def broadcast_reply(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    await state.clear()

    await state.set_state(
        Broadcast.message
    )

    await message.answer(
        "📢 <b>RASSILKA</b>\n\n"
        "Barcha foydalanuvchilarga yuboriladigan "
        "xabarni yuboring.",
        reply_markup=cancel_keyboard()
    )


@dp.message(F.text == "👥 Foydalanuvchilar")
async def users_reply(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    await state.clear()

    conn = connect_db()

    rows = conn.execute(
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

    conn.close()

    text = "👥 <b>FOYDALANUVCHILAR</b>\n\n"

    if not rows:

        text += "Hozircha foydalanuvchi yo‘q."

    else:

        for row in rows:

            vip = (
                " ⭐ VIP"
                if row["is_vip"]
                else ""
            )

            text += (
                f"🆔 <code>{row['telegram_id']}</code>\n"
                f"📛 {row['full_name'] or '-'}{vip}\n\n"
            )

    await message.answer(
        text,
        reply_markup=admin_keyboard()
    )


@dp.message(F.text == "📊 Statistika")
async def stats_reply(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    await state.clear()

    conn = connect_db()

    users = conn.execute(
        "SELECT COUNT(*) c FROM users"
    ).fetchone()["c"]

    anime = conn.execute(
        "SELECT COUNT(*) c FROM animes"
    ).fetchone()["c"]

    episodes = conn.execute(
        "SELECT COUNT(*) c FROM episodes"
    ).fetchone()["c"]

    shorts = conn.execute(
        "SELECT COUNT(*) c FROM shorts"
    ).fetchone()["c"]

    vip = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE is_vip=1"
    ).fetchone()["c"]

    vip_episodes = conn.execute(
        "SELECT COUNT(*) c FROM episodes WHERE is_vip=1"
    ).fetchone()["c"]

    conn.close()

    await message.answer(
        "📊 <b>STATISTIKA</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users}</b>\n"
        f"🎬 Anime: <b>{anime}</b>\n"
        f"📺 Qismlar: <b>{episodes}</b>\n"
        f"🔒 VIP qismlar: <b>{vip_episodes}</b>\n"
        f"🎞 Shorts: <b>{shorts}</b>\n"
        f"⭐ VIP foydalanuvchilar: <b>{vip}</b>",
        reply_markup=admin_keyboard()
    )


# =========================================================
# CLIENT ID SEARCH
# =========================================================

@dp.message(F.text == "🔎 ID qidirish")
async def id_search_button(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "🔎 <b>ID QIDIRISH</b>\n\n"
        "Anime yoki qism ID raqamini yuboring.\n\n"
        "Masalan: <code>1</code>",
        reply_markup=user_keyboard()
    )


# =========================================================
# ADVERTISEMENT
# =========================================================

@dp.message(F.text == "📢 Reklama")
async def advertising_button(
    message: Message,
    state: FSMContext
):

    if is_admin(
        message.from_user.id
    ):

        await broadcast_reply(
            message,
            state
        )

        return

    await state.clear()

    await message.answer(
        "📢 <b>REKLAMA / HAMKORLIK</b>\n\n"
        "Reklama uchun quyidagi kontaktlardan biriga yozing:",
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="📢 @arata_2915",
                    url="https://t.me/arata_2915"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 @Ichi1010",
                    url="https://t.me/Ichi1010"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Bosh menyu",
                    callback_data="user_home"
                )
            ]
        ])
    )


# =========================================================
# CONTACT
# =========================================================

@dp.message(F.text == "📩 Murojaat")
async def contact_button(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "📩 <b>MUROJAAT</b>\n\n"
        "Admin bilan bog‘lanish:\n\n"
        "👤 <b>@Ichi1010</b>",
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="📩 Bog‘lanish",
                    url="https://t.me/Ichi1010"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Bosh menyu",
                    callback_data="user_home"
                )
            ]
        ])
    )


# =========================================================
# ADMIN INLINE MAIN
# =========================================================

@dp.callback_query(F.data == "admin_back")
async def admin_back(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await animate_menu(
        callback.message,
        "👑 <b>ADMIN PANEL</b>\n\n"
        "Kerakli bo‘limni tanlang:",
        admin_inline(),
        "⏳ <b>Admin panel tayyorlanmoqda...</b>",
        "🎬 <b>Admin panel ochilmoqda...</b>"
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_anime")
async def admin_anime(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await animate_menu(
        callback.message,
        "🎬 <b>ANIME BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        anime_keyboard(),
        "⏳ <b>Anime bo‘limi yuklanmoqda...</b>",
        "🎬 <b>Anime bo‘limi ochilmoqda...</b>"
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_episodes")
async def admin_episodes(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await animate_menu(
        callback.message,
        "📺 <b>QISMLAR BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        episodes_keyboard(),
        "⏳ <b>Qismlar yuklanmoqda...</b>",
        "📺 <b>Qismlar bo‘limi ochilmoqda...</b>"
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_shorts")
async def admin_shorts(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await animate_menu(
        callback.message,
        "🎞 <b>SHORTS BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        shorts_keyboard(),
        "⏳ <b>Shorts yuklanmoqda...</b>",
        "🎞 <b>Shorts bo‘limi ochilmoqda...</b>"
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_vip")
async def admin_vip(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await animate_menu(
        callback.message,
        "⭐ <b>VIP BOSHQARUVI</b>\n\n"
        "Kerakli amalni tanlang:",
        vip_keyboard(),
        "⏳ <b>VIP bo‘limi yuklanmoqda...</b>",
        "⭐ <b>VIP bo‘limi ochilmoqda...</b>"
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

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await state.set_state(
        AddAnime.title
    )

    await callback.message.edit_text(
        "➕ <b>ANIME QO‘SHISH</b>\n\n"
        "1️⃣ Anime nomini yuboring."
    )

    await callback.message.answer(
        "❌ Bekor qilish tugmasi mavjud.",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(AddAnime.title)
async def anime_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    title = (
        message.text or ""
    ).strip()

    if not title:

        await ask_text(
            message,
            "❌ Anime nomini kiriting."
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddAnime.description
    )

    await ask_text(
        message,
        "2️⃣ Anime tavsifini yuboring."
    )


@dp.message(AddAnime.description)
async def anime_description(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    description = (message.text or "").strip()
    if not description:
        await ask_text(message, "❌ Tavsifni kiriting.")
        return

    await state.update_data(description=description)
    await state.set_state(AddAnime.genre)

    await ask_text(
        message,
        "3️⃣ Janrlarni kiriting.\n\n"
        "Masalan: <code>Action, Fantasy, Comedy</code>\n"
        "Kerak bo‘lmasa: <code>-</code>"
    )


@dp.message(AddAnime.genre)
async def anime_genre(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    genre = (message.text or "").strip()
    if genre == "-":
        genre = ""

    data = await state.get_data()
    if "title" not in data or "description" not in data:
        await state.clear()
        await message.answer(
            "❌ Anime ma'lumotlari topilmadi.",
            reply_markup=admin_keyboard()
        )
        return

    await state.update_data(genre=genre)
    await state.set_state(AddAnime.poster)

    await ask_text(
        message,
        "4️⃣ Anime posterini yuboring.\n\n"
        "🖼 Rasm yuboring yoki kerak bo‘lmasa <code>-</code> yozing."
    )


@dp.message(AddAnime.poster)
async def anime_poster(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.photo:
        poster_file_id = message.photo[-1].file_id
    elif (message.text or "").strip() == "-":
        poster_file_id = ""
    else:
        await ask_text(message, "❌ Rasm yuboring yoki <code>-</code> yozing.")
        return

    data = await state.get_data()
    if "title" not in data or "description" not in data or "genre" not in data:
        await state.clear()
        await message.answer(
            "❌ Anime ma'lumotlari topilmadi.",
            reply_markup=admin_keyboard()
        )
        return

    conn = connect_db()
    cursor = conn.execute(
        """
        INSERT INTO animes (
            title,
            description,
            genre,
            poster_file_id
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            data["title"],
            data["description"],
            data["genre"],
            poster_file_id
        )
    )
    anime_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ <b>ANIME SAQLANDI</b>\n\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎬 {data['title']}\n"
        f"🎭 {data['genre'] or 'Noma‘lum'}\n"
        f"🖼 Poster: {'✅' if poster_file_id else '➖'}",
        reply_markup=anime_keyboard()
    )


# =========================================================
# ANIME LIST
# =========================================================

@dp.callback_query(F.data == "anime_list")
async def anime_list(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title, description
        FROM animes
        WHERE is_active=1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    text = (
        "📋 <b>ANIME RO‘YXATI</b>\n\n"
    )

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
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="⬅️ Anime",
                    callback_data="admin_anime"
                )
            ]
        ])
    )

    await callback.answer()


# =========================================================
# ANIME EDIT
# =========================================================

@dp.callback_query(F.data == "anime_edit")
async def anime_edit(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active=1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("anime_edit_"))
async def anime_edit_select(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo‘q!", show_alert=True)
        return

    anime_id = int(callback.data.rsplit("_", 1)[1])

    conn = connect_db()
    row = conn.execute(
        """
        SELECT title, description, genre, poster_file_id
        FROM animes
        WHERE id=?
        """,
        (anime_id,)
    ).fetchone()
    conn.close()

    if not row:
        await callback.answer("❌ Anime topilmadi.", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        anime_id=anime_id,
        old_poster_file_id=row["poster_file_id"] or ""
    )
    await state.set_state(EditAnime.title)

    await callback.message.edit_text(
        f"✏️ Hozirgi nom: <b>{row['title']}</b>\n\n"
        "Yangi nomni yuboring:"
    )
    await callback.message.answer(
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()


@dp.message(EditAnime.title)
async def edit_anime_title(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()
    if not title:
        await ask_text(message, "❌ Nom kiriting.")
        return

    await state.update_data(title=title)
    await state.set_state(EditAnime.description)
    await ask_text(message, "Yangi tavsifni yuboring.")


@dp.message(EditAnime.description)
async def edit_anime_description(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    description = (message.text or "").strip()
    if not description:
        await ask_text(message, "❌ Tavsif kiriting.")
        return

    await state.update_data(description=description)
    await state.set_state(EditAnime.genre)

    await ask_text(
        message,
        "Yangi janrni yuboring.\n"
        "Janrni o‘chirish uchun <code>-</code>."
    )


@dp.message(EditAnime.genre)
async def edit_anime_genre(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    genre = (message.text or "").strip()
    if genre == "-":
        genre = ""

    await state.update_data(genre=genre)
    await state.set_state(EditAnime.poster)

    await ask_text(
        message,
        "Yangi poster rasm yuboring.\n"
        "Eski posterni saqlash uchun <code>-</code>, olib tashlash uchun <code>0</code>."
    )


@dp.message(EditAnime.poster)
async def edit_anime_poster(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    if "anime_id" not in data or "title" not in data or "description" not in data or "genre" not in data:
        await state.clear()
        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )
        return

    old_poster = data.get("old_poster_file_id", "")

    if message.photo:
        poster_file_id = message.photo[-1].file_id
    elif (message.text or "").strip() == "-":
        poster_file_id = old_poster
    elif (message.text or "").strip() == "0":
        poster_file_id = ""
    else:
        await ask_text(
            message,
            "❌ Rasm yuboring, <code>-</code> yoki <code>0</code> yozing."
        )
        return

    conn = connect_db()
    conn.execute(
        """
        UPDATE animes
        SET title=?,
            description=?,
            genre=?,
            poster_file_id=?
        WHERE id=?
        """,
        (
            data["title"],
            data["description"],
            data["genre"],
            poster_file_id,
            data["anime_id"]
        )
    )
    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ <b>ANIME YANGILANDI</b>\n\n"
        f"🆔 ID: <code>{data['anime_id']}</code>\n"
        f"🎬 {data['title']}\n"
        f"🎭 {data['genre'] or 'Noma‘lum'}\n"
        f"🖼 Poster: {'✅' if poster_file_id else '➖'}",
        reply_markup=anime_keyboard()
    )


# =========================================================
# ANIME DELETE
# =========================================================

@dp.callback_query(F.data == "anime_delete")
async def anime_delete(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active=1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

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
                callback_data=f"anime_del_{row['id']}"
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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^anime_del_\d+$")
)
async def anime_delete_confirm(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    row = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE id=?
        AND is_active=1
        """,
        (anime_id,)
    ).fetchone()

    conn.close()

    if not row:

        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )

        return

    await callback.message.edit_text(
        f"⚠️ <b>{row['title']}</b>\n\n"
        "Bu animega tegishli barcha qismlar ham o‘chiriladi.\n\n"
        "Haqiqatan ham o‘chirmoqchimisiz?",
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="✅ Ha",
                    callback_data=f"anime_del_yes_{anime_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Yo‘q",
                    callback_data="anime_delete"
                )
            ]
        ])
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("anime_del_yes_")
)
async def anime_delete_yes(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    anime = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE id=?
        """,
        (anime_id,)
    ).fetchone()

    if not anime:

        conn.close()

        await callback.answer(
            "❌ Anime allaqachon o‘chirilgan.",
            show_alert=True
        )

        return

    conn.execute(
        """
        DELETE FROM episodes
        WHERE anime_id=?
        """,
        (anime_id,)
    )

    conn.execute(
        """
        DELETE FROM animes
        WHERE id=?
        """,
        (anime_id,)
    )

    conn.commit()
    conn.close()

    await callback.answer(
        "✅ O‘chirildi!"
    )

    await callback.message.edit_text(
        f"✅ <b>{anime['title']}</b> o‘chirildi!\n\n"
        "🗑 Anime va unga tegishli barcha qismlar ham o‘chirildi.",
        reply_markup=anime_keyboard()
    )


# =========================================================
# EPISODE ADD
# =========================================================

@dp.callback_query(F.data == "episode_add")
async def episode_add(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active=1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

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
                callback_data=f"episode_choose_{row['id']}"
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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("episode_choose_")
)
async def episode_choose(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    row = conn.execute(
        """
        SELECT title
        FROM animes
        WHERE id=?
        """,
        (anime_id,)
    ).fetchone()

    conn.close()

    if not row:

        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )

        return

    await state.clear()

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

    await callback.message.answer(
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(AddEpisode.number)
async def episode_number(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    value = (
        message.text or ""
    ).strip()

    if (
        not value.isdigit()
        or int(value) < 1
    ):

        await ask_text(
            message,
            "❌ Masalan: <code>1</code>"
        )

        return

    await state.update_data(
        number=int(value)
    )

    await state.set_state(
        AddEpisode.title
    )

    await ask_text(
        message,
        "2️⃣ Qism nomini yuboring."
    )


@dp.message(AddEpisode.title)
async def episode_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    title = (
        message.text or ""
    ).strip()

    if not title:

        await ask_text(
            message,
            "❌ Qism nomini kiriting."
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddEpisode.video
    )

    await ask_text(
        message,
        "3️⃣ Qism videosini yuboring 🎥"
    )


@dp.message(
    AddEpisode.video,
    F.video
)
async def episode_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    data = await state.get_data()

    required = (
        "anime_id",
        "anime_title",
        "number",
        "title"
    )

    if any(
        key not in data
        for key in required
    ):

        await state.clear()

        await message.answer(
            "❌ Qism jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    conn = connect_db()

    existing_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM episodes
        WHERE anime_id=?
        """,
        (data["anime_id"],)
    ).fetchone()["count"]

    is_vip = (
        1
        if existing_count >= 3
        else 0
    )

    cursor = conn.execute(
        """
        INSERT INTO episodes (
            anime_id,
            episode_number,
            title,
            video_file_id,
            is_vip
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            data["anime_id"],
            data["number"],
            data["title"],
            message.video.file_id,
            is_vip
        )
    )

    episode_id = cursor.lastrowid

    conn.commit()
    conn.close()

    update_episode_vip_status()

    asyncio.create_task(
        notify_favorited_users(
            data["anime_id"],
            data["anime_title"],
            data["number"]
        )
    )

    await state.clear()

    vip_text = (
        "🔒 VIP qism"
        if is_vip
        else "✅ Bepul qism"
    )

    await message.answer(
        "✅ <b>QISM SAQLANDI</b>\n\n"
        f"🆔 ID: <code>{episode_id}</code>\n"
        f"🎬 {data['anime_title']}\n"
        f"📺 {data['number']}-qism\n"
        f"📝 {data['title']}\n"
        f"⭐ Holati: <b>{vip_text}</b>",
        reply_markup=episodes_keyboard()
    )


@dp.message(AddEpisode.video)
async def episode_video_wrong(
    message: Message
):

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "❌ Videoni video qilib yuboring 🎥"
        )


# =========================================================
# EPISODE LIST
# =========================================================

@dp.callback_query(F.data == "episode_list")
async def episode_list(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            e.title,
            e.is_vip,
            a.title AS anime
        FROM episodes e
        JOIN animes a
        ON a.id=e.anime_id
        ORDER BY e.id DESC
        """
    ).fetchall()

    conn.close()

    text = (
        "📋 <b>QISMLAR RO‘YXATI</b>\n\n"
    )

    if not rows:

        text += "Hozircha qism yo‘q."

    else:

        for row in rows:

            status = (
                "🔒 VIP"
                if row["is_vip"]
                else "✅ Bepul"
            )

            text += (
                f"🆔 <code>{row['id']}</code>\n"
                f"🎬 {row['anime']}\n"
                f"📺 {row['episode_number']}-qism — "
                f"{row['title']}\n"
                f"⭐ Holati: {status}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="⬅️ Qismlar",
                    callback_data="admin_episodes"
                )
            ]
        ])
    )

    await callback.answer()


# =========================================================
# EPISODE EDIT
# =========================================================

@dp.callback_query(F.data == "episode_edit")
async def episode_edit(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
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

    conn.close()

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
                text=(
                    f"✏️ {row['anime']} — "
                    f"{row['episode_number']}-qism"
                ),
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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("episode_edit_")
)
async def episode_edit_select(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    row = conn.execute(
        """
        SELECT title
        FROM episodes
        WHERE id=?
        """,
        (episode_id,)
    ).fetchone()

    conn.close()

    if not row:

        await callback.answer(
            "❌ Qism topilmadi.",
            show_alert=True
        )

        return

    await state.clear()

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
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(EditEpisode.title)
async def edit_episode_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    title = (
        message.text or ""
    ).strip()

    if not title:

        await ask_text(
            message,
            "❌ Nom kiriting."
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        EditEpisode.video
    )

    await ask_text(
        message,
        "Yangi video yuboring yoki "
        "<code>skip</code> yozing."
    )


@dp.message(
    EditEpisode.video,
    F.video
)
async def edit_episode_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    data = await state.get_data()

    if (
        "episode_id" not in data
        or "title" not in data
    ):

        await state.clear()

        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    conn = connect_db()

    conn.execute(
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

    conn.commit()
    conn.close()

    update_episode_vip_status()

    await state.clear()

    await message.answer(
        "✅ Qism yangilandi.",
        reply_markup=episodes_keyboard()
    )


@dp.message(EditEpisode.video)
async def edit_episode_video_skip(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    if (
        message.text or ""
    ).strip().lower() != "skip":

        await message.answer(
            "❌ Video yuboring yoki "
            "<code>skip</code> yozing."
        )

        return

    data = await state.get_data()

    if (
        "episode_id" not in data
        or "title" not in data
    ):

        await state.clear()

        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    conn = connect_db()

    conn.execute(
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

    conn.commit()
    conn.close()

    update_episode_vip_status()

    await state.clear()

    await message.answer(
        "✅ Qism nomi yangilandi.",
        reply_markup=episodes_keyboard()
    )


# =========================================================
# EPISODE DELETE
# =========================================================

@dp.callback_query(F.data == "episode_delete")
async def episode_delete(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
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

    conn.close()

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
                text=(
                    f"🗑 {row['anime']} — "
                    f"{row['episode_number']}-qism"
                ),
                callback_data=f"episode_del_{row['id']}"
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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^episode_del_\d+$")
)
async def episode_delete_confirm(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    await callback.message.edit_text(
        "⚠️ Qismni o‘chirishni tasdiqlaysizmi?",
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="✅ Ha",
                    callback_data=f"episode_del_yes_{episode_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Yo‘q",
                    callback_data="episode_delete"
                )
            ]
        ])
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("episode_del_yes_")
)
async def episode_delete_yes(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    episode = conn.execute(
        """
        SELECT anime_id
        FROM episodes
        WHERE id=?
        """,
        (episode_id,)
    ).fetchone()

    conn.execute(
        """
        DELETE FROM episodes
        WHERE id=?
        """,
        (episode_id,)
    )

    conn.commit()
    conn.close()

    if episode:

        update_episode_vip_status()

    await callback.message.edit_text(
        "✅ Qism o‘chirildi.",
        reply_markup=episodes_keyboard()
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

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await state.set_state(
        AddShort.title
    )

    await callback.message.edit_text(
        "➕ <b>SHORTS QO‘SHISH</b>\n\n"
        "1️⃣ Shorts nomini yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(AddShort.title)
async def short_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    title = (
        message.text or ""
    ).strip()

    if not title:

        await ask_text(
            message,
            "❌ Shorts nomini kiriting."
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddShort.description
    )

    await ask_text(
        message,
        "2️⃣ Shorts tavsifini yuboring."
    )


@dp.message(AddShort.description)
async def short_description(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    description = (
        message.text or ""
    ).strip()

    if not description:

        await ask_text(
            message,
            "❌ Shorts tavsifini kiriting."
        )

        return

    data = await state.get_data()

    if "title" not in data:

        await state.clear()

        await message.answer(
            "❌ Shorts jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    await state.update_data(
        description=description
    )

    await state.set_state(
        AddShort.video
    )

    await ask_text(
        message,
        "3️⃣ Shorts videosini yuboring 🎥"
    )


@dp.message(
    AddShort.video,
    F.video
)
async def short_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    data = await state.get_data()

    if (
        "title" not in data
        or "description" not in data
    ):

        await state.clear()

        await message.answer(
            "❌ Shorts ma'lumotlari yo‘qolgan.",
            reply_markup=admin_keyboard()
        )

        return

    conn = connect_db()

    cursor = conn.execute(
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

    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ <b>SHORTS SAQLANDI</b>\n\n"
        f"🆔 ID: <code>{short_id}</code>\n"
        f"🎞 {data['title']}\n"
        f"📝 {data['description']}",
        reply_markup=shorts_keyboard()
    )


@dp.message(AddShort.video)
async def short_video_wrong(
    message: Message
):

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "❌ Shorts videosini video qilib yuboring 🎥"
        )


# =========================================================
# SHORT LIST
# =========================================================

@dp.callback_query(F.data == "short_list")
async def short_list(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT
            id,
            title,
            description,
            is_vip
        FROM shorts
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    text = (
        "📋 <b>SHORTS RO‘YXATI</b>\n\n"
    )

    if not rows:

        text += "Hozircha Shorts yo‘q."

    else:

        for row in rows:

            status = (
                "🔒 VIP"
                if row["is_vip"]
                else "✅ Bepul"
            )

            text += (
                f"🆔 <code>{row['id']}</code>\n"
                f"🎞 <b>{row['title']}</b>\n"
                f"📝 {row['description']}\n"
                f"⭐ Holati: {status}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="⬅️ Shorts",
                    callback_data="admin_shorts"
                )
            ]
        ])
    )

    await callback.answer()


# =========================================================
# SHORT EDIT
# =========================================================

@dp.callback_query(F.data == "short_edit")
async def short_edit(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM shorts
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("short_edit_")
)
async def short_edit_select(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    row = conn.execute(
        """
        SELECT title
        FROM shorts
        WHERE id=?
        """,
        (short_id,)
    ).fetchone()

    conn.close()

    if not row:

        await callback.answer(
            "❌ Shorts topilmadi.",
            show_alert=True
        )

        return

    await state.clear()

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
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(EditShort.title)
async def edit_short_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    title = (
        message.text or ""
    ).strip()

    if not title:

        await ask_text(
            message,
            "❌ Nom kiriting."
        )

        return

    data = await state.get_data()

    if "short_id" not in data:

        await state.clear()

        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        EditShort.description
    )

    await ask_text(
        message,
        "Yangi tavsifni yuboring."
    )


@dp.message(EditShort.description)
async def edit_short_description(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    description = (
        message.text or ""
    ).strip()

    if not description:

        await ask_text(
            message,
            "❌ Tavsif kiriting."
        )

        return

    data = await state.get_data()

    if (
        "short_id" not in data
        or "title" not in data
    ):

        await state.clear()

        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    await state.update_data(
        description=description
    )

    await state.set_state(
        EditShort.video
    )

    await ask_text(
        message,
        "Yangi video yuboring yoki "
        "<code>skip</code> yozing."
    )


@dp.message(
    EditShort.video,
    F.video
)
async def edit_short_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    data = await state.get_data()

    if any(
        key not in data
        for key in (
            "short_id",
            "title",
            "description"
        )
    ):

        await state.clear()

        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    conn = connect_db()

    conn.execute(
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

    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ Shorts yangilandi.",
        reply_markup=shorts_keyboard()
    )


@dp.message(EditShort.video)
async def edit_short_video_skip(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    if (
        message.text or ""
    ).strip().lower() != "skip":

        await message.answer(
            "❌ Video yuboring yoki "
            "<code>skip</code> yozing."
        )

        return

    data = await state.get_data()

    if any(
        key not in data
        for key in (
            "short_id",
            "title",
            "description"
        )
    ):

        await state.clear()

        await message.answer(
            "❌ Tahrirlash jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    conn = connect_db()

    conn.execute(
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

    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ Shorts ma’lumotlari yangilandi.",
        reply_markup=shorts_keyboard()
    )


# =========================================================
# SHORT DELETE
# =========================================================

@dp.callback_query(F.data == "short_delete")
async def short_delete(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM shorts
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

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
                callback_data=f"short_del_{row['id']}"
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
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^short_del_\d+$")
)
async def short_delete_confirm(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    await callback.message.edit_text(
        "⚠️ Shortsni o‘chirishni tasdiqlaysizmi?",
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="✅ Ha",
                    callback_data=f"short_del_yes_{short_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Yo‘q",
                    callback_data="short_delete"
                )
            ]
        ])
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("short_del_yes_")
)
async def short_delete_yes(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    conn.execute(
        """
        DELETE FROM shorts
        WHERE id=?
        """,
        (short_id,)
    )

    conn.commit()
    conn.close()

    await callback.message.edit_text(
        "✅ Shorts o‘chirildi.",
        reply_markup=shorts_keyboard()
    )

    await callback.answer()


# =========================================================
# VIP
# =========================================================

@dp.callback_query(F.data == "vip_add")
async def vip_add(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await state.set_state(
        VipAdd.user_id
    )

    await callback.message.edit_text(
        "⭐ <b>VIP BERISH</b>\n\n"
        "Foydalanuvchining Telegram ID raqamini yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(VipAdd.user_id)
async def vip_user_id(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    value = (
        message.text or ""
    ).strip()

    if not value.isdigit():

        await ask_text(
            message,
            "❌ ID faqat raqam bo‘lsin."
        )

        return

    await state.update_data(
        user_id=int(value)
    )

    await state.set_state(
        VipAdd.days
    )

    await ask_text(
        message,
        "Necha kunlik VIP?\n\n"
        "Masalan: <code>30</code>"
    )


@dp.message(VipAdd.days)
async def vip_days(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    value = (
        message.text or ""
    ).strip()

    if (
        not value.isdigit()
        or int(value) < 1
    ):

        await ask_text(
            message,
            "❌ Kun sonini kiriting."
        )

        return

    days = int(value)

    data = await state.get_data()

    if "user_id" not in data:

        await state.clear()

        await message.answer(
            "❌ VIP jarayoni buzilgan.",
            reply_markup=admin_keyboard()
        )

        return

    expiry = (
        datetime.now(timezone.utc)
        + timedelta(days=days)
    ).isoformat()

    conn = connect_db()

    conn.execute(
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
            expiry
        )
    )

    conn.commit()
    conn.close()

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

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    await state.clear()

    await state.set_state(
        VipRemove.user_id
    )

    await callback.message.edit_text(
        "❌ <b>VIPNI OLIB TASHLASH</b>\n\n"
        "Telegram ID raqamini yuboring:"
    )

    await callback.message.answer(
        "❌ Bekor qilish",
        reply_markup=cancel_keyboard()
    )

    await callback.answer()


@dp.message(VipRemove.user_id)
async def vip_remove_user(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    value = (
        message.text or ""
    ).strip()

    if not value.isdigit():

        await ask_text(
            message,
            "❌ ID faqat raqam bo‘lsin."
        )

        return

    conn = connect_db()

    conn.execute(
        """
        UPDATE users
        SET is_vip=0,
            vip_until=NULL
        WHERE telegram_id=?
        """,
        (int(value),)
    )

    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ VIP olib tashlandi.",
        reply_markup=vip_keyboard()
    )


@dp.callback_query(F.data == "vip_list")
async def vip_list(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )

        return

    conn = connect_db()

    rows = conn.execute(
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

    conn.close()

    text = (
        "⭐ <b>VIP RO‘YXATI</b>\n\n"
    )

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
        reply_markup=inline([
            [
                InlineKeyboardButton(
                    text="⬅️ VIP",
                    callback_data="admin_vip"
                )
            ]
        ])
    )

    await callback.answer()


# =========================================================
# BROADCAST
# =========================================================

@dp.message(Broadcast.message)
async def broadcast_message(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()

        return

    conn = connect_db()

    users = conn.execute(
        """
        SELECT telegram_id
        FROM users
        """
    ).fetchall()

    conn.close()

    sent = 0
    failed = 0

    for row in users:

        try:

            await bot.copy_message(
                chat_id=row["telegram_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            sent += 1

        except Exception:

            failed += 1

        await asyncio.sleep(
            0.04
        )

    conn = connect_db()

    conn.execute(
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

    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ <b>RASSILKA YAKUNLANDI</b>\n\n"
        f"✅ Yuborildi: <b>{sent}</b>\n"
        f"❌ Xatolik: <b>{failed}</b>",
        reply_markup=admin_keyboard()
    )


# =========================================================
# USER HOME
# =========================================================

@dp.callback_query(F.data == "user_home")
async def user_home(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await animate_menu(
        callback.message,
        "🎬 <b>ANIME BOT</b>\n\n"
        "Bosh menyu ochildi.\n"
        "Pastki klaviaturadan bo‘lim tanlang.",
        None,
        "⏳ <b>Bosh menyu yuklanmoqda...</b>",
        "🎬 <b>Bosh menyu ochilmoqda...</b>"
    )

    await callback.message.answer(
        "🏠 <b>Bosh menyu</b>",
        reply_markup=user_keyboard()
    )

    await callback.answer()


# =========================================================
# SHORTS USER / ADMIN
# =========================================================

@dp.message(F.text == "🎞 Shorts")
async def shorts_main_button(
    message: Message,
    state: FSMContext
):

    await state.clear()

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "🎞 <b>SHORTS BOSHQARUVI</b>\n\n"
            "Kerakli amalni tanlang:",
            reply_markup=shorts_keyboard()
        )

        return

    register_user(
        message.from_user
    )

    conn = connect_db()

    first = conn.execute(
        """
        SELECT id
        FROM shorts
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    if not first:

        await message.answer(
            "🎞 <b>SHORTS</b>\n\n"
            "Hozircha Shorts mavjud emas.",
            reply_markup=user_keyboard()
        )

        return

    result = await send_short_video(
        message.from_user.id,
        first["id"]
    )

    if result == "VIP":

        await message.answer(
            "⭐ Bu Shorts faqat VIP uchun.",
            reply_markup=user_keyboard()
        )


# =========================================================
# USER DISCOVERY / FAVORITES / HISTORY / REQUESTS
# =========================================================

async def send_anime_card(
    message: Message,
    anime_id: int
) -> bool:

    conn = connect_db()

    anime = conn.execute(
        """
        SELECT id, title, description, genre, poster_file_id, view_count
        FROM animes
        WHERE id=?
        AND is_active=1
        """,
        (anime_id,)
    ).fetchone()

    if not anime:
        conn.close()
        return False

    episodes = conn.execute(
        """
        SELECT id, episode_number, title, is_vip, view_count
        FROM episodes
        WHERE anime_id=?
        ORDER BY episode_number ASC, id ASC
        """,
        (anime_id,)
    ).fetchall()

    conn.close()

    buttons = []

    for ep in episodes:
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"🔒 {ep['episode_number']}-qism ⭐ VIP"
                    if ep["is_vip"]
                    else f"▶️ {ep['episode_number']}-qism"
                ),
                callback_data=f"user_episode_{ep['id']}"
            )
        ])

    favorite = is_favorite(
        message.from_user.id,
        anime_id
    )

    buttons.append([
        InlineKeyboardButton(
            text=(
                "💔 Sevimlilardan olib tashlash"
                if favorite
                else "❤️ Sevimlilarga qo‘shish"
            ),
            callback_data=f"favorite_toggle_{anime_id}"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    description = anime["description"] or "-"
    if len(description) > 700:
        description = description[:697] + "..."

    caption = (
        f"🎬 <b>{anime['title']}</b>\n"
        f"🎭 Janr: <b>{anime['genre'] or 'Noma‘lum'}</b>\n"
        f"👁 Ko‘rishlar: <b>{anime['view_count'] or 0}</b>\n"
        f"📺 Qismlar: <b>{len(episodes)}</b>\n\n"
        f"📝 {description}"
    )

    if anime["poster_file_id"]:
        await message.answer_photo(
            anime["poster_file_id"],
            caption=caption,
            reply_markup=inline(buttons)
        )
    else:
        await message.answer(
            caption,
            reply_markup=inline(buttons)
        )

    return True


@dp.message(F.text == "🆕 Yangi")
async def new_anime_button(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    register_user(message.from_user)

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active=1
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    conn.close()

    if not rows:
        await message.answer(
            "🆕 <b>YANGI ANIMELAR</b>\n\nHozircha anime yo‘q.",
            reply_markup=user_keyboard()
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🎬 {row['title'][:45]}",
                callback_data=f"open_anime_{row['id']}"
            )
        ]
        for row in rows
    ]

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await message.answer(
        "🆕 <b>YANGI ANIMELAR</b>\n\n"
        "Eng so‘nggi qo‘shilganlar:",
        reply_markup=inline(buttons)
    )


@dp.message(F.text == "🔥 Mashhur")
async def popular_anime_button(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    register_user(message.from_user)

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT
            a.id,
            a.title,
            COALESCE(a.view_count, 0) AS views
        FROM animes a
        WHERE a.is_active=1
        ORDER BY a.view_count DESC, a.id DESC
        LIMIT 15
        """
    ).fetchall()

    conn.close()

    buttons = []

    for row in rows:
        buttons.append([
            InlineKeyboardButton(
                text=f"🔥 {row['title'][:38]} · {row['views']}",
                callback_data=f"open_anime_{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await message.answer(
        "🔥 <b>MASHHUR ANIMELAR</b>\n\n"
        "Ko‘rishlar asosida:",
        reply_markup=inline(buttons)
    )


@dp.message(F.text == "🏆 Top 10")
async def top10_user_button(
    message: Message,
    state: FSMContext
):
    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    register_user(message.from_user)

    conn = connect_db()
    rows = conn.execute(
        """
        SELECT id, title, view_count
        FROM animes
        WHERE is_active=1
        ORDER BY view_count DESC, id DESC
        LIMIT 10
        """
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer(
            "🏆 <b>TOP 10</b>\n\nHozircha anime yo‘q.",
            reply_markup=user_keyboard()
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🏆 {index}. {row['title'][:35]} · 👁 {row['view_count'] or 0}",
                callback_data=f"open_anime_{row['id']}"
            )
        ]
        for index, row in enumerate(rows, start=1)
    ]
    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await message.answer(
        "🏆 <b>TOP 10 ANIMELAR</b>\n\n"
        "Haqiqiy video yuborishlar asosida:",
        reply_markup=inline(buttons)
    )


@dp.message(F.text == "❤️ Sevimlilar")
async def favorites_button(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    register_user(message.from_user)

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT a.id, a.title
        FROM favorites f
        JOIN animes a ON a.id=f.anime_id
        WHERE f.telegram_id=?
        AND a.is_active=1
        ORDER BY f.id DESC
        LIMIT 30
        """,
        (message.from_user.id,)
    ).fetchall()

    conn.close()

    if not rows:
        await message.answer(
            "❤️ <b>SEVIMLILAR</b>\n\n"
            "Hali anime saqlanmagan.",
            reply_markup=user_keyboard()
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"❤️ {row['title'][:45]}",
                callback_data=f"open_anime_{row['id']}"
            )
        ]
        for row in rows
    ]

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await message.answer(
        "❤️ <b>SEVIMLI ANIMELAR</b>",
        reply_markup=inline(buttons)
    )


@dp.message(F.text == "🕘 Tarix")
async def history_button(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    register_user(message.from_user)

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT
            h.episode_id,
            a.title AS anime,
            e.episode_number
        FROM watch_history h
        JOIN animes a ON a.id=h.anime_id
        JOIN episodes e ON e.id=h.episode_id
        WHERE h.telegram_id=?
        ORDER BY h.watched_at DESC
        LIMIT 20
        """,
        (message.from_user.id,)
    ).fetchall()

    conn.close()

    if not rows:
        await message.answer(
            "🕘 <b>TARIX</b>\n\nHali qism ko‘rilmagan.",
            reply_markup=user_keyboard()
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"▶️ {row['anime'][:30]} · {row['episode_number']}-qism",
                callback_data=f"user_episode_{row['episode_id']}"
            )
        ]
        for row in rows
    ]

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await message.answer(
        "🕘 <b>KO‘RISH TARIXI</b>\n\n"
        "Oxirgi ko‘rilgan qismlar:",
        reply_markup=inline(buttons)
    )


@dp.message(F.text == "📚 Janrlar")
async def genres_button(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    register_user(message.from_user)

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT genre
        FROM animes
        WHERE is_active=1
        AND genre <> ''
        """
    ).fetchall()

    conn.close()

    genres = set()

    for row in rows:
        for genre in (row["genre"] or "").split(","):
            genre = genre.strip()
            if genre:
                genres.add(genre)

    genres = sorted(genres, key=str.casefold)

    if not genres:
        await message.answer(
            "📚 <b>JANRLAR</b>\n\nHozircha janr mavjud emas.",
            reply_markup=user_keyboard()
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🎭 {genre[:50]}",
                callback_data=f"genre_{index}"
            )
        ]
        for index, genre in enumerate(genres[:30])
    ]

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await message.answer(
        "📚 <b>JANRLAR</b>\n\nJanrni tanlang:",
        reply_markup=inline(buttons)
    )


@dp.message(F.text == "📩 Anime so‘rash")
async def anime_request_button(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    await state.clear()
    await state.set_state(AnimeRequest.title)

    await message.answer(
        "📩 <b>ANIME SO‘RASH</b>\n\n"
        "Kerakli anime nomini yozing.",
        reply_markup=cancel_keyboard()
    )


@dp.message(AnimeRequest.title)
async def anime_request_title(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:
        await ask_text(message, "❌ Anime nomini yozing.")
        return

    register_user(message.from_user)

    conn = connect_db()

    cursor = conn.execute(
        """
        INSERT INTO anime_requests (
            telegram_id,
            title
        )
        VALUES (?, ?)
        """,
        (
            message.from_user.id,
            title
        )
    )

    request_id = cursor.lastrowid

    conn.commit()
    conn.close()

    await state.clear()

    await message.answer(
        "✅ <b>SO‘ROV QABUL QILINDI</b>\n\n"
        f"🆔 So‘rov: <code>{request_id}</code>\n"
        f"🎬 {title}\n\n"
        "Admin ko‘rib chiqadi.",
        reply_markup=user_keyboard()
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "📩 <b>YANGI ANIME SO‘ROVI</b>\n\n"
                f"🆔 <code>{request_id}</code>\n"
                f"👤 User: <code>{message.from_user.id}</code>\n"
                f"🎬 <b>{title}</b>"
            )
        except Exception as exc:
            print(
                f"⚠️ Request notification failed: {type(exc).__name__}: {exc}",
                flush=True
            )


@dp.callback_query(F.data.regexp(r"^open_anime_\d+$"))
async def open_anime_callback(
    callback: CallbackQuery
):

    if user_is_banned(callback.from_user.id):
        await callback.answer(
            "❌ Siz bloklangansiz.",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    await callback.answer()

    if not await send_anime_card(
        callback.message,
        anime_id
    ):
        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )


@dp.callback_query(F.data.regexp(r"^favorite_toggle_\d+$"))
async def favorite_toggle_callback(
    callback: CallbackQuery
):

    if user_is_banned(callback.from_user.id):
        await callback.answer(
            "❌ Siz bloklangansiz.",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    if not await send_anime_card(
        callback.message,
        anime_id
    ):
        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )
        return

    favorite = toggle_favorite(
        callback.from_user.id,
        anime_id
    )

    # Refresh the card with the new favorite state.
    await callback.message.delete()

    await send_anime_card(
        callback.message,
        anime_id
    )

    await callback.answer(
        "❤️ Saqlandi." if favorite else "💔 O‘chirildi."
    )


@dp.callback_query(F.data.regexp(r"^genre_\d+$"))
async def genre_callback(
    callback: CallbackQuery
):

    if user_is_banned(callback.from_user.id):
        await callback.answer(
            "❌ Siz bloklangansiz.",
            show_alert=True
        )
        return

    index = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT genre
        FROM animes
        WHERE is_active=1
        AND genre <> ''
        """
    ).fetchall()

    conn.close()

    genres = set()

    for row in rows:
        for genre in (row["genre"] or "").split(","):
            genre = genre.strip()
            if genre:
                genres.add(genre)

    genres = sorted(genres, key=str.casefold)

    if index >= len(genres):
        await callback.answer(
            "❌ Janr topilmadi.",
            show_alert=True
        )
        return

    genre = genres[index]

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT id, title
        FROM animes
        WHERE is_active=1
        AND genre ILIKE ?
        ORDER BY id DESC
        LIMIT 30
        """,
        (f"%{genre}%",)
    ).fetchall()

    conn.close()

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🎬 {row['title'][:48]}",
                callback_data=f"open_anime_{row['id']}"
            )
        ]
        for row in rows
    ]

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Janrlar",
            callback_data="user_genres"
        )
    ])

    await callback.message.edit_text(
        f"🎭 <b>{genre}</b>\n\n"
        "Anime tanlang:",
        reply_markup=inline(buttons)
    )

    await callback.answer()


@dp.callback_query(F.data == "user_genres")
async def user_genres_callback(
    callback: CallbackQuery
):

    await callback.answer()

    conn = connect_db()

    rows = conn.execute(
        """
        SELECT genre
        FROM animes
        WHERE is_active=1
        AND genre <> ''
        """
    ).fetchall()

    conn.close()

    genres = set()

    for row in rows:
        for genre in (row["genre"] or "").split(","):
            genre = genre.strip()
            if genre:
                genres.add(genre)

    genres = sorted(genres, key=str.casefold)

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🎭 {genre[:50]}",
                callback_data=f"genre_{index}"
            )
        ]
        for index, genre in enumerate(genres[:30])
    ]

    buttons.append([
        InlineKeyboardButton(
            text="🏠 Bosh menyu",
            callback_data="user_home"
        )
    ])

    await callback.message.edit_text(
        "📚 <b>JANRLAR</b>\n\nJanrni tanlang:",
        reply_markup=inline(buttons)
    )


async def admin_dashboard_text():
    conn = connect_db()
    values = {
        "users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "anime": conn.execute("SELECT COUNT(*) c FROM animes WHERE is_active=1").fetchone()["c"],
        "episodes": conn.execute("SELECT COUNT(*) c FROM episodes").fetchone()["c"],
        "shorts": conn.execute("SELECT COUNT(*) c FROM shorts").fetchone()["c"],
        "vip": conn.execute("SELECT COUNT(*) c FROM users WHERE is_vip=1").fetchone()["c"],
        "favorites": conn.execute("SELECT COUNT(*) c FROM favorites").fetchone()["c"],
        "requests": conn.execute("SELECT COUNT(*) c FROM anime_requests WHERE status='pending'").fetchone()["c"],
        "views": conn.execute("SELECT COALESCE(SUM(view_count),0) c FROM episodes").fetchone()["c"],
        "short_views": conn.execute("SELECT COALESCE(SUM(view_count),0) c FROM shorts").fetchone()["c"],
    }
    conn.close()

    return (
        "📈 <b>BOT DASHBOARD</b>\n\n"
        f"👥 Users: <b>{values['users']}</b>\n"
        f"🎬 Active anime: <b>{values['anime']}</b>\n"
        f"📺 Qismlar: <b>{values['episodes']}</b>\n"
        f"🎞 Shorts: <b>{values['shorts']}</b>\n"
        f"⭐ VIP users: <b>{values['vip']}</b>\n"
        f"❤️ Favorites: <b>{values['favorites']}</b>\n"
        f"📩 Pending requests: <b>{values['requests']}</b>\n"
        f"👁 Video views: <b>{values['views']}</b>\n"
        f"🎞 Shorts views: <b>{values['short_views']}</b>"
    )


@dp.message(F.text == "🏆 Top 10")
async def top10_admin_reply(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    conn = connect_db()
    rows = conn.execute(
        """
        SELECT title, view_count
        FROM animes
        WHERE is_active=1
        ORDER BY view_count DESC, id DESC
        LIMIT 10
        """
    ).fetchall()
    conn.close()

    lines = ["🏆 <b>TOP 10 ANIMELAR</b>", ""]
    if not rows:
        lines.append("Hozircha anime yo‘q.")
    else:
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. <b>{row['title']}</b> — 👁 {row['view_count'] or 0}"
            )

    await message.answer("\n".join(lines), reply_markup=admin_keyboard())


async def make_and_deliver_backup(admin_id: int):
    path = await asyncio.to_thread(make_backup)
    try:
        await bot.send_document(
            chat_id=admin_id,
            document=FSInputFile(str(path)),
            caption=(
                "💾 <b>BACKUP TAYYOR</b>\n\n"
                f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )
        )
    except Exception as exc:
        print(
            f"⚠️ Backup delivery failed for {admin_id}: {type(exc).__name__}: {exc}",
            flush=True
        )


async def auto_backup_loop():
    while True:
        try:
            for admin_id in ADMIN_IDS:
                await make_and_deliver_backup(admin_id)
            print("✅ Automatic backup completed.", flush=True)
        except Exception as exc:
            print(
                f"⚠️ Automatic backup error: {type(exc).__name__}: {exc}",
                flush=True
            )
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)


@dp.message(F.text == "💾 Backup")
async def backup_reply(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("⏳ <b>Backup tayyorlanmoqda...</b>")
    await make_and_deliver_backup(message.from_user.id)
    await message.answer("✅ <b>Backup yuborildi.</b>", reply_markup=admin_keyboard())


@dp.message(F.text == "📈 Dashboard")
async def dashboard_reply(
    message: Message,
    state: FSMContext
):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        await admin_dashboard_text(),
        reply_markup=inline([
            [
                InlineKeyboardButton(text="🏆 Top 10", callback_data="admin_top10"),
                InlineKeyboardButton(text="💾 Backup", callback_data="admin_backup")
            ],
            [
                InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin_back")
            ]
        ])
    )


@dp.callback_query(F.data == "admin_dashboard")
async def dashboard_callback(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo‘q!", show_alert=True)
        return
    await callback.message.edit_text(
        await admin_dashboard_text(),
        reply_markup=inline([
            [
                InlineKeyboardButton(text="🏆 Top 10", callback_data="admin_top10"),
                InlineKeyboardButton(text="💾 Backup", callback_data="admin_backup")
            ],
            [
                InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin_back")
            ]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_top10")
async def top10_admin_callback(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo‘q!", show_alert=True)
        return
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT title, view_count
        FROM animes
        WHERE is_active=1
        ORDER BY view_count DESC, id DESC
        LIMIT 10
        """
    ).fetchall()
    conn.close()

    lines = ["🏆 <b>TOP 10 ANIMELAR</b>", ""]
    if not rows:
        lines.append("Hozircha anime yo‘q.")
    else:
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. <b>{row['title']}</b> — 👁 {row['view_count'] or 0}"
            )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=inline([
            [
                InlineKeyboardButton(text="📈 Dashboard", callback_data="admin_dashboard"),
                InlineKeyboardButton(text="💾 Backup", callback_data="admin_backup")
            ],
            [
                InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin_back")
            ]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_backup")
async def backup_callback(
    callback: CallbackQuery
):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo‘q!", show_alert=True)
        return
    await callback.answer("⏳ Backup tayyorlanmoqda...")
    await make_and_deliver_backup(callback.from_user.id)


# =========================================================
# ADMIN BAN / UNBAN
# =========================================================

@dp.message(F.text.startswith("/ban"))
async def admin_ban_command(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "❌ Format: <code>/ban TELEGRAM_ID [sabab]</code>"
        )
        return

    user_id = int(parts[1])

    if is_admin(user_id):
        await message.answer("❌ Adminni bloklab bo‘lmaydi.")
        return

    reason = (
        parts[2].strip()
        if len(parts) >= 3
        else "Admin tomonidan bloklandi."
    )

    conn = connect_db()

    conn.execute(
        """
        INSERT INTO users (
            telegram_id,
            is_banned,
            ban_reason
        )
        VALUES (?, 1, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            is_banned=1,
            ban_reason=excluded.ban_reason
        """,
        (user_id, reason)
    )

    conn.commit()
    conn.close()

    await message.answer(
        "🚫 <b>USER BLOKLANDI</b>\n\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"📝 {reason}"
    )


@dp.message(F.text.startswith("/unban"))
async def admin_unban_command(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.clear()

    parts = (message.text or "").split()

    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "❌ Format: <code>/unban TELEGRAM_ID</code>"
        )
        return

    user_id = int(parts[1])

    conn = connect_db()

    conn.execute(
        """
        UPDATE users
        SET is_banned=0,
            ban_reason=''
        WHERE telegram_id=?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()

    await message.answer(
        "✅ <b>USER BLOKDAN CHIQARILDI</b>\n\n"
        f"👤 ID: <code>{user_id}</code>"
    )


# =========================================================
# DIRECT ID SEARCH
# =========================================================

@dp.message(
    F.text.regexp(r"^\d+$")
)
async def numeric_search(
    message: Message,
    state: FSMContext
):

    if user_is_banned(message.from_user.id):
        return

    current_state = await state.get_state()

    if current_state:
        return

    register_user(
        message.from_user
    )

    value = int(
        message.text.strip()
    )

    conn = connect_db()

    episode = conn.execute(
        """
        SELECT
            e.id,
            e.episode_number,
            e.title,
            e.video_file_id,
            e.is_vip,
            e.anime_id,
            a.title AS anime
        FROM episodes e
        JOIN animes a
        ON a.id=e.anime_id
        WHERE e.id=?
        """,
        (value,)
    ).fetchone()

    if episode:

        conn.close()

        if (
            episode["is_vip"]
            and not user_is_vip(
                message.from_user.id
            )
        ):

            await message.answer(
                "🔒 <b>VIP KONTENT</b>\n\n"
                "Bu qism 4-qismdan boshlab VIP kontentga kiradi.\n\n"
                "⭐ VIP oling va barcha qismlarni oching.",
                reply_markup=inline([
                    [
                        InlineKeyboardButton(
                            text="⭐ VIP olish",
                            url="https://t.me/Ichi1010"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Bosh menyu",
                            callback_data="user_home"
                        )
                    ]
                ])
            )

            return

        loading_message, opening_message = (
            await send_loading_messages(
                message.from_user.id,
                "⏳ <b>Qism tayyorlanmoqda...</b>",
                "🎬 <b>Qism ochilmoqda...</b>"
            )
        )

        try:

            record_watch(
                message.from_user.id,
                episode["anime_id"],
                episode["id"]
            )

            await message.answer_video(
                episode["video_file_id"],
                caption=(
                    f"🎬 <b>{episode['anime']}</b>\n"
                    f"📺 {episode['episode_number']}-qism\n"
                    f"📝 {episode['title']}\n"
                    f"🆔 ID: <code>{episode['id']}</code>"
                ),
                protect_content=True
            )

        finally:

            await delete_message_safe(
                message.chat.id,
                loading_message.message_id
            )

            await delete_message_safe(
                message.chat.id,
                opening_message.message_id
            )

        return

    anime = conn.execute(
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

        episodes = conn.execute(
            """
            SELECT
                id,
                episode_number,
                title,
                is_vip
            FROM episodes
            WHERE anime_id=?
            ORDER BY episode_number ASC, id ASC
            """,
            (value,)
        ).fetchall()

        conn.close()

        buttons = []

        for ep in episodes:

            if ep["is_vip"]:

                label = (
                    f"🔒 {ep['episode_number']}-qism "
                    f"⭐ VIP"
                )

            else:

                label = (
                    f"▶️ {ep['episode_number']}-qism"
                )

            buttons.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"user_episode_{ep['id']}"
                )
            ])

        if buttons:

            await message.answer(
                f"🎬 <b>{anime['title']}</b>\n\n"
                f"{anime['description']}\n\n"
                "📺 <b>Qismlar:</b>\n"
                "✅ 1–3-qism bepul\n"
                "🔒 4-qismdan boshlab VIP",
                reply_markup=inline(buttons)
            )

        else:

            await message.answer(
                f"🎬 <b>{anime['title']}</b>\n\n"
                f"{anime['description']}\n\n"
                "📺 Hozircha qism yo‘q.",
                reply_markup=user_keyboard()
            )

        return

    conn.close()

    await message.answer(
        "❌ <b>Bunday anime yoki qism ID topilmadi.</b>\n\n"
        f"🔎 ID: <code>{value}</code>",
        reply_markup=user_keyboard()
    )


# =========================================================
# USER EPISODE
# =========================================================

@dp.callback_query(
    F.data.startswith("user_episode_")
)
async def user_episode(
    callback: CallbackQuery
):

    if user_is_banned(callback.from_user.id):
        await callback.answer(
            "❌ Siz bloklangansiz.",
            show_alert=True
        )
        return

    episode_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    conn = connect_db()

    episode = conn.execute(
        """
        SELECT
            e.id,
            e.anime_id,
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

    conn.close()

    if not episode:

        await callback.answer(
            "❌ Qism topilmadi.",
            show_alert=True
        )

        return

    if (
        episode["is_vip"]
        and not user_is_vip(
            callback.from_user.id
        )
    ):

        await callback.answer(
            "⭐ Bu qism VIP uchun.",
            show_alert=True
        )

        await bot.send_message(
            callback.from_user.id,
            "🔒 <b>VIP KONTENT</b>\n\n"
            f"🎬 {episode['anime']}\n"
            f"📺 {episode['episode_number']}-qism\n\n"
            "4-qismdan boshlab bu anime VIP kontent hisoblanadi.",
            reply_markup=inline([
                [
                    InlineKeyboardButton(
                        text="⭐ VIP olish",
                        url="https://t.me/Ichi1010"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Bosh menyu",
                        callback_data="user_home"
                    )
                ]
            ])
        )

        return

    await callback.answer()

    loading_message, opening_message = (
        await send_loading_messages(
            callback.from_user.id,
            "⏳ <b>Qism tayyorlanmoqda...</b>",
            "🎬 <b>Qism ochilmoqda...</b>"
        )
    )

    try:

        record_watch(
            callback.from_user.id,
            episode["anime_id"],
            episode["id"]
        )

        await bot.send_video(
            callback.from_user.id,
            episode["video_file_id"],
            caption=(
                f"🎬 <b>{episode['anime']}</b>\n"
                f"📺 {episode['episode_number']}-qism\n"
                f"📝 {episode['title']}"
            ),
            protect_content=True
        )

    finally:

        await delete_message_safe(
            callback.from_user.id,
            loading_message.message_id
        )

        await delete_message_safe(
            callback.from_user.id,
            opening_message.message_id
        )


# =========================================================
# FALLBACK
# =========================================================

@dp.message()
async def fallback(
    message: Message,
    state: FSMContext
):

    current_state = await state.get_state()

    if current_state:
        return

    register_user(
        message.from_user
    )

    if is_admin(
        message.from_user.id
    ):

        await message.answer(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "Pastki klaviaturadan foydalaning.",
            reply_markup=admin_keyboard()
        )

    else:

        await message.answer(
            "🔎 Anime yoki qism ID raqamini yuboring.",
            reply_markup=user_keyboard()
        )


# =========================================================
# MAIN
# =========================================================

async def main():

    print("🚀 Telegram polling ishga tushmoqda...", flush=True)

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )