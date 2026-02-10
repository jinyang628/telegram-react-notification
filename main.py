import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageReactionHandler,
)

BOT_TOKEN = "YOUR_BOT_TOKEN"
DELAY_HOURS = 3

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

    # reaction added
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

    # reaction removed → cancel DM
    else:
        cur.execute(
            """
            DELETE FROM pending_dm
            WHERE user_id = ? AND message_id = ?
            """,
            (user_id, message_id),
        )

    conn.commit()
    conn.close()


# ---------- WORKER ----------
async def dm_worker(app):
    while True:
        now = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT user_id, message_id
            FROM pending_dm
            WHERE sent = 0 AND scheduled_at <= ?
            """,
            (now,),
        )

        rows = cur.fetchall()

        for user_id, message_id in rows:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text="👋 You reacted earlier — here’s the follow-up I promised.",
                )

                cur.execute(
                    """
                    UPDATE pending_dm
                    SET sent = 1
                    WHERE user_id = ? AND message_id = ?
                    """,
                    (user_id, message_id),
                )

            except Exception:
                # User never started bot / blocked bot
                cur.execute(
                    """
                    DELETE FROM pending_dm
                    WHERE user_id = ? AND message_id = ?
                    """,
                    (user_id, message_id),
                )

        conn.commit()
        conn.close()

        await asyncio.sleep(60)  # check every minute


# ---------- MAIN ----------
async def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageReactionHandler(on_reaction))

    asyncio.create_task(dm_worker(app))

    print("Bot running...")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
