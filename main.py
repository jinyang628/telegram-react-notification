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

# How long to wait before tagging the user in the group
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
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot active! React to messages and I'll tag you here shortly."
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

    if reaction.new_reaction:
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
        cur.execute(
            "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )

    conn.commit()
    conn.close()


# ---------- JOB QUEUE WORKER (Group Tagging) ----------
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
            # Using HTML instead of MarkdownV2 to avoid "reserved character" errors
            # This creates a clickable mention using the user's ID
            mention_text = (
                f'Hey <a href="tg://user?id={user_id}">user</a>, '
                f"thanks for the reaction! Here is the info I promised."
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=mention_text,
                parse_mode=constants.ParseMode.HTML,  # Changed to HTML
                reply_to_message_id=message_id,
            )

            cur.execute(
                "UPDATE pending_dm SET sent = 1 WHERE user_id = ? AND message_id = ?",
                (user_id, message_id),
            )
        except Exception as e:
            print(f"Error tagging user {user_id} in chat {chat_id}: {e}")
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
    app.add_handler(MessageReactionHandler(on_reaction))

    # Check for pending tags every 10 seconds
    app.job_queue.run_repeating(check_pending_mentions, interval=2)

    print("Bot is running... Monitoring reactions for group tagging...")

    app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])


if __name__ == "__main__":
    main()
