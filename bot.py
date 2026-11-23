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


def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Играть", callback_data="tiers")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ Добро пожаловать в Lucky Sticker!\n\n"
        "Выбирай количество игр и развлекайся!",
        reply_markup=menu()
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "tiers":
        keyboard = [
            [InlineKeyboardButton("1 игра", callback_data="tier:1")],
            [InlineKeyboardButton("3 игры", callback_data="tier:3")],
            [InlineKeyboardButton("5 игр", callback_data="tier:5")],
            [InlineKeyboardButton("10 игр", callback_data="tier:10")],
            [InlineKeyboardButton("100 игр", callback_data="tier:100")],
        ]

        await query.edit_message_text(
            "Выбери количество игр:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("tier:"):
        context.user_data["rounds"] = int(data.split(":")[1])

        keyboard = [
            [InlineKeyboardButton("🏀 Баскетбол", callback_data="game:basketball")],
            [InlineKeyboardButton("🎳 Боулинг", callback_data="game:bowling")],
            [InlineKeyboardButton("🎲 Кубики", callback_data="game:dice")],
            [InlineKeyboardButton("🎯 Дартс", callback_data="game:darts")],
        ]

        await query.edit_message_text(
            "Выбери игру:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("game:"):
        user_id = query.from_user.id

        if user_id in active_users:
            await query.answer("Дождись окончания предыдущей игры!")
            return

        game = data.split(":")[1]
        rounds = context.user_data.get("rounds", 1)

        emoji, name = GAMES[game]
        active_users.add(user_id)

        await query.edit_message_text(
            f"🎮 Запускаю: {name}\n"
            f"Количество игр: {rounds}\n\n"
            "Результаты появятся в чате."
        )

        context.application.create_task(
            play_games(context.bot, query.message.chat_id,
                       rounds, emoji, user_id)
        )

async def play_games(bot, chat_id, rounds, emoji, user_id):
    try:
        for i in range(rounds):
            result = await bot.send_dice(
                chat_id=chat_id,
                emoji=emoji
            )

            points = result.dice.value

            await asyncio.sleep(2)

            await bot.send_message(
                chat_id=chat_id,
                text=f"🎯 Результат броска №{i + 1}: {points}"
            )

            if i < rounds - 1:
                await asyncio.sleep(1)

        await bot.send_message(
            chat_id=chat_id,
            text=f"✅ Все готово! Проведено игр: {rounds}"
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
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)

    future = asyncio.run_coroutine_threadsafe(
        application.update_queue.put(update),
        loop
    )
    future.result(timeout=10)

    return "OK"


def run_bot():
    global loop

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    loop.run_until_complete(
        application.bot.set_webhook(URL + "/webhook")
    )

    ready.set()
    loop.run_forever()


if __name__ == "__main__":
    if not TOKEN or not URL:
        raise RuntimeError("Проверь BOT_TOKEN и RENDER_EXTERNAL_URL")

    threading.Thread(target=run_bot, daemon=True).start()

    if not ready.wait(timeout=30):
        raise RuntimeError("Бот не запустился")

    serve(app, host="0.0.0.0", port=PORT)
