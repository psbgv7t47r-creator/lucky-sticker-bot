
import os
import asyncio
import threading

from flask import Flask, request
from waitress import serve

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN")
URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", 10000))

app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

loop = None
ready = threading.Event()
active_users = set()

GAMES = {
    "basketball": ("🏀", "Баскетбол"),
    "bowling": ("🎳", "Боулинг"),
    "dice": ("🎲", "Кубики"),
    "darts": ("🎯", "Дартс")
}

TIERS = [1, 3, 5, 10, 100]


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Играть", callback_data="tiers")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ Добро пожаловать в Lucky Sticker!\n\n"
        "Выбирай количество игр и начинай!",
        reply_markup=main_menu()
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "tiers":
        keyboard = [
            [InlineKeyboardButton(
                f"🎮 {n} игр",
                callback_data=f"tier:{n}"
            )]
            for n in TIERS
        ]

        keyboard.append([
            InlineKeyboardButton("⬅️ Главное меню", callback_data="home")
        ])

        await query.edit_message_text(
            "Выбери количество игр:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "home":
        await query.edit_message_text(
            "⭐ Lucky Sticker\n\nГлавное меню:",
            reply_markup=main_menu()
        )

    elif data.startswith("tier:"):
        rounds = int(data.split(":")[1])
        context.user_data["rounds"] = rounds

        keyboard = [
            [InlineKeyboardButton(
                f"{emoji} {name}",
                callback_data=f"game:{key}"
            )]
            for key, (emoji, name) in GAMES.items()
        ]

        keyboard.append([
            InlineKeyboardButton("⬅️ Назад", callback_data="tiers")
        ])

        await query.edit_message_text(
            f"Выбрано игр: {rounds}\n\nВыбери игру:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("game:"):
        user_id = query.from_user.id

        if user_id in active_users:
            await query.answer("Дождись окончания текущей серии!")
            return

        game = data.split(":")[1]

        if game not in GAMES:
            return

        rounds = context.user_data.get("rounds", 1)
        emoji, name = GAMES[game]

        active_users.add(user_id)

        await query.edit_message_text(
            f"🎮 Игра: {name}\n"
            f"Количество попыток: {rounds}\n\n"
            "Начинаем!"
        )

        context.application.create_task(
            play_games(
                context.bot,
                query.message.chat_id,
                rounds,
                emoji,
                name,
                user_id
            )
        )


async def play_games(bot, chat_id, rounds, emoji, name, user_id):
    total_points = 0

    try:
        for i in range(rounds):
            result = await bot.send_dice(
                chat_id=chat_id,
                emoji=emoji
            )

            points = result.dice.value
            total_points += points

            await asyncio.sleep(2)

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"{emoji} {name}\n"
                    f"🎯 Игра №{i + 1}\n"
                    f"⭐ Выпало очков: {points}"
                )
            )

            if i < rounds - 1:
                await asyncio.sleep(1)

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ Серия завершена!\n\n"
                f"🎮 Игр сыграно: {rounds}\n"
                f"⭐ Всего очков: {total_points}\n"
                f"📊 Среднее количество очков: "
                f"{total_points / rounds:.2f}"
            ),
            reply_markup=main_menu()
        )

    except Exception as error:
        print(f"Game error: {error}")
        await bot.send_message(
            chat_id=chat_id,
            text="Произошла ошибка во время игры."
        )

    finally:
        active_users.discard(user_id)


application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button))


@app.route("/")
def home():
    return "Lucky Sticker is running!"


@app.route("/webhook", methods=["POST"])
def webhook():
    if not application.running:
        return "Bot is not ready", 503

    data = request.get_json(silent=True)

    if not data:
        return "Invalid update", 400

    update = Update.de_json(data, application.bot)

    future = asyncio.run_coroutine_threadsafe(
        application.update_queue.put(update),
        loop
    )

    try:
        future.result(timeout=10)
    except Exception:
        return "Webhook error", 500

    return "OK", 200


def run_bot():
    global loop

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def setup():
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(URL + "/webhook")

    loop.run_until_complete(setup())
    ready.set()
    loop.run_forever()


if __name__ == "__main__":
    if not TOKEN or not URL:
        raise RuntimeError(
            "Проверь BOT_TOKEN и RENDER_EXTERNAL_URL"
        )

    threading.Thread(target=run_bot, daemon=True).start()

    if not ready.wait(timeout=30):
        raise RuntimeError("Bot startup timeout")

    serve(app, host="0.0.0.0", port=PORT)
