import asyncio
import sqlite3
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageReactionHandler,
    CommandHandler,
)

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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_dm (
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            scheduled_at TEXT,
            sent INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, message_id)
        )
        """
    )
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Got it! I’ll message you later if you react to the group message."
    )

# ---------- REACTION HANDLER ----------
async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction:
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

# ---------- JOB QUEUE WORKER (Replaces dm_worker) ----------
async def check_pending_dms(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, message_id FROM pending_dm WHERE sent = 0 AND scheduled_at <= ?",
        (now,),
    )
    rows = cur.fetchall()

    for user_id, message_id in rows:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="👋 You reacted earlier — here’s the follow-up I promised.",
            )
            cur.execute(
                "UPDATE pending_dm SET sent = 1 WHERE user_id = ? AND message_id = ?",
                (user_id, message_id),
            )
        except Exception as e:
            # Usually if the user hasn't started the bot or blocked it
            print(f"Failed to send DM to {user_id}: {e}")
            cur.execute(
                "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
                (user_id, message_id),
            )

    conn.commit()
    conn.close()

# ---------- MAIN ----------
def main():
    init_db()

    # Build the application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageReactionHandler(on_reaction))

    job_queue = app.job_queue
    job_queue.run_repeating(check_pending_dms, interval=5)

    print("Bot is running...")
    
    app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])

if __name__ == "__main__":
    main()