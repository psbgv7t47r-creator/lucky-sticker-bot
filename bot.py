import os
import sqlite3
from datetime import date
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
URL = os.getenv("RENDER_EXTERNAL_URL")
DB = "lucky_sticker.db"

app_web = Flask(__name__)
bot_app = None


def setup_db():
    with sqlite3.connect(DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                coins INTEGER DEFAULT 0,
                bonus_date TEXT DEFAULT ''
            )
        """)


def get_user(user_id, name):
    with sqlite3.connect(DB) as con:
        con.execute(
            "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
            (user_id, name)
        )
        con.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))
        row = con.execute(
            "SELECT coins, bonus_date FROM users WHERE user_id=?",
            (user_id,)
        ).fetchone()
        return row


def add_coins(user_id, amount):
    with sqlite3.connect(DB) as con:
        con.execute(
            "UPDATE users SET coins=coins+? WHERE user_id=?",
            (amount, user_id)
        )


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
        [InlineKeyboardButton("🏆 Рейтинг", callback_data="top")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.first_name)
    await update.message.reply_text(
        "🍀 LUCKY STICKER\n\n"
        "Добро пожаловать в мини-игры!\n"
        "Играй, собирай виртуальные очки и открывай достижения.\n\n"
        "Выбирай игру:",
        reply_markup=menu()
    )


async def games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 Выбирай игру:", reply_markup=menu())


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    get_user(user.id, user.first_name)
    action = query.data

    if action == "profile":
        coins, _ = get_user(user.id, user.first_name)
        await query.message.reply_text(
            f"👤 Профиль\nИмя: {user.first_name}\n⭐ Очки: {coins}"
        )

    elif action == "bonus":
        with sqlite3.connect(DB) as con:
            today = date.today().isoformat()
            row = con.execute(
                "SELECT bonus_date FROM users WHERE user_id=?",
                (user.id,)
            ).fetchone()
            if row[0] == today:
                message = "🎁 Сегодняшняя отметка уже получена!"
            else:
                con.execute(
                    "UPDATE users SET coins=coins+10, bonus_date=? WHERE user_id=?",
                    (today, user.id)
                )
                message = "🎁 Ежедневная отметка получена! +10 очков."
        await query.message.reply_text(message, reply_markup=menu())

    elif action == "top":
        with sqlite3.connect(DB) as con:
            rows = con.execute(
                "SELECT name, coins FROM users ORDER BY coins DESC LIMIT 10"
            ).fetchall()
        text = "🏆 ТОП ИГРОКОВ\n\n"
        for i, (name, coins) in enumerate(rows, 1):
            text += f"{i}. {name} — ⭐ {coins}\n"
        await query.message.reply_text(text or "Пока игроков нет.")

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
        points = result.dice.value
        add_coins(user.id, points)
        await query.message.reply_text(
            f"Результат: {result.dice.value}\n⭐ Получено очков: +{points}",
            reply_markup=menu()
        )


async def setup_bot():
    global bot_app
    setup_db()
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("games", games))
    bot_app.add_handler(CallbackQueryHandler(button))

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(f"{URL}/webhook")


@app_web.route("/", methods=["GET"])
def home():
    return "Lucky Sticker is running!"


@app_web.route("/webhook", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return "OK"


if __name__ == "__main__":
    import asyncio
    from threading import Thread
    from waitress import serve

    asyncio.run(setup_bot())
    serve(app_web, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

