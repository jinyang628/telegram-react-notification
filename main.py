import html
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, MessageReactionHandler, filters)

from commands import kill_monitor, monitor_trigger
from constants import DB_PATH, DELAY_HOURS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "@MessageReactorsBot"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS pending_dm (
            user_id INTEGER, chat_id INTEGER, message_id INTEGER, 
            scheduled_at TEXT, sent INTEGER DEFAULT 0, 
            PRIMARY KEY (user_id, message_id))""")

    cur.execute("PRAGMA table_info(pending_dm)")
    columns = [column[1] for column in cur.fetchall()]
    if "full_name" not in columns:
        cur.execute("ALTER TABLE pending_dm ADD COLUMN full_name TEXT")

    cur.execute(
        "CREATE TABLE IF NOT EXISTS monitored_message (id INTEGER PRIMARY KEY CHECK (id = 1), chat_id INTEGER, message_id INTEGER)"
    )
    conn.commit()
    conn.close()


async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction or not reaction.user:
        return

    user_id = reaction.user.id
    user_name = html.escape(reaction.user.first_name)
    chat_id = reaction.chat.id
    message_id = reaction.message_id

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT message_id FROM monitored_message WHERE id = 1")
    row = cur.fetchone()

    if not row or row[0] != message_id:
        conn.close()
        return

    if reaction.new_reaction:
        sched = (datetime.now(timezone.utc) + timedelta(hours=DELAY_HOURS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        cur.execute(
            "INSERT OR REPLACE INTO pending_dm (user_id, chat_id, message_id, full_name, scheduled_at, sent) VALUES (?, ?, ?, ?, ?, 0)",
            (user_id, chat_id, message_id, user_name, sched),
        )
    else:
        cur.execute(
            "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )

    conn.commit()
    conn.close()


async def check_pending_mentions(context: ContextTypes.DEFAULT_TYPE):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, chat_id, message_id, full_name FROM pending_dm WHERE sent = 0 AND scheduled_at <= ?",
        (now_str,),
    )
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return

    groups = {}
    for user_id, chat_id, message_id, full_name in rows:
        key = (chat_id, message_id)
        if key not in groups:
            groups[key] = []
        groups[key].append((user_id, full_name))

    for (chat_id, message_id), users in groups.items():
        try:
            mentions = [f'<a href="tg://user?id={u[0]}">{u[1]}</a>' for u in users]
            text = f"🔥 <b>AVALON ASSEMBLE!</b> 🔥\n\nYo {', '.join(mentions)}, game starts in 15 mins!"

            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=constants.ParseMode.HTML,
                reply_to_message_id=message_id,
            )

            u_ids = [u[0] for u in users]
            cur.execute(
                f"UPDATE pending_dm SET sent = 1 WHERE message_id = ? AND user_id IN ({','.join(['?']*len(u_ids))})",
                (message_id, *u_ids),
            )
        except Exception as e:
            print(f"ERROR: Failed to send group message: {e}")

    conn.commit()
    conn.close()


def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("monitor", monitor_trigger))
    app.add_handler(CommandHandler("kill", kill_monitor))
    app.add_handler(
        MessageHandler(
            filters.Mention(BOT_USERNAME) & filters.Regex(r"monitor"), monitor_trigger
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Mention(BOT_USERNAME) & filters.Regex(r"kill"), kill_monitor
        )
    )
    app.add_handler(MessageReactionHandler(on_reaction))
    app.job_queue.run_repeating(check_pending_mentions, interval=2)

    print("Bot started...")
    app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])


if __name__ == "__main__":
    main()
