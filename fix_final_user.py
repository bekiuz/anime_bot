from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")


# =========================================================
# 1. CLIENT KEYBOARDNI TO'LIQ ALMASHTIRAMIZ
# =========================================================

start = text.find("def user_keyboard():")
end = text.find("\ndef admin_keyboard():", start)

if start == -1 or end == -1:
    print("❌ user_keyboard topilmadi")
    raise SystemExit

new_user_keyboard = '''def user_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔎 ID qidirish"),
                KeyboardButton(text="🎞 Shorts")
            ],
            [
                KeyboardButton(text="⭐ VIP"),
                KeyboardButton(text="📢 Reklama")
            ],
            [
                KeyboardButton(text="📩 Murojaat")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Bo‘limni tanlang..."
    )


'''

text = text[:start] + new_user_keyboard + text[end:]

print("✅ Client keyboard yangilandi")


# =========================================================
# 2. SEND SHORT FUNKSIYASINI TO'LIQ ALMASHTIRAMIZ
# =========================================================

start = text.find("async def send_short(")
end = text.find("\n\n# =========================================================\n# STATES", start)

if start == -1:
    print("❌ send_short topilmadi")
    raise SystemExit

new_send_short = r'''async def send_short(
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

    current_index = None

    for index, short in enumerate(shorts):

        if short["id"] == short_id:

            current_index = index
            break

    if current_index is None:
        current_index = 0

    short = shorts[current_index]

    # VIP tekshiruvi
    if short["is_vip"]:

        if not user_is_vip(chat_id):

            return "VIP"

    # Keyingi video
    if len(shorts) > 1:

        next_index = (
            current_index + 1
        ) % len(shorts)

        next_id = shorts[next_index]["id"]

    else:

        # Faqat bitta Shorts bo‘lsa ham tugma chiqadi.
        next_id = short["id"]

    keyboard = inline([
        [
            InlineKeyboardButton(
                text="➡️ Keyingi video",
                callback_data=f"next_short_{next_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Bosh menyu",
                callback_data="user_home"
            )
        ]
    ])

    await bot.send_video(
        chat_id=chat_id,
        video=short["video_file_id"],
        caption=(
            f"🎞 <b>{short['title']}</b>\n\n"
            f"{short['description']}\n\n"
            f"🆔 ID: <code>{short['id']}</code>"
        ),
        reply_markup=keyboard
    )

    return True
'''

text = text[:start] + new_send_short + text[end:]

print("✅ Shorts Keyingi video tizimi yangilandi")


# =========================================================
# 3. NEXT SHORT HANDLERNI TO'LIQ ALMASHTIRAMIZ
# =========================================================

start = text.find(
    '@dp.callback_query(F.data.startswith("next_short_"))'
)

if start == -1:
    print("❌ next_short handler topilmadi")
    raise SystemExit

# Keyingi callback handlerdan oldingi katta separatorni topamiz.
end = text.find(
    "\n\n# =========================================================",
    start + 10
)

if end == -1:
    print("❌ next_short tugashi topilmadi")
    raise SystemExit

new_next = r'''
@dp.callback_query(F.data.startswith("next_short_"))
async def next_short(
    callback: CallbackQuery
):

    short_id = int(
        callback.data.rsplit("_", 1)[1]
    )

    result = await send_short(
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
'''

text = text[:start] + new_next + text[end:]

print("✅ Keyingi video handler yangilandi")


# =========================================================
# 4. REKLAMA HANDLERNI MAJBURAN QO'SHAMIZ
# =========================================================

# Eski handlerni topamiz
start = text.find(
    '@dp.message(F.text == "📢 Reklama")'
)

if start != -1:

    end = text.find(
        "\n\n# =========================================================",
        start
    )

    if end == -1:
        print("❌ Reklama handler oxiri topilmadi")
        raise SystemExit

    text = text[:start] + text[end:]

    print("✅ Eski reklama handler olib tashlandi")


# Yangi handlerni ID qidirish buttonidan oldin qo'yamiz
marker = "# =========================================================\n# CLIENT ID SEARCH BUTTON"

if marker not in text:
    print("❌ CLIENT ID SEARCH marker topilmadi")
    raise SystemExit

advertising = r'''
# =========================================================
# CLIENT REKLAMA
# =========================================================

@dp.message(F.text == "📢 Reklama")
async def advertising_button(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "📢 <b>REKLAMA / HAMKORLIK</b>\n\n"
        "Reklama uchun quyidagi kontaktlardan biriga "
        "murojaat qiling:",
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

'''

pos = text.find(marker)

text = text[:pos] + advertising + text[pos:]

print("✅ Reklama handler qo'shildi")


# =========================================================
# 5. START YUBORGANDAN KEYIN KEYBOARDNI YANGILASH
# =========================================================

start_handler = text.find("@dp.message(CommandStart())")

if start_handler != -1:

    # Oddiy user javobida user_keyboard bo'lishi kerak.
    block_end = text.find(
        "\n\n# =========================================================",
        start_handler
    )

    if block_end != -1:

        block = text[start_handler:block_end]

        # client keyboard
        block = block.replace(
            "reply_markup=admin_keyboard()",
            "reply_markup=admin_keyboard()"
        )

        block = block.replace(
            "reply_markup=user_keyboard()",
            "reply_markup=user_keyboard()"
        )

        text = (
            text[:start_handler]
            + block
            + text[block_end:]
        )

print("✅ /start client keyboard tekshirildi")


# =========================================================
# 6. SAQLASH
# =========================================================

path.write_text(
    text,
    encoding="utf-8"
)

print("")
print("========================================")
print("✅ REKLAMA + SHORTS TUZATILDI")
print("========================================")
print("📢 Reklama")
print("   ├── @arata_2915")
print("   └── @Ichi1010")
print("")
print("🎞 Shorts")
print("   └── ➡️ Keyingi video")
print("========================================")
