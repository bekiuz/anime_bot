from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")

# =========================================================
# 1. KERAKLI IMPORTNI TEKSHIRISH
# =========================================================

if "ReplyKeyboardMarkup" not in text:

    text = text.replace(
        "    InlineKeyboardMarkup,\n",
        "    InlineKeyboardMarkup,\n    ReplyKeyboardMarkup,\n    KeyboardButton,\n    ReplyKeyboardRemove,\n"
    )

# =========================================================
# 2. BEKOR QILISH KLAVIATURASI
# =========================================================

marker = "def make_kb(rows):"

if "def cancel_keyboard():" not in text:

    cancel_code = '''
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


'''

    pos = text.find(marker)

    if pos == -1:
        print("❌ make_kb topilmadi")
        raise SystemExit

    text = text[:pos] + cancel_code + text[pos:]

# =========================================================
# 3. GLOBAL CANCEL HANDLER
# =========================================================

cancel_marker = "# =========================================================\n# START"

if "@dp.message(F.text == \"❌ Bekor qilish\")" not in text:

    cancel_handler = '''
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
            "👑 <b>ADMIN PANEL</b>\\n\\n"
            "Kerakli bo‘limni tanlang:",
            reply_markup=admin_main_keyboard()
        )

    else:

        await message.answer(
            "🎬 <b>Anime Bot</b>\\n\\n"
            "Anime yoki qism ID raqamini yuboring 🔎",
            reply_markup=user_keyboard()
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
            "👑 <b>ADMIN PANEL</b>\\n\\n"
            "Kerakli bo‘limni tanlang:",
            reply_markup=admin_main_keyboard()
        )

    else:

        await message.answer(
            "🎬 <b>Anime Bot</b>\\n\\n"
            "Anime yoki qism ID raqamini yuboring 🔎",
            reply_markup=user_keyboard()
        )


'''

    pos = text.find(cancel_marker)

    if pos == -1:
        print("❌ START marker topilmadi")
        raise SystemExit

    text = text[:pos] + cancel_handler + text[pos:]

# =========================================================
# 4. FSM BOSHLANGANDA BEKOR QILISH KLAVIATURASINI KO'RSATISH
# =========================================================

# Anime title
text = text.replace(
    'await message.answer(\n        "2️⃣ Anime tavsifini yuboring:"\n    )',
    'await message.answer(\n        "2️⃣ Anime tavsifini yuboring:",\n        reply_markup=cancel_keyboard()\n    )'
)

# Anime add start
text = text.replace(
    'await callback.message.edit_text(\n        "➕ <b>ANIME QO‘SHISH</b>\\n\\n"\n        "1️⃣ Anime nomini yuboring:"\n    )',
    'await callback.message.edit_text(\n        "➕ <b>ANIME QO‘SHISH</b>\\n\\n"\n        "1️⃣ Anime nomini yuboring:"\n    )\n\n    await callback.message.answer(\n        "❌ Tugma orqali bekor qilishingiz mumkin.",\n        reply_markup=cancel_keyboard()\n    )'
)

# Anime edit title
text = text.replace(
    'await callback.message.edit_text(\n        f"✏️ Hozirgi nom: <b>{row[\'title\']}</b>\\n\\n"\n        "Yangi nomni yuboring:"\n    )',
    'await callback.message.edit_text(\n        f"✏️ Hozirgi nom: <b>{row[\'title\']}</b>\\n\\n"\n        "Yangi nomni yuboring:"\n    )\n\n    await callback.message.answer(\n        "❌ Bekor qilish mumkin.",\n        reply_markup=cancel_keyboard()\n    )'
)

# Episode number
text = text.replace(
    'await message.answer(\n        "2️⃣ Qism nomini yuboring:"\n    )',
    'await message.answer(\n        "2️⃣ Qism nomini yuboring:",\n        reply_markup=cancel_keyboard()\n    )'
)

# Episode title
text = text.replace(
    'await message.answer(\n        "3️⃣ Qism videosini yuboring 🎥"\n    )',
    'await message.answer(\n        "3️⃣ Qism videosini yuboring 🎥",\n        reply_markup=cancel_keyboard()\n    )'
)

