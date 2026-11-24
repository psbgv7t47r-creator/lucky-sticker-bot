import os
import sqlite3
import asyncio
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "lucky_sticker.db")

# Telegram technical results for 🎰, indexed from 1 to 64.
# This is the scoring table supplied for Lucky Sticker.
SLOT_POINTS = [
    40, 2, 2, 2, 2, 2, 1, 1,
    2, 1, 2, 1, 2, 1, 1, 2,
    2, 2, 1, 1, 2, 15, 2, 2,
    1, 2, 2, 1, 1, 2, 1, 2,
    2, 1, 2, 1, 1, 2, 2, 1,
    2, 2, 15, 2, 1, 1, 2, 2,
    2, 1, 1, 2, 1, 2, 1, 2,
    1, 1, 2, 2, 2, 2, 2, 100,
]

GAMES = {
    "dice": ("🎲", "Кубики"),
    "darts": ("🎯", "Дартс"),
    "basketball": ("🏀", "Баскетбол"),
    "bowling": ("🎳", "Боулинг"),
    "slots": ("🎰", "Слоты"),
}

COUNTS = (1, 3, 5, 10, 100)
DAILY_BONUS = 50
REGULAR_GAME_MULTIPLIER = 5


# =========================
# БАЗА ДАННЫХ
# =========================

