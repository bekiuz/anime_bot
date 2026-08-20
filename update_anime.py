from pathlib import Path

# ==========================================
# ANIME TABLENI TO'G'RILASH
# ==========================================

db_file = Path("setup_db.py")

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

print("✅ Database jadvallari tayyor")
'''

db_file.write_text(db_code, encoding="utf-8")


# ==========================================
# BOT.PY O'QISH
# ==========================================

bot = Path("bot.py")
text = bot.read_text(encoding="utf-8")


# ==========================================
# ANIME STATE'LARINI ALMASHTIRISH
# ==========================================

old_states = """class AddAnime(StatesGroup):
    title = State()
    description = State()
    poster = State()
    year = State()
    rating = State()
    genres = State()
"""

new_states = """class AddAnime(StatesGroup):
    title = State()
    description = State()
"""

if old_states in text:
    text = text.replace(old_states, new_states)


# ==========================================
# ESKI ANIME ADD QISMINI TOPISH
# ==========================================

start_marker = '@dp.callback_query(F.data == "anime_add")'
end_marker = '@dp.callback_query(F.data == "anime_list")'

start = text.find(start_marker)
end = text.find(end_marker)

if start == -1 or end == -1:
    print("❌ Anime qo'shish qismi topilmadi.")
    raise SystemExit

# ==========================================
# YANGI ANIME QO'SHISH
# ==========================================

new_anime_code = r'''
@dp.callback_query(F.data == "anime_add")
async def anime_add_start(
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
    await state.set_state(AddAnime.title)

    await callback.message.edit_text(
        "➕ <b>YANGI ANIME QO‘SHISH</b>\n\n"
        "1️⃣ Anime nomini yuboring:\n\n"
        "Masalan:\n"
        "<code>Naruto</code>"
    )

    await callback.answer()


@dp.message(AddAnime.title)
async def new_anime_title(
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
        "2️⃣ <b>Anime tavsifini yuboring:</b>\n\n"
        "Masalan:\n"
        "<code>Yosh ninja haqidagi mashhur anime.</code>"
    )


@dp.message(AddAnime.description)
async def new_anime_description(
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

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            INSERT INTO animes (
                title,
                description,
                is_active
            )
            VALUES (?, ?, 1)
            """,
            (
                data["title"],
                description
            )
        )

        anime_id = cursor.lastrowid

        await db.commit()

    await state.clear()

    await message.answer(
        "✅ <b>ANIME MUVAFFAQIYATLI QO‘SHILDI!</b>\n\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎬 Nomi: <b>{data['title']}</b>\n"
        f"📝 Tavsifi: {description}\n\n"
        "📺 Endi shu animega qism qo‘shishingiz mumkin.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📺 Qism qo‘shish",
                        callback_data="episode_add"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎬 Anime boshqaruvi",
                        callback_data="admin_anime"
                    )
                ]
            ]
        )
    )


'''

text = text[:start] + new_anime_code + text[end:]


# ==========================================
# DATABASE INIT BOT START'DA ISHLASHI
# ==========================================

startup_marker = "@dp.startup()\nasync def startup():"

if startup_marker in text and "await init_database()" not in text:

    # startup funksiyasiga database init qo'shamiz
    replacement = """@dp.startup()
async def startup():

    import sqlite3
    from pathlib import Path

    Path("data").mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(\"\"\"
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
    \"\"\")

    cursor.execute(\"\"\"
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
    \"\"\")

    cursor.execute(\"\"\"
    CREATE TABLE IF NOT EXISTS shorts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        video_file_id TEXT NOT NULL,
        is_vip INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    \"\"\")

    conn.commit()
    conn.close()

    print("========================================")
    print("🤖 ANIME BOT")
    print("========================================")
    print(f"✅ {len(ADMIN_IDS)} ta admin yuklandi")
    print("✅ Database tayyor")
    print("✅ Anime tizimi tayyor")
    print("🚀 Polling boshlandi")
    print("========================================")
"""

    start = text.find(startup_marker)
    end = text.find("\n\n", start)

    if end != -1:
        text = text[:start] + replacement + text[end:]


# ==========================================
# BOTNI SAQLASH
# ==========================================

bot.write_text(text, encoding="utf-8")

print("✅ Anime qo'shish tizimi yangilandi")
print("✅ Poster olib tashlandi")
print("✅ Yil olib tashlandi")
print("✅ Reyting olib tashlandi")
print("✅ Janr olib tashlandi")
print("✅ Faqat ID + nom + tavsif qoldi")
