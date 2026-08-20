from pathlib import Path

bot_path = Path("bot.py")
text = bot_path.read_text(encoding="utf-8")

# ============================================
# 1. DATABASE SETUP
# ============================================

Path("data").mkdir(exist_ok=True)

db_code = r'''
import sqlite3
from pathlib import Path

Path("data").mkdir(exist_ok=True)

conn = sqlite3.connect("data/bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    full_name TEXT,
    is_vip INTEGER DEFAULT 0,
    vip_until TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS animes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    poster TEXT,
    banner TEXT,
    year INTEGER,
    rating REAL DEFAULT 0,
    genres TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    title TEXT,
    video_file_id TEXT NOT NULL,
    is_vip INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (anime_id) REFERENCES animes(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS shorts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    video_file_id TEXT NOT NULL,
    is_vip INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("✅ SQLite jadvallari tayyor")
'''

Path("setup_db.py").write_text(db_code, encoding="utf-8")

# ============================================
# 2. OLD EPISODE HANDLERNI OLIB TASHLASH
# ============================================

old_block_start = '@dp.callback_query(F.data == "episode_add")'
old_block_end = '@dp.callback_query(F.data == "episode_edit")'

start_index = text.find(old_block_start)

if start_index != -1:
    end_index = text.find(old_block_end, start_index)

    if end_index != -1:
        text = text[:start_index] + text[end_index:]
        print("✅ Eski episode_add handler olib tashlandi")
    else:
        print("⚠️ episode_edit topilmadi")
else:
    print("ℹ️ Eski episode_add handler topilmadi")

# ============================================
# 3. YANGI EPISODE STATE
# ============================================

if "class AddEpisode(StatesGroup):" not in text:

    marker = "class AddAnime(StatesGroup):"

    pos = text.find(marker)

    if pos != -1:

        end = text.find("\n\n\n", pos)

        if end == -1:
            end = text.find("\n\n", pos)

        episode_state = '''

class AddEpisode(StatesGroup):
    anime_id = State()
    anime_title = State()
    episode_number = State()
    title = State()
    video = State()
'''

        text = text[:end] + episode_state + text[end:]

        print("✅ AddEpisode state qo‘shildi")

# ============================================
# 4. YANGI EPISODE KODI
# ============================================

episode_code = r'''

# ==================================================
# REAL EPISODE SYSTEM
# ==================================================

def episode_anime_keyboard(rows):

    buttons = []

    for anime_id, title in rows:
        buttons.append([
            InlineKeyboardButton(
                text=f"🎬 {title}",
                callback_data=f"episode_anime_{anime_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Qismlar boshqaruvi",
            callback_data="admin_episodes"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


@dp.callback_query(F.data == "episode_add")
async def real_episode_add(
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

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT id, title
            FROM animes
            WHERE is_active = 1
            ORDER BY id DESC
            """
        )

        rows = await cursor.fetchall()

    if not rows:

        await callback.answer(
            "❌ Avval anime qo‘shing!",
            show_alert=True
        )

        return

    await callback.message.edit_text(
        "📺 <b>QISM QO‘SHISH</b>\n\n"
        "Qaysi animega qism qo‘shasiz?",
        reply_markup=episode_anime_keyboard(rows)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("episode_anime_"))
async def real_episode_select(
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
        callback.data.replace(
            "episode_anime_",
            ""
        )
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT title
            FROM animes
            WHERE id = ?
            """,
            (anime_id,)
        )

        row = await cursor.fetchone()

    if not row:

        await callback.answer(
            "❌ Anime topilmadi!",
            show_alert=True
        )

        return

    await state.update_data(
        anime_id=anime_id,
        anime_title=row[0]
    )

    await state.set_state(
        AddEpisode.episode_number
    )

    await callback.message.edit_text(
        f"🎬 <b>{row[0]}</b>\n\n"
        "1️⃣ Qism raqamini yuboring.\n\n"
        "Masalan: <code>1</code>"
    )

    await callback.answer()


@dp.message(AddEpisode.episode_number)
async def real_episode_number(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    value = (message.text or "").strip()

    if not value.isdigit():

        await message.answer(
            "❌ Faqat raqam yuboring.\n"
            "Masalan: <code>1</code>"
        )

        return

    number = int(value)

    if number < 1:

        await message.answer(
            "❌ Qism raqami 1 dan kichik bo‘lmasin."
        )

        return

    await state.update_data(
        episode_number=number
    )

    await state.set_state(
        AddEpisode.title
    )

    await message.answer(
        "2️⃣ <b>Qism nomini yuboring:</b>\n\n"
        "Masalan: <code>1-qism</code>"
    )


@dp.message(AddEpisode.title)
async def real_episode_title(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()

    if not title:

        await message.answer(
            "❌ Qism nomini kiriting."
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddEpisode.video
    )

    await message.answer(
        "3️⃣ <b>Endi videoni yuboring 🎥</b>\n\n"
        "Video sifatida yuboring."
    )


@dp.message(AddEpisode.video, F.video)
async def real_episode_video(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    video_file_id = message.video.file_id

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            INSERT INTO episodes (
                anime_id,
                episode_number,
                title,
                video_file_id,
                is_vip
            )
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                data["anime_id"],
                data["episode_number"],
                data["title"],
                video_file_id
            )
        )

        episode_id = cursor.lastrowid

        await db.commit()

    await state.clear()

    await message.answer(
        "✅ <b>QISM SAQLANDI!</b>\n\n"
        f"🆔 Qism ID: <code>{episode_id}</code>\n"
        f"🎬 Anime: <b>{data['anime_title']}</b>\n"
        f"📺 Qism: <b>{data['episode_number']}</b>\n"
        f"📝 Nomi: <b>{data['title']}</b>\n\n"
        "🎥 Video Telegram file_id bilan saqlandi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Yana qism qo‘shish",
                        callback_data="episode_add"
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
                        text="👑 Admin panel",
                        callback_data="admin_back"
                    )
                ]
            ]
        )
    )


@dp.message(AddEpisode.video)
async def real_episode_not_video(
    message: Message
):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "❌ Iltimos, video yuboring 🎥"
    )


@dp.callback_query(F.data == "episode_list")
async def real_episode_list(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT
                episodes.id,
                episodes.episode_number,
                episodes.title,
                animes.title
            FROM episodes
            JOIN animes
                ON animes.id = episodes.anime_id
            ORDER BY episodes.id DESC
            """
        )

        rows = await cursor.fetchall()

    if not rows:

        text = (
            "📋 <b>QISMLAR RO‘YXATI</b>\n\n"
            "Hozircha qism yo‘q."
        )

    else:

        parts = [
            "📋 <b>QISMLAR RO‘YXATI</b>\n"
        ]

        for episode_id, number, title, anime_title in rows:

            parts.append(
                f"🆔 <code>{episode_id}</code>\n"
                f"🎬 {anime_title}\n"
                f"📺 {number}-qism — {title}\n"
            )

        text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()
'''

# Eski/new episode sistem allaqachon bo‘lmasa qo‘shamiz
if "async def real_episode_add(" not in text:

    # admin_episodes dan keyin qo‘shish
    marker = "# ==================================================\n# SHORTS"

    pos = text.find(marker)

    if pos != -1:

        text = text[:pos] + episode_code + "\n\n" + text[pos:]

        print("✅ Yangi haqiqiy episode tizimi qo‘shildi")

    else:

        print("❌ SHORTS marker topilmadi")
        raise SystemExit

else:

    print("ℹ️ Episode tizimi allaqachon mavjud")

bot_path.write_text(text, encoding="utf-8")

print("✅ bot.py yangilandi")
