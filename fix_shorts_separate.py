from pathlib import Path
import re

path = Path("bot.py")
text = path.read_text(encoding="utf-8")

# =========================================================
# 1. ESKI "🎞 Shorts" REPLY HANDLERLARINI OLIB TASHLASH
# =========================================================

pattern = re.compile(
    r'@dp\.message\(F\.text == "🎞 Shorts"\)\n'
    r'async def [\s\S]*?(?=\n@dp\.)',
    re.MULTILINE
)

text, removed = pattern.subn("", text)

print(f"✅ Eski Shorts reply handlerlari o‘chirildi: {removed}")


# =========================================================
# 2. YANGI ANIQLANGAN SHORTS REPLY HANDLER
# =========================================================

marker = "# =========================================================\n# CLIENT ID SEARCH"

if marker not in text:
    marker = "# =========================================================\n# DIRECT ID SEARCH"

if marker not in text:
    print("❌ SHORTS joylashtiriladigan joy topilmadi")
    raise SystemExit

short_reply = r'''
# =========================================================
# CLIENT / ADMIN SHORTS BUTTON
# =========================================================

@dp.message(F.text == "🎞 Shorts")
async def shorts_main_button(
    message: Message,
    state: FSMContext
):

    await state.clear()

    # ADMIN uchun Shorts boshqaruvi
    if is_admin(message.from_user.id):

        await message.answer(
            "🎞 <b>SHORTS BOSHQARUVI</b>\n\n"
            "Kerakli amalni tanlang:",
            reply_markup=shorts_keyboard()
        )

        return

    # MIJOZ uchun faqat Shorts ko‘rish
    register_user(message.from_user)

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

'''

pos = text.find(marker)

text = text[:pos] + short_reply + text[pos:]

print("✅ Shorts client/admin ajratildi")


# =========================================================
# 3. ESKI send_short FUNKSIYASINI OLIB TASHLASH
# =========================================================

start = text.find("async def send_short(")

if start != -1:

    # keyingi asosiy separatorni topamiz
    end = text.find(
        "\n\n# =========================================================",
        start + 10
    )

    if end == -1:
        print("❌ send_short oxiri topilmadi")
        raise SystemExit

    text = text[:start] + text[end + 2:]

    print("✅ Eski send_short olib tashlandi")


# =========================================================
# 4. YANGI SHORTS ENGINE
# =========================================================

# States yoki boshqa bo‘limlardan oldin qo‘yamiz
marker2 = "# =========================================================\n# STATES"

if marker2 not in text:
    print("❌ STATES marker topilmadi")
    raise SystemExit

new_short_engine = r'''
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

    # Faqat shorts jadvalidan qidiramiz.
    current_index = -1

    for index, item in enumerate(shorts):

        if item["id"] == short_id:
            current_index = index
            break

    if current_index == -1:

        return False

    current = shorts[current_index]

    # VIP tekshiruvi
    if current["is_vip"]:

        if not user_is_vip(chat_id):

            return "VIP"

    # Keyingi Shorts
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

    await bot.send_video(
        chat_id=chat_id,
        video=current["video_file_id"],
        caption=(
            f"🎞 <b>{current['title']}</b>\n\n"
            f"{current['description']}"
        ),
        reply_markup=inline(buttons)
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

    # Callback faqat SHORTS uchun ishlaydi.
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


'''

pos = text.find(marker2)

text = text[:pos] + new_short_engine + text[pos:]

print("✅ Yangi Shorts engine qo‘shildi")


# =========================================================
# 5. ESKI next_short HANDLERLARNI OLIB TASHLASH
# =========================================================

pattern2 = re.compile(
    r'@dp\.callback_query\(F\.data\.startswith\("next_short_"\)\)\n'
    r'async def [\s\S]*?(?=\n@dp\.|\n# =========================================================)',
    re.MULTILINE
)

text, removed2 = pattern2.subn("", text)

print(f"✅ Eski next_short handlerlari o‘chirildi: {removed2}")


# =========================================================
# 6. CLIENT SHORTS BUTTONNI DUPLIKAT QILMASLIK
# =========================================================

# Bir nechta bir xil handler qolgan bo‘lsa, yuqoridagi regex ularni
# olib tashlaydi. Yakuniy tekshiruv:
count = text.count('@dp.message(F.text == "🎞 Shorts")')

if count > 1:

    print(
        f"⚠️ {count} ta Shorts handler topildi. "
        "Faqat birinchisini qoldiramiz."
    )

    pattern3 = re.compile(
        r'@dp\.message\(F\.text == "🎞 Shorts"\)\n'
        r'async def [\s\S]*?(?=\n@dp\.)',
        re.MULTILINE
    )

    matches = list(pattern3.finditer(text))

    for match in reversed(matches[1:]):
        text = (
            text[:match.start()]
            + text[match.end():]
        )


# =========================================================
# 7. SYNTAX UCHUN SAQLASH
# =========================================================

path.write_text(
    text,
    encoding="utf-8"
)

print("")
print("========================================")
print("✅ SHORTS TO‘LIQ AJRATILDI")
print("========================================")
print("📺 Qismlar → episodes jadvali")
print("🎞 Shorts → shorts jadvali")
print("➡️ Keyingi video → shortnext_")
print("👑 Admin Shorts → boshqaruv")
print("👤 Client Shorts → video")
print("========================================")
