from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")

# =========================================================
# 1. REPLY KEYBOARD IMPORT
# =========================================================

if "ReplyKeyboardMarkup" not in text:

    text = text.replace(
        "    InlineKeyboardMarkup,\n",
        "    InlineKeyboardMarkup,\n"
        "    ReplyKeyboardMarkup,\n"
        "    KeyboardButton,\n"
        "    ReplyKeyboardRemove,\n"
    )

# =========================================================
# 2. USER REPLY KEYBOARD
# =========================================================

if "def user_reply_keyboard():" not in text:

    marker = "def user_keyboard():"

    code = '''
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


'''

    pos = text.find(marker)

    if pos == -1:
        print("❌ user_keyboard topilmadi")
        raise SystemExit

    text = text[:pos] + code + text[pos:]


# =========================================================
# 3. STARTNI REPLY KEYBOARDGA O'TKAZISH
# =========================================================

start_marker = '@dp.message(CommandStart())'
start = text.find(start_marker)

if start == -1:
    print("❌ /start handler topilmadi")
    raise SystemExit

next_marker = '# =========================================================\n# ADMIN MAIN'
end = text.find(next_marker, start)

if end == -1:
    print("❌ ADMIN MAIN topilmadi")
    raise SystemExit

new_start = r'''
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


'''

text = text[:start] + new_start + text[end:]


# =========================================================
# 4. USER TEXT BUTTON HANDLERS
# =========================================================

user_handler_marker = "# =========================================================\n# DIRECT ID SEARCH"

if "async def user_reply_id_search(" not in text:

    user_handlers = r'''
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


'''

    pos = text.find(user_handler_marker)

    if pos == -1:
        print("❌ DIRECT ID SEARCH topilmadi")
        raise SystemExit

    text = text[:pos] + user_handlers + text[pos:]


# =========================================================
# 5. ADMIN REPLY KEYBOARD
# =========================================================

admin_marker = "# =========================================================\n# ANIME MENU"

if "async def admin_reply_anime(" not in text:

    admin_handlers = r'''
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


'''

    pos = text.find(admin_marker)

    if pos == -1:
        print("❌ ANIME MENU topilmadi")
        raise SystemExit

    text = text[:pos] + admin_handlers + text[pos:]


# =========================================================
# 6. CANCEL'DA HAM REPLY KEYBOARDNI QOLDIRISH
# =========================================================

text = text.replace(
    'reply_markup=admin_main_keyboard()\n        )',
    'reply_markup=admin_reply_keyboard()\n        )'
)

text = text.replace(
    'reply_markup=user_keyboard()\n        )',
    'reply_markup=user_reply_keyboard()\n        )'
)


# =========================================================
# 7. SAQLASH
# =========================================================

path.write_text(
    text,
    encoding="utf-8"
)

print("")
print("========================================")
print("✅ REPLY KEYBOARD TAYYOR")
print("========================================")
print("👤 User keyboard")
print("👑 Admin keyboard")
print("🔎 ID qidirish")
print("🎞 Shorts")
print("⭐ VIP")
print("📩 Murojaat")
print("========================================")
