from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")

# =========================================================
# 1. EDIT ANIME STATE
# =========================================================

if "class EditAnime(StatesGroup):" not in text:

    marker = """class AddAnime(StatesGroup):
    title = State()
    description = State()
"""

    replacement = """class AddAnime(StatesGroup):
    title = State()
    description = State()


class EditAnime(StatesGroup):
    anime_id = State()
    title = State()
    description = State()
"""

    if marker not in text:
        print("❌ AddAnime state topilmadi")
        raise SystemExit

    text = text.replace(marker, replacement)
    print("✅ EditAnime state qo‘shildi")


# =========================================================
# 2. ESKI ANIME EDIT/DELETE HANDLERLARNI OLIB TASHLASH
# =========================================================

start_marker = '@dp.callback_query(F.data == "anime_edit")'
end_marker = '# ==================================================\n# QISMLAR BOSHQARUVI'

start = text.find(start_marker)
end = text.find(end_marker)

if start != -1 and end != -1:

    text = text[:start] + text[end:]

    print("✅ Eski anime edit/delete handlerlar olib tashlandi")

else:

    print("ℹ️ Eski anime edit/delete handlerlar topilmadi")


# =========================================================
# 3. YANGI ANIME EDIT/DELETE
# =========================================================

anime_management_code = r'''
# ==================================================
# ANIME TAHRIRLASH / O‘CHIRISH
# ==================================================

@dp.callback_query(F.data == "anime_edit")
async def anime_edit_start(
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
            "❌ Hozircha anime yo‘q!",
            show_alert=True
        )

        return

    buttons = []

    for anime_id, title in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {title}",
                callback_data=f"anime_edit_{anime_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Anime boshqaruvi",
            callback_data="admin_anime"
        )
    ])

    await callback.message.edit_text(
        "✏️ <b>ANIME TAHRIRLASH</b>\n\n"
        "O‘zgartirmoqchi bo‘lgan animeni tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
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
        callback.data.replace(
            "anime_edit_",
            ""
        )
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT title, description
            FROM animes
            WHERE id = ?
              AND is_active = 1
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
        old_title=row[0],
        old_description=row[1] or ""
    )

    await state.set_state(
        EditAnime.title
    )

    await callback.message.edit_text(
        "✏️ <b>ANIME TAHRIRLASH</b>\n\n"
        f"🎬 Hozirgi nomi: <b>{row[0]}</b>\n\n"
        "Yangi anime nomini yuboring:"
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
            "❌ Yangi nomni kiriting."
        )

        return

    await state.update_data(
        new_title=title
    )

    await state.set_state(
        EditAnime.description
    )

    await message.answer(
        "📝 <b>Yangi tavsifni yuboring:</b>\n\n"
        "Masalan:\n"
        "<code>Yangi tavsif</code>"
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
            "❌ Tavsifni kiriting."
        )

        return

    data = await state.get_data()

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            UPDATE animes
            SET title = ?,
                description = ?
            WHERE id = ?
            """,
            (
                data["new_title"],
                description,
                data["anime_id"]
            )
        )

        await db.commit()

    await state.clear()

    await message.answer(
        "✅ <b>ANIME MUVAFFAQIYATLI TAHRIRLANDI!</b>\n\n"
        f"🆔 ID: <code>{data['anime_id']}</code>\n"
        f"🎬 Nomi: <b>{data['new_title']}</b>\n"
        f"📝 Tavsifi: {description}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Yana tahrirlash",
                        callback_data="anime_edit"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎬 Anime boshqaruvi",
                        callback_data="admin_anime"
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


# ==================================================
# ANIME O‘CHIRISH
# ==================================================

@dp.callback_query(F.data == "anime_delete")
async def anime_delete_start(
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
            SELECT id, title
            FROM animes
            WHERE is_active = 1
            ORDER BY id DESC
            """
        )

        rows = await cursor.fetchall()

    if not rows:

        await callback.answer(
            "❌ Hozircha anime yo‘q!",
            show_alert=True
        )

        return

    buttons = []

    for anime_id, title in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {title}",
                callback_data=f"anime_delete_{anime_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Anime boshqaruvi",
            callback_data="admin_anime"
        )
    ])

    await callback.message.edit_text(
        "🗑 <b>ANIME O‘CHIRISH</b>\n\n"
        "O‘chirmoqchi bo‘lgan animeni tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
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
        callback.data.replace(
            "anime_delete_",
            ""
        )
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT title
            FROM animes
            WHERE id = ?
              AND is_active = 1
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

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, o‘chirish",
                    callback_data=f"anime_delete_confirm_{anime_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="anime_delete"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "⚠️ <b>TASDIQLASH</b>\n\n"
        f"🎬 Anime: <b>{row[0]}</b>\n"
        f"🆔 ID: <code>{anime_id}</code>\n\n"
        "Unga tegishli barcha qismlar ham o‘chiriladi.\n\n"
        "Haqiqatan o‘chirasizmi?",
        reply_markup=confirm_keyboard
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("anime_delete_confirm_")
)
async def anime_delete_confirmed(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "❌ Ruxsat yo‘q!",
            show_alert=True
        )
        return

    anime_id = int(
        callback.data.replace(
            "anime_delete_confirm_",
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

        anime_title = row[0]

        # Avval shu anime qismlarini o‘chiramiz
        await db.execute(
            """
            DELETE FROM episodes
            WHERE anime_id = ?
            """,
            (anime_id,)
        )

        # Keyin animeni o‘chiramiz
        await db.execute(
            """
            DELETE FROM animes
            WHERE id = ?
            """,
            (anime_id,)
        )

        await db.commit()

    await callback.message.edit_text(
        "✅ <b>ANIME O‘CHIRILDI!</b>\n\n"
        f"🎬 {anime_title}\n"
        f"🆔 ID: <code>{anime_id}</code>\n\n"
        "📺 Unga tegishli qismlar ham o‘chirildi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Yana o‘chirish",
                        callback_data="anime_delete"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎬 Anime boshqaruvi",
                        callback_data="admin_anime"
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

    await callback.answer()


'''

# =========================================================
# 4. QISMLAR BOSHQARUVIDAN OLDIN JOYLASH
# =========================================================

marker = "# ==================================================\n# QISMLAR BOSHQARUVI"

if marker not in text:
    print("❌ QISMLAR BOSHQARUVI marker topilmadi")
    raise SystemExit

if "async def anime_edit_start(" not in text:

    pos = text.find(marker)

    text = (
        text[:pos]
        + anime_management_code
        + "\n"
        + text[pos:]
    )

    print("✅ Anime edit/delete tizimi qo‘shildi")

else:

    print("ℹ️ Anime edit/delete allaqachon mavjud")


# =========================================================
# 5. SAQLASH
# =========================================================

path.write_text(
    text,
    encoding="utf-8"
)

print("✅ bot.py saqlandi")