# Short title
text = text.replace(
    'await callback.message.edit_text(\n        "➕ <b>SHORTS QO‘SHISH</b>\\n\\n"\n        "1️⃣ Shorts nomini yuboring:"\n    )',
    'await callback.message.edit_text(\n        "➕ <b>SHORTS QO‘SHISH</b>\\n\\n"\n        "1️⃣ Shorts nomini yuboring:"\n    )\n\n    await callback.message.answer(\n        "❌ Tugma orqali bekor qilishingiz mumkin.",\n        reply_markup=cancel_keyboard()\n    )'
)

# Short description
text = text.replace(
    'await message.answer(\n        "2️⃣ Shorts tavsifini yuboring:"\n    )',
    'await message.answer(\n        "2️⃣ Shorts tavsifini yuboring:",\n        reply_markup=cancel_keyboard()\n    )'
)

# Short video
text = text.replace(
    'await message.answer(\n        "3️⃣ Shorts videosini yuboring 🎥"\n    )',
    'await message.answer(\n        "3️⃣ Shorts videosini yuboring 🎥",\n        reply_markup=cancel_keyboard()\n    )'
)

# VIP user ID
text = text.replace(
    'await callback.message.edit_text(\n        "⭐ <b>VIP BERISH</b>\\n\\n"\n        "Foydalanuvchining Telegram ID sini yuboring:"\n    )',
    'await callback.message.edit_text(\n        "⭐ <b>VIP BERISH</b>\\n\\n"\n        "Foydalanuvchining Telegram ID sini yuboring:"\n    )\n\n    await callback.message.answer(\n        "❌ Bekor qilish tugmasi tayyor.",\n        reply_markup=cancel_keyboard()\n    )'
)

# VIP days
text = text.replace(
    'await message.answer(\n        "Necha kunlik VIP?\\n\\n"\n        "Masalan: <code>30</code>"\n    )',
    'await message.answer(\n        "Necha kunlik VIP?\\n\\n"\n        "Masalan: <code>30</code>",\n        reply_markup=cancel_keyboard()\n    )'
)

# VIP remove
text = text.replace(
    'await callback.message.edit_text(\n        "❌ <b>VIPNI OLIB TASHLASH</b>\\n\\n"\n        "Telegram ID raqamini yuboring:"\n    )',
    'await callback.message.edit_text(\n        "❌ <b>VIPNI OLIB TASHLASH</b>\\n\\n"\n        "Telegram ID raqamini yuboring:"\n    )\n\n    await callback.message.answer(\n        "❌ Bekor qilish tugmasi tayyor.",\n        reply_markup=cancel_keyboard()\n    )'
)

# Broadcast
text = text.replace(
    'await callback.message.edit_text(\n        "📢 <b>RASSILKA</b>\\n\\n"\n        "Yuboriladigan xabarni shu yerga yuboring.\\n\\n"\n        "Matn, rasm, video yoki boshqa Telegram xabari bo‘lishi mumkin."\n    )',
    'await callback.message.edit_text(\n        "📢 <b>RASSILKA</b>\\n\\n"\n        "Yuboriladigan xabarni shu yerga yuboring.\\n\\n"\n        "Matn, rasm, video yoki boshqa Telegram xabari bo‘lishi mumkin."\n    )\n\n    await callback.message.answer(\n        "❌ Bekor qilish mumkin.",\n        reply_markup=cancel_keyboard()\n    )'
)

# =========================================================
# 5. YAKUNIY JAVOBLARDA KLAWIATURANI OLIB TASHLASH
# =========================================================

# Bot importlari mavjud bo'lsa ReplyKeyboardRemove ishlaydi.
# Muvaffaqiyatli yakunda keyboardni olib tashlaymiz.
replacements = {
    'reply_markup=anime_keyboard()\n    )':
        'reply_markup=anime_keyboard()\n    )',
}

path.write_text(text, encoding="utf-8")

print("========================================")
print("✅ BEKOR QILISH TIZIMI QO‘SHILDI")
print("========================================")
print("❌ Bekor qilish tugmasi")
print("✅ /cancel komandasi")
print("✅ Anime")
print("✅ Qism")
print("✅ Shorts")
print("✅ VIP")
print("✅ Rassilka")
print("========================================")
