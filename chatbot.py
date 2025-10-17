import os
import asyncio
import sys
import json
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
import g4f

# --- Bot sozlamalari ---
API_TOKEN = "8317894534:AAGPx7Fh6UqQ6TJhtjIiZSkxgonjreUYT6A"
LOG_FILE = "logs.txt"

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# Har bir foydalanuvchi uchun chat tarixini saqlash
user_chat_histories = {}

# =====================================================
# --- FUNKSIYALAR ---
# =====================================================

def extract_content(raw_response: str) -> str:
    """G4F dan kelgan xom javobdan faqat 'content' qismini ajratadi."""
    if not raw_response:
        return ""
    try:
        if raw_response.strip().startswith("{"):
            data = json.loads(raw_response)
            return data["choices"][0]["message"]["content"].strip().replace("\\n", "\n")
    except Exception:
        pass

    match = re.search(r"'content':\s*'([^']+)'", raw_response)
    if match:
        return match.group(1).strip().replace("\\n", "\n")

    parts = raw_response.split("}")
    if len(parts) > 1:
        return parts[-1].strip().replace("\\n", "\n")

    return str(raw_response).strip().replace("\\n", "\n")


def get_user_chat_history(user_id: int):
    """Foydalanuvchi chat tarixini olish"""
    if user_id not in user_chat_histories:
        user_chat_histories[user_id] = []
    return user_chat_histories[user_id]


def add_to_chat_history(user_id: int, role: str, content: str):
    """Chat tarixiga qo'shish"""
    history = get_user_chat_history(user_id)
    history.append({"role": role, "content": content})

    # Chat tarixini 8 ta xabar bilan cheklaymiz
    if len(history) > 8:
        user_chat_histories[user_id] = history[-8:]


def clear_chat_history(user_id: int):
    """Chat tarixini tozalash"""
    if user_id in user_chat_histories:
        user_chat_histories[user_id] = []

# =====================================================
# --- HANDLERLAR ---
# =====================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    clear_chat_history(message.from_user.id)
    await message.answer(
        f"👋 Salom, *{message.from_user.first_name or 'foydalanuvchi'}!* \n"
        "Men AI yordamchisiman. Menga savolingizni matn shaklida yozing!\n\n"
        "💡 *Eslatma:* Men avvalgi xabarlaringizni eslayman va kontekstni tushunaman.\n"
        "🔄 Yangi suhbat boshlash uchun /clear buyrug'ini yuboring. Creator bot: @Tamerkhan"
    )


@dp.message(Command("clear"))
async def clear_handler(message: types.Message):
    clear_chat_history(message.from_user.id)
    await message.answer("🔄 Chat tarixi tozalandi! Endi yangi suhbat boshlanadi.")


@dp.message()
async def handle_message(message: types.Message):
    # 1️⃣ Xabar turi — matn ekanligini tekshiramiz
    if message.content_type != "text" or not message.text:
        await message.answer("🤖 Hozircha faqat matnli xabarlarni tushunaman. Iltimos, matn yuboring.")
        return

    text = message.text.strip()
    if not text:
        await message.answer("⚠️ Bo‘sh matn yuborildi. Iltimos, biror narsa yozing.")
        return

    # 2️⃣ /clear komandasi
    if text.lower() in ["/clear", "/new", "/yangi"]:
        clear_chat_history(message.from_user.id)
        await message.answer("🔄 Chat tarixi tozalandi! Endi yangi suhbat boshlanadi.")
        return

    # 3️⃣ Javob tayyorlanmoqda
    await bot.send_chat_action(message.chat.id, "typing")
    answer = ""

    try:
        # Tarixni olish
        chat_history = get_user_chat_history(message.from_user.id)
        messages_to_send = chat_history + [{"role": "user", "content": text}]

        print(f"📨 User {message.from_user.id} uchun {len(messages_to_send)} ta xabar yuborilmoqda")

        # GPT-4 modelidan foydalanish
        try:
            response = await asyncio.to_thread(
                g4f.ChatCompletion.create,
                model=g4f.models.gpt_4,
                messages=messages_to_send,
                timeout=120
            )
            answer = extract_content(str(response))
            print(f"✅ GPT-4 javobi olindi: {answer[:100]}...")
        except Exception as e:
            print(f"❌ GPT-4 xatosi: {e}")
            # GPT-3.5 bilan urinib ko‘ramiz
            try:
                response = await asyncio.to_thread(
                    g4f.ChatCompletion.create,
                    model=g4f.models.gpt_35_turbo,
                    messages=messages_to_send,
                    timeout=120
                )
                answer = extract_content(str(response))
                print(f"✅ GPT-3.5 javobi olindi: {answer[:100]}...")
            except Exception as e2:
                print(f"❌ GPT-3.5 xatosi: {e2}")
                answer = f"❌ Texnik xatolik: {str(e2)}"

        # Tarixga qo‘shish
        if answer and not answer.startswith("❌"):
            add_to_chat_history(message.from_user.id, "user", text)
            add_to_chat_history(message.from_user.id, "assistant", answer)
            print(f"💾 Chat tarixi yangilandi: {len(get_user_chat_history(message.from_user.id))} ta xabar")

    except Exception as e:
        print(f"❌ Umumiy xatolik: {e}")
        answer = f"❌ Xatolik yuz berdi: {str(e)}"

    # Agar javob bo‘sh bo‘lsa
    if not answer or not answer.strip():
        answer = "⚠️ Javob topilmadi. Iltimos, qaytadan urinib ko‘ring."

    # Log yozish
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n"
            f"👤 {message.from_user.full_name} ({message.from_user.id}): {text}\n"
            f"🤖 {answer}\n"
            f"📊 Tarixdagi xabarlar: {len(get_user_chat_history(message.from_user.id))}\n"
        )

    await message.answer(answer, parse_mode=ParseMode.MARKDOWN)

# =====================================================
# --- MAIN ---
# =====================================================

async def main():
    print("🤖 Bot ishga tushdi. AI kontekstni eslab qoladi.")
    print("💡 /clear - yangi suhbat boshlash")
    await dp.start_polling(bot)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

