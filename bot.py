import os
import sqlite3
import asyncio
import logging
from datetime import date
from collections import Counter

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ==============================
# НАСТРОЙКИ
# ==============================

TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "lucky_sticker.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ==============================
# БАЗА ДАННЫХ
# ==============================

def init_db():
    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                coins INTEGER DEFAULT 0,
                bonus_date TEXT DEFAULT ''
            )
        """)
        db.commit()


def update_user(user):
    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            INSERT INTO users (user_id, name)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET name = excluded.name
        """, (user.id, user.first_name or "Игрок"))
        db.commit()


def get_user(user_id):
    with sqlite3.connect(DB_NAME) as db:
        return db.execute(
            "SELECT coins, bonus_date FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()


def add_coins(user_id, amount):
    with sqlite3.connect(DB_NAME) as db:
        db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        db.commit()


# ==============================
# ТАБЛИЦА 64 КОМБИНАЦИЙ
# ==============================

SYMBOLS = ["BAR", "🍇", "🍋", "7"]

SLOT_POINTS = [
    40, 2, 2, 2, 2, 2, 1, 1,
    2, 1, 2, 1, 2, 1, 1, 2,
    2, 2, 1, 1, 2, 15, 2, 2,
    1, 2, 2, 1, 1, 2, 1, 2,
    2, 1, 2, 1, 1, 2, 2, 1,
    2, 2, 15, 2, 1, 1, 2, 2,
    2, 1, 1, 2, 1, 2, 1, 2,
    1, 1, 2, 2, 2, 2, 2, 100
]

SLOT_COMBINATIONS = {}

number = 1

for third in SYMBOLS:
    for second in SYMBOLS:
        for first in SYMBOLS:
            SLOT_COMBINATIONS[number] = {
                "combination": (first, second, third),
                "points": SLOT_POINTS[number - 1]
            }
            number += 1


# ==============================
# КЛАВИАТУРЫ
# ==============================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎮 Играть", callback_data="games"),
        ],
        [
            InlineKeyboardButton("🎁 Бонус", callback_data="bonus"),
            InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        ],
        [
            InlineKeyboardButton("🏆 Рейтинг", callback_data="top"),
        ],
    ])


def games_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏀 Баскетбол", callback_data="game:basketball"),
            InlineKeyboardButton("🎳 Боулинг", callback_data="game:bowling"),
        ],
        [
            InlineKeyboardButton("🎲 Кубик", callback_data="game:dice"),
            InlineKeyboardButton("🎯 Дартс", callback_data="game:darts"),
        ],
        [
            InlineKeyboardButton("🎰 Слоты", callback_data="game:slots"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="menu"),
        ]
    ])


def count_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 запуск", callback_data="count:1"),
            InlineKeyboardButton("3 запуска", callback_data="count:3"),
        ],
        [
            InlineKeyboardButton("5 запусков", callback_data="count:5"),
            InlineKeyboardButton("10 запусков", callback_data="count:10"),
        ],
        [
            InlineKeyboardButton("100 запусков", callback_data="count:100"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="games"),
        ]
    ])


# ==============================
# КОМАНДА START
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user(user)

    await update.message.reply_text(
        f"👋 Добро пожаловать, {user.first_name}!\n\n"
        "🎮 Добро пожаловать в Lucky Sticker!\n\n"
        "Здесь тебя ждут игры, бонусы и рейтинг игроков.\n\n"
        "🎁 Ежедневный бонус: +50 очков\n"
        "♾️ Бесплатные игровые попытки\n\n"
        "Выбирай действие:",
        reply_markup=main_keyboard()
    )


# ==============================
# ИГРЫ
# ==============================

GAME_NAMES = {
    "basketball": ("🏀 Баскетбол", "🏀"),
    "bowling": ("🎳 Боулинг", "🎳"),
    "dice": ("🎲 Кубик", "🎲"),
    "darts": ("🎯 Дартс", "🎯"),
    "slots": ("🎰 Слоты", "🎰"),
}


async def play_game(update, context, game, count):
    query = update.callback_query
    user_id = query.from_user.id

    if context.user_data.get("playing"):
        await query.message.reply_text("⏳ Твоя игра уже выполняется.")
        return

    context.user_data["playing"] = True

    emoji = GAME_NAMES[game][1]

    total_points = 0
    results = Counter()
    slot_details = Counter()

    await query.message.reply_text(
        f"🎮 Начинаем игру!\n"
        f"Игра: {GAME_NAMES[game][0]}\n"
        f"Количество запусков: {count}\n\n"
        "Следи за результатами!"
    )

    try:
        for i in range(count):
            result_message = await context.bot.send_dice(
                chat_id=query.message.chat_id,
                emoji=emoji
            )

            value = result_message.dice.value

            if game == "slots":
                slot = SLOT_COMBINATIONS[value]
                combination = slot["combination"]
                points = slot["points"]

                combination_text = " – ".join(combination)

                total_points += points
                slot_details[(combination_text, points)] += 1

            else:
                points = value * 5
                total_points += points
                results[value] += 1

            if i < count - 1:
                await asyncio.sleep(1.1)

        add_coins(user_id, total_points)

        summary = (
            "🏁 ИГРА ЗАВЕРШЕНА!\n\n"
            f"🎮 Игра: {GAME_NAMES[game][0]}\n"
            f"🔢 Запусков: {count}\n"
            f"⭐ Получено очков: {total_points}\n\n"
        )

        if game == "slots":
            summary += "📊 РЕЗУЛЬТАТЫ КОМБИНАЦИЙ:\n"

            for (combination, points), amount in sorted(
                slot_details.items()
            ):
                summary += (
                    f"\n{combination} — {points} очков"
                    f" × {amount}"
                )
        else:
            summary += "📊 РЕЗУЛЬТАТЫ:\n"

            for value, amount in sorted(results.items()):
                summary += (
                    f"\nВыпало {value} — {amount} раз"
                )

        await query.message.reply_text(
            summary,
            reply_markup=main_keyboard()
        )

    except Exception:
        logging.exception("Ошибка во время игры")
        await query.message.reply_text(
            "⚠️ Произошла ошибка во время игры. Попробуй позже.",
            reply_markup=main_keyboard()
        )

    finally:
        context.user_data["playing"] = False


