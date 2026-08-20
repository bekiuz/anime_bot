from pathlib import Path
import shutil
from datetime import datetime

path = Path("bot.py")

# =========================================================
# BACKUP
# =========================================================

backup_name = (
    f"bot_backup_"
    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
)

shutil.copy2(path, backup_name)

print(f"✅ Backup yaratildi: {backup_name}")

text = path.read_text(encoding="utf-8")


# =========================================================
# 1. USER REPLY KEYBOARDNI ALMASHTIRISH
# =========================================================

start = text.find("def user_reply_keyboard():")
end = text.find("\ndef admin_reply_keyboard():", start)

if start == -1 or end == -1:
    print("❌ user_reply_keyboard topilmadi")
    raise SystemExit

user_keyboard_code = '''def user_reply_keyboard():
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
        is_persistent=True
    )


'''

text = text[:start] + user_keyboard_code + text[end:]

print("✅ Client keyboard yangilandi")


# =========================================================
# 2. ESKI USER REPLY HANDLERLARNI ALMASHTIRISH
# =========================================================

start_marker = "# =========================================================\n# USER REPLY KEYBOARD HANDLERS"

end_marker = "# =========================================================\n# ADMIN REPLY KEYBOARD HANDLERS"

start = text.find(start_marker)
end = text.find(end_marker)

if start == -1 or end == -1:
    print("❌ User reply handler bo‘limi topilmadi")
    raise SystemExit


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

    register_user(message.from_user)

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
            "🎞 <b>SHORTS</b>\n\n"
            "Hozircha Shorts mavjud emas.",
            reply_markup=user_reply_keyboard()
        )

        return

    try:

        result = await send_short_to_user(
            message.from_user.id,
            first["id"]
        )

        if result == "VIP":

            await message.answer(
                "⭐ Bu Shorts faqat VIP foydalanuvchilar uchun."
            )

    except Exception as e:

        print(f"❌ Shorts xatosi: {e}")

        await message.answer(
            "❌ Shortsni chiqarishda xatolik yuz berdi."
        )


@dp.message(F.text == "⭐ VIP")
async def user_reply_vip(
    message: Message,
    state: FSMContext
):

    await state.clear()

    register_user(message.from_user)

    connection = db()

    row = connection.execute(
        """
        SELECT is_vip, vip_until
        FROM users
        WHERE telegram_id = ?
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
            "VIP kontent va maxsus imkoniyatlar uchun "
            "quyidagi admin bilan bog‘laning:\n\n"
            "👤 <b>@Ichi1010</b>",
            reply_markup=make_kb([
                [
                    InlineKeyboardButton(
                        text="⭐ VIP olish",
                        url="https://t.me/Ichi1010"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Orqaga",
                        callback_data="user_back"
                    )
                ]
            ])
        )


@dp.message(F.text == "📢 Reklama")
async def user_reply_advertising(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "📢 <b>REKLAMA / HAMKORLIK</b>\n\n"
        "Reklama yoki hamkorlik uchun quyidagi "
        "kontaktlardan biriga murojaat qiling:",
        reply_markup=make_kb([
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
                    callback_data="user_back"
                )
            ]
        ])
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


'''

text = text[:start] + user_handlers + text[end:]

print("✅ User tugmalari qayta yozildi")


# =========================================================
# 3. DIRECT SEARCHDA FSMGA XALAQIT BERMASLIK
# =========================================================

old = '''@dp.message(F.text.regexp(r"^\\d+$"))
async def numeric_search(
    message: Message,
    state: FSMContext
):

    current_state = await state.get_state()

    # FSM jarayonida bo‘lsa, state handler ishlaydi.
    if current_state:
        return
'''

new = '''@dp.message(F.text.regexp(r"^\\d+$"))
async def numeric_search(
    message: Message,
    state: FSMContext
):

    current_state = await state.get_state()

    # FSM ichida bo‘lsa, tegishli state handler ishlaydi.
    if current_state:
        return
'''

if old in text:
    text = text.replace(old, new)

print("✅ ID qidiruv saqlandi")


# =========================================================
# 4. SAQLASH
# =========================================================

path.write_text(
    text,
    encoding="utf-8"
)

print("")
print("========================================")
print("✅ MIJOZ TOMONI YANGILANDI")
print("========================================")
print("🔎 ID qidirish")
print("🎞 Shorts")
print("⭐ VIP")
print("📢 Reklama")
print("📩 Murojaat")
print("")
print("📢 Reklama kontaktlari:")
print("   @arata_2915")
print("   @Ichi1010")
print("========================================")