def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                coins INTEGER NOT NULL DEFAULT 0,
                last_bonus TEXT
            )
        """)
        conn.commit()


def register_user(user):
    with db_connect() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user.id, user.username or "", user.first_name or "Игрок"))
        conn.commit()


def get_user(user_id):
    with db_connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def add_coins(user_id, amount):
    with db_connect() as conn:
        conn.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id),
        )
        conn.commit()


def claim_daily_bonus(user_id):
    today = date.today().isoformat()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT last_bonus FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row is None:
            return False

        if row["last_bonus"] == today:
            return False

        conn.execute("""
            UPDATE users
            SET coins = coins + ?, last_bonus = ?
            WHERE user_id = ?
        """, (DAILY_BONUS, today, user_id))
        conn.commit()
        return True


def get_top_users():
    with db_connect() as conn:
        return conn.execute("""
            SELECT first_name, username, coins
            FROM users
            ORDER BY coins DESC, user_id ASC
            LIMIT 10
        """).fetchall()


# =========================
# КЛАВИАТУРЫ
# =========================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎮 Игры", callback_data="games"),
            InlineKeyboardButton("🎁 Бонус", callback_data="bonus"),
        ],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="profile"),
            InlineKeyboardButton("🏆 Рейтинг", callback_data="top"),
        ],
    ])


def games_keyboard():
    rows = []
    for key, (emoji, title) in GAMES.items():
        rows.append([
            InlineKeyboardButton(
                f"{emoji} {title}",
                callback_data=f"game:{key}"
            )
        ])
    rows.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def counts_keyboard(game_key):
    rows = []
    for i in range(0, len(COUNTS), 2):
        row = [
            InlineKeyboardButton(
                f"{n} {'попытка' if n == 1 else 'попыток'}",
                callback_data=f"count:{game_key}:{n}"
            )
            for n in COUNTS[i:i + 2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ К играм", callback_data="games")])
    return InlineKeyboardMarkup(rows)


# =========================
# КОМАНДЫ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await update.message.reply_text(
        "⭐ Добро пожаловать в Lucky Sticker!\n\n"
        "Играй в мини-игры, зарабатывай виртуальные очки и попадай в рейтинг.\n"
        "Все попытки бесплатные. Очки существуют только внутри игры "
        "и не покупаются, не ставятся и не выводятся.",
        reply_markup=main_keyboard(),
    )


async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await update.message.reply_text(
        "Выбери игру:",
        reply_markup=games_keyboard(),
    )


async def bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await send_bonus(update, update.effective_user.id)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await send_profile(update, update.effective_user.id)


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await send_top(update)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — главное меню\n"
        "/games — список игр\n"
        "/bonus — ежедневный бонус\n"
        "/profile — профиль\n"
        "/top — рейтинг\n\n"
        "Попытки бесплатные и неограниченные. "
        "В боте нет денежных ставок, покупок очков или вывода денег.",
        reply_markup=main_keyboard(),
    )


# =========================
# ЭКРАНЫ
# =========================

async def send_bonus(target, user_id):
    if claim_daily_bonus(user_id):
        text = f"🎁 Ежедневный бонус получен: +{DAILY_BONUS} очков!"
    else:
        text = "⏳ Сегодня бонус уже получен. Возвращайся завтра!"
    if isinstance(target, Update):
        await target.message.reply_text(text, reply_markup=main_keyboard())
    else:
        await target.edit_message_text(text, reply_markup=main_keyboard())


async def send_profile(target, user_id):
    row = get_user(user_id)
    coins = row["coins"] if row else 0
    text = (
        "👤 ТВОЙ ПРОФИЛЬ\n\n"
        f"🆔 ID: {user_id}\n"
        f"⭐ Очки: {coins}"
    )
    if isinstance(target, Update):
        await target.message.reply_text(text, reply_markup=main_keyboard())
    else:
        await target.edit_message_text(text, reply_markup=main_keyboard())


async def send_top(target):
    rows = get_top_users()
    if not rows:
        text = "🏆 Рейтинг пока пуст."
    else:
        lines = ["🏆 ТОП-10 ИГРОКОВ\n"]
        for index, row in enumerate(rows, start=1):
            name = row["first_name"] or "Игрок"
            if row["username"]:
                name += f" (@{row['username']})"
            lines.append(f"{index}. {name} — {row['coins']} ⭐")
        text = "\n".join(lines)

    if isinstance(target, Update):
        await target.message.reply_text(text, reply_markup=main_keyboard())
    else:
        await target.edit_message_text(text, reply_markup=main_keyboard())


# =========================
# ИГРЫ
# =========================

async def play_series(query, context, game_key, count):
    user = query.from_user
    chat_id = query.message.chat_id
    emoji, game_name = GAMES[game_key]

    await query.edit_message_text(
        f"{emoji} Запускаю: {game_name}\n"
        f"Количество попыток: {count}\n\n"
        "Результаты появятся ниже."
    )

    total_points = 0
    result_lines = []

    for number in range(1, count + 1):
        try:
            sent = await context.bot.send_dice(chat_id=chat_id, emoji=emoji)
            value = sent.dice.value

            if game_key == "slots":
                points = SLOT_POINTS[value - 1]
            else:
                points = value * REGULAR_GAME_MULTIPLIER

            total_points += points
            result_lines.append(
                f"№{number}: результат {value} → +{points} ⭐"
            )

            # Показываем результаты порциями, чтобы серия из 100
            # попыток не создавала слишком много отдельных сообщений.
            if len(result_lines) == 10 or number == count:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="\n".join(result_lines),
                )
                result_lines.clear()

            if count >= 10:
                await asyncio.sleep(0.25)

        except Exception as exc:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ Не удалось завершить попытку №{number}.\n"
                    f"Ошибка: {type(exc).__name__}"
                ),
            )
            break

    add_coins(user.id, total_points)
    completed = number if "number" in locals() else 0
    average = total_points / completed if completed else 0

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ СЕРИЯ ЗАВЕРШЕНА\n\n"
            f"Игра: {emoji} {game_name}\n"
            f"Выполнено попыток: {completed}/{count}\n"
            f"Всего заработано: +{total_points} ⭐\n"
            f"Среднее за попытку: {average:.2f} ⭐\n\n"
            "Очки — только виртуальные игровые баллы."
        ),
        reply_markup=main_keyboard(),
    )


# =========================
# CALLBACK-КНОПКИ
# =========================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    register_user(query.from_user)

    data = query.data

    if data == "home":
        await query.edit_message_text(
            "⭐ Главное меню Lucky Sticker",
            reply_markup=main_keyboard(),
        )
        return

    if data == "games":
        await query.edit_message_text(
            "🎮 Выбери игру:",
            reply_markup=games_keyboard(),
        )
        return

    if data == "bonus":
        await send_bonus(query, query.from_user.id)
        return

    if data == "profile":
        await send_profile(query, query.from_user.id)
        return

    if data == "top":
        await send_top(query)
        return

    if data.startswith("game:"):
        game_key = data.split(":", 1)[1]
        if game_key not in GAMES:
            await query.edit_message_text("Неизвестная игра.")
            return

        emoji, title = GAMES[game_key]
        await query.edit_message_text(
            f"{emoji} Игра: {title}\n\nВыбери количество бесплатных попыток:",
            reply_markup=counts_keyboard(game_key),
        )
        return

    if data.startswith("count:"):
        _, game_key, count_text = data.split(":")
        if game_key not in GAMES:
            await query.edit_message_text("Неизвестная игра.")
            return

        count = int(count_text)
        if count not in COUNTS:
            await query.edit_message_text("Неверное количество попыток.")
            return

        await play_series(query, context, game_key, count)
        return


# =========================
# ЗАПУСК НА RENDER WEB SERVICE
# =========================

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь токен в Environment Variables Render."
        )

    if len(SLOT_POINTS) != 64:
        raise RuntimeError("В таблице слотов должно быть ровно 64 результата.")

    init_db()

    external_url = (
        os.getenv("WEBHOOK_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
    )
    if not external_url:
        raise RuntimeError(
            "Не найден WEBHOOK_URL или RENDER_EXTERNAL_URL. "
            "Для Render Web Service нужен публичный URL сервиса."
        )

    external_url = external_url.rstrip("/")
    webhook_url = f"{external_url}/{BOT_TOKEN}"

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("games", games_command))
    application.add_handler(CommandHandler("bonus", bonus_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(callbacks))

    print("Lucky Sticker запускается через Webhook...", flush=True)

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