# ==============================
# БОНУС
# ==============================

async def bonus(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    today = date.today().isoformat()
    data = get_user(user_id)

    if data is None:
        update_user(query.from_user)
        data = get_user(user_id)

    if data[1] == today:
        await query.message.reply_text(
            "⏳ Ты уже получил сегодняшний бонус!",
            reply_markup=main_keyboard()
        )
        return

    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            UPDATE users
            SET coins = coins + 50, bonus_date = ?
            WHERE user_id = ?
        """, (today, user_id))
        db.commit()

    await query.message.reply_text(
        "🎁 БОНУС ПОЛУЧЕН!\n\n"
        "⭐ Тебе начислено 50 очков!\n"
        "Возвращайся завтра за новым бонусом.",
        reply_markup=main_keyboard()
    )


# ==============================
# ПРОФИЛЬ
# ==============================

async def profile(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    data = get_user(user_id)

    if data is None:
        update_user(query.from_user)
        data = get_user(user_id)

    await query.message.reply_text(
        "👤 ТВОЙ ПРОФИЛЬ\n\n"
        f"Имя: {query.from_user.first_name}\n"
        f"ID: {user_id}\n"
        f"⭐ Баланс: {data[0]} очков",
        reply_markup=main_keyboard()
    )


# ==============================
# РЕЙТИНГ
# ==============================

async def top(update, context):
    query = update.callback_query

    with sqlite3.connect(DB_NAME) as db:
        users = db.execute("""
            SELECT name, coins
            FROM users
            ORDER BY coins DESC
            LIMIT 10
        """).fetchall()

    text = "🏆 ТОП-10 ИГРОКОВ\n\n"

    if not users:
        text += "Пока игроков нет."
    else:
        for i, (name, coins) in enumerate(users, 1):
            text += f"{i}. {name} — {coins} ⭐\n"

    await query.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# ==============================
# ОБРАБОТЧИК КНОПОК
# ==============================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    update_user(user)

    data = query.data

    if data == "menu":
        await query.message.reply_text(
            "🏠 Главное меню",
            reply_markup=main_keyboard()
        )

    elif data == "games":
        await query.message.reply_text(
            "🎮 ВЫБЕРИ ИГРУ:",
            reply_markup=games_keyboard()
        )

    elif data.startswith("game:"):
        game = data.split(":")[1]

        context.user_data["selected_game"] = game

        await query.message.reply_text(
            f"🎮 Выбрана игра: {GAME_NAMES[game][0]}\n\n"
            "Выбери количество бесплатных запусков:",
            reply_markup=count_keyboard()
        )

    elif data.startswith("count:"):
        count = int(data.split(":")[1])
        game = context.user_data.get("selected_game")

        if game not in GAME_NAMES:
            await query.message.reply_text(
                "Сначала выбери игру.",
                reply_markup=games_keyboard()
            )
            return

        await play_game(update, context, game, count)

    elif data == "bonus":
        await bonus(update, context)

    elif data == "profile":
        await profile(update, context)

    elif data == "top":
        await top(update, context)


# ==============================
# КОМАНДЫ
# ==============================

async def games_command(update, context):
    update_user(update.effective_user)

    await update.message.reply_text(
        "🎮 ВЫБЕРИ ИГРУ:",
        reply_markup=games_keyboard()
    )


async def bonus_command(update, context):
    update_user(update.effective_user)

    class FakeQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user

    class FakeUpdate:
        def __init__(self, message):
            self.callback_query = FakeQuery(message)

    await bonus(FakeUpdate(update.message), context)


async def profile_command(update, context):
    update_user(update.effective_user)

    class FakeQuery:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user

    class FakeUpdate:
        def __init__(self, message):
            self.callback_query = FakeQuery(message)

    await profile(FakeUpdate(update.message), context)


async def top_command(update, context):
    class FakeQuery:
        def __init__(self, message):
            self.message = message

    class FakeUpdate:
        def __init__(self, message):
            self.callback_query = FakeQuery(message)

    await top(FakeUpdate(update.message), context)


# ==============================
# ЗАПУСК
# ==============================

def main():
    if not TOKEN:
        raise RuntimeError(
            "Не найдена переменная окружения BOT_TOKEN"
        )

    init_db()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("games", games_command))
    application.add_handler(CommandHandler("bonus", bonus_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("top", top_command))

    application.add_handler(
        CallbackQueryHandler(buttons)
    )

    print("Lucky Sticker запущен!")

    application.run_polling()


if __name__ == "__main__":
    main()




