from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")


# =========================================================
# 1. USER MENU
# =========================================================

old = '''def user_keyboard():
    return make_kb([
        [
            InlineKeyboardButton(
                text="🔎 ID orqali qidirish",
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
'''

new = '''def user_keyboard():
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
'''

if old in text:
    text = text.replace(old, new)
    print("✅ Foydalanuvchi menyusi yangilandi")
else:
    print("ℹ️ User keyboard allaqachon o‘zgargan")


# =========================================================
# 2. SHORTS BO‘LIMI
# =========================================================

short_start = '@dp.callback_query(F.data == "user_shorts")'
short_end = '# =========================================================\n# USER VIP'

start = text.find(short_start)
end = text.find(short_end)

if start == -1 or end == -1:
    print("❌ Shorts bo‘limi topilmadi")
    raise SystemExit

new_shorts = r'''
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


'''

text = text[:start] + new_shorts + text[end:]


# =========================================================
# 3. VIP BO‘LIMI
# =========================================================

vip_start = '@dp.callback_query(F.data == "user_vip")'
vip_end = '# =========================================================\n# USER CONTACT'

start = text.find(vip_start)
end = text.find(vip_end)

if start == -1 or end == -1:
    print("❌ VIP bo‘limi topilmadi")
    raise SystemExit

new_vip = r'''
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


'''

text = text[:start] + new_vip + text[end:]


# =========================================================
# 4. USER CONTACT
# =========================================================

contact_start = '@dp.callback_query(F.data == "user_contact")'
contact_end = '# =========================================================\n# DIRECT ID SEARCH'

start = text.find(contact_start)
end = text.find(contact_end)

if start != -1 and end != -1:

    new_contact = r'''
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


'''

    text = text[:start] + new_contact + text[end:]

    print("✅ Murojaat bo‘limi ham @Ichi1010 ga bog‘landi")


# =========================================================
# 5. SAQLASH
# =========================================================

path.write_text(
    text,
    encoding="utf-8"
)

print("")
print("========================================")
print("✅ FOYDALANUVCHI PANELI YANGILANDI")
print("========================================")
print("🔎 ID qidirish")
print("🎞 Shorts + ➡️ Keyingisi")
print("⭐ VIP olish")
print("👤 @Ichi1010")
print("📩 Murojaat → @Ichi1010")
print("========================================")
