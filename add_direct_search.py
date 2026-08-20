from pathlib import Path

path = Path("bot.py")
text = path.read_text(encoding="utf-8")

# Eski ID handler nomini boshqa nomga o'zgartiramiz
text = text.replace(
    '@dp.message()\nasync def other_messages(message: Message):',
    '@dp.message()\nasync def other_messages(message: Message):'
)

# ============================================================
# ID SEARCH HANDLERNI MAIN DAN OLDIN JOYLASH
# ============================================================

marker = "# ==================================================\n# MAIN"

if marker not in text:
    print("❌ MAIN marker topilmadi")
    raise SystemExit

# Agar oldin qo'shilgan bo'lsa, qayta qo'shmaymiz
if "async def direct_episode_search(" not in text:

    code = r'''
# ==================================================
# DIRECT EPISODE ID SEARCH
# ==================================================

@dp.message(F.text.regexp(r"^\d+$"))
async def direct_episode_search(message: Message):

    episode_id = int(message.text.strip())

    print(
        f"🔎 ID qidiruv: user={message.from_user.id} "
        f"episode_id={episode_id}"
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT
                episodes.id,
                episodes.episode_number,
                episodes.title,
                episodes.video_file_id,
                animes.title
            FROM episodes
            INNER JOIN animes
                ON animes.id = episodes.anime_id
            WHERE episodes.id = ?
            LIMIT 1
            """,
            (episode_id,)
        )

        row = await cursor.fetchone()

    if row is None:

        await message.answer(
            "❌ <b>Bunday qism ID topilmadi.</b>\n\n"
            f"🔎 ID: <code>{episode_id}</code>"
        )

        return

    db_episode_id = row[0]
    episode_number = row[1]
    episode_title = row[2]
    video_file_id = row[3]
    anime_title = row[4]

    caption = (
        f"🎬 <b>{anime_title}</b>\n"
        f"📺 <b>{episode_number}-qism</b>\n"
        f"📝 {episode_title}\n\n"
        f"🆔 ID: <code>{db_episode_id}</code>"
    )

    print(
        f"✅ Qism topildi: {anime_title} / "
        f"{episode_number}-qism"
    )

    try:

        await message.answer_video(
            video=video_file_id,
            caption=caption
        )

        print("✅ Video yuborildi")

    except Exception as e:

        print(
            f"❌ Telegram video yuborishda xato: {e}"
        )

        await message.answer(
            "❌ Video yuborishda xatolik yuz berdi.\n\n"
            "Terminaldagi xatoni tekshiring."
        )

'''

    pos = text.find(marker)

    text = text[:pos] + code + "\n" + text[pos:]

    print("✅ Direct ID search qo'shildi")

else:

    print("ℹ️ Direct ID search allaqachon mavjud")

path.write_text(text, encoding="utf-8")

print("✅ bot.py saqlandi")
