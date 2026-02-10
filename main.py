import os
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageReactionHandler)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

DELAY_HOURS = 0.001
DB_PATH = "reactions.db"


# ---------- DB SETUP ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_dm (
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            scheduled_at TEXT,
            sent INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, message_id)
        )
        """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS monitored_message (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            chat_id INTEGER,
            message_id INTEGER
        )
        """)
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot active! Reply to a message with /monitor to start tracking reactions."
    )


# ---------- MONITOR COMMAND ----------
async def monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please **reply** to the message you want to monitor."
        )
        return

    target_msg = update.message.reply_to_message
    chat_id = target_msg.chat_id
    message_id = target_msg.message_id

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO monitored_message (id, chat_id, message_id) VALUES (1, ?, ?)",
        (chat_id, message_id),
    )
    cur.execute("DELETE FROM pending_dm WHERE sent = 0")
    conn.commit()
    conn.close()

    print(f"DEBUG: Now monitoring Chat {chat_id}, Msg {message_id}")
    await update.message.reply_text(
        f"🎯 Monitoring reactions for message {message_id}."
    )


# ---------- REACTION HANDLER ----------
async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction or not reaction.user:
        return

    user_id = reaction.user.id
    chat_id = reaction.chat.id
    message_id = reaction.message_id

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get the currently monitored message
    cur.execute("SELECT chat_id, message_id FROM monitored_message WHERE id = 1")
    row = cur.fetchone()

    if not row:
        print("DEBUG: No message is currently being monitored.")
        conn.close()
        return

    monitored_chat_id, monitored_msg_id = row

    # DEBUG LINE: See what the bot is comparing
    print(f"DEBUG: Reaction on Msg {message_id} | Monitored Msg: {monitored_msg_id}")

    if message_id != monitored_msg_id:
        # Ignore reactions on other messages
        conn.close()
        return

    if reaction.new_reaction:
        print(f"DEBUG: Valid reaction from {user_id}. Scheduling mention...")
        scheduled_time = (
            datetime.now(timezone.utc) + timedelta(hours=DELAY_HOURS)
        ).isoformat()

        cur.execute(
            """
            INSERT OR REPLACE INTO pending_dm
            (user_id, chat_id, message_id, scheduled_at, sent)
            VALUES (?, ?, ?, ?, 0)
            """,
            (user_id, chat_id, message_id, scheduled_time),
        )
    else:
        print(f"DEBUG: Reaction removed by {user_id}.")
        cur.execute(
            "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )

    conn.commit()
    conn.close()


# ---------- JOB QUEUE WORKER ----------
async def check_pending_mentions(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, chat_id, message_id FROM pending_dm WHERE sent = 0 AND scheduled_at <= ?",
        (now,),
    )
    rows = cur.fetchall()

    for user_id, chat_id, message_id in rows:
        try:
            print(f"DEBUG: Attempting to tag user {user_id} in chat {chat_id}")
            mention_text = (
                f'Hey <a href="tg://user?id={user_id}">user</a>, '
                f"thanks for the reaction!"
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=mention_text,
                parse_mode=constants.ParseMode.HTML,
                reply_to_message_id=message_id,
            )

            cur.execute(
                "UPDATE pending_dm SET sent = 1 WHERE user_id = ? AND message_id = ?",
                (user_id, message_id),
            )
        except Exception as e:
            print(f"ERROR in worker: {e}")
            cur.execute(
                "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
                (user_id, message_id),
            )

    conn.commit()
    conn.close()


# ---------- MAIN ----------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("monitor", monitor))
    app.add_handler(MessageReactionHandler(on_reaction))

    # Run check every 2 seconds
    app.job_queue.run_repeating(check_pending_mentions, interval=2)

    print("Bot is running...")
    app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])


if __name__ == "__main__":
    main()
