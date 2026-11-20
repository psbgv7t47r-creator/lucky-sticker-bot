
import os
import sqlite3
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
DB = "lucky_sticker.db"

# Database
def setup_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 0,
            bonus_date TEXT DEFAULT ''
        )
    """)
    con.commit()
    con.close()


def get_user(user_id, name):
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
        (user_id, name)
    )
    con.execute(
        "UPDATE users SET name=? WHERE user_id=?",
        (name, user_id)
    )
    con.commit()
    user = con.execute(
        "SELECT coins, bonus_date FROM users WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()
    return user


def add_coins(user_id, amount):
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE users SET coins=coins+? WHERE user_id=?",
        (amount, user_id)
    )
    con.commit()
    con.close()


def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎲 Кубики", callback_data="dice"),
            InlineKeyboardButton("🎯 Дартс", callback_data="dart")
        ],
        [
            InlineKeyboardButton("🏀 Баскетбол", callback_data="basket"),
            InlineKeyboardButton("🎳 Боулинг", callback_data="bowl")
        ],
        [
            InlineKeyboardButton("🎁 Бонус", callback_data="bonus"),
            InlineKeyboardButton("👤 Профиль", callback_data="profile")
        ],
        [
            InlineKeyboardButton("🏆 Рейтинг", callback_data="top")
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.first_name)

    await update.message.reply_text(
        "🎰 LUCKY STICKER\n\n"
        "Добро пожаловать!\n"
        "Играй, собирай монеты и попадай в рейтинг!\n\n"
        "Выбирай игру:",
        reply_markup=menu()
    )


async def games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Выбирай игру:",
        reply_markup=menu()
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    get_user(user.id, user.first_name)

    action = query.data

    if action == "profile":
        coins, _ = get_user(user.id, user.first_name)
        await query.message.reply_text(
            f"👤 Твой профиль\n\n"
            f"Имя: {user.first_name}\n"
            f"🪙 Монеты: {coins}"
        )

    elif action == "bonus":
        con = sqlite3.connect(DB)
        today = date.today().isoformat()

        last = con.execute(
            "SELECT bonus_date FROM users WHERE user_id=?",
            (user.id,)
        ).fetchone()[0]

        if last == today:
            message = "🎁 Ты уже получил сегодняшний бонус!"
        else:
            con.execute(
                "UPDATE users SET coins=coins+50, bonus_date=? WHERE user_id=?",
                (today, user.id)
            )
            con.commit()
            message = "🎁 Ежедневный бонус получен!\n\n🪙 +50 монет"

        con.close()
        await query.message.reply_text(message)

    elif action == "top":
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT name, coins FROM users ORDER BY coins DESC LIMIT 10"
        ).fetchall()
        con.close()

        text = "🏆 ТОП ИГРОКОВ\n\n"
        for i, (name, coins) in enumerate(rows, 1):
            text += f"{i}. {name} — 🪙 {coins}\n"

        await query.message.reply_text(text)

    else:
        games_data = {
            "dice": ("🎲", "Кубики"),
            "dart": ("🎯", "Дартс"),
            "basket": ("🏀", "Баскетбол"),
            "bowl": ("🎳", "Боулинг")
        }

        if action not in games_data:
            return

        emoji, title = games_data[action]

        await query.message.reply_text(f"{title} — твой ход!")

        result = await context.bot.send_dice(
            chat_id=query.message.chat_id,
            emoji=emoji
        )

        points = result.dice.value * 5
        add_coins(user.id, points)

        await query.message.reply_text(
            f"🍀 Результат: {result.dice.value}\n\n"
            f"🪙 Получено: +{points} монет\n"
            f"Продолжай играть!",
            reply_markup=menu()
        )


async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await button(update, context)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    coins, _ = get_user(user.id, user.first_name)
    await update.message.reply_text(f"👤 Профиль\n🪙 Монеты: {coins}")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT name, coins FROM users ORDER BY coins DESC LIMIT 10"
    ).fetchall()
    con.close()

    text = "🏆 Рейтинг:\n\n"
    for i, (name, coins) in enumerate(rows, 1):
        text += f"{i}. {name} — {coins} 🪙\n"

    await update.message.reply_text(text)


def main():
    if not TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")

    setup_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("games", games))
    app.add_handler(CommandHandler("bonus", bonus))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CallbackQueryHandler(button))

    print("Lucky Sticker запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()

