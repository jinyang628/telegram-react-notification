import os
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, MessageReactionHandler, filters)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "@MessageReactorsBot"

DELAY_HOURS = 0.001
DB_PATH = "reactions.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS pending_dm (user_id INTEGER, chat_id INTEGER, message_id INTEGER, scheduled_at TEXT, sent INTEGER DEFAULT 0, PRIMARY KEY (user_id, message_id))"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS monitored_message (id INTEGER PRIMARY KEY CHECK (id = 1), chat_id INTEGER, message_id INTEGER)"
    )
    conn.commit()
    conn.close()


async def monitor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    This handles both the standard /monitor command AND
    when someone types '@BotName /monitor'
    """
    # 1. Ensure it's a reply
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ **Explicit Reply Required**\n\n"
            "To monitor a message, you must **reply** to that specific message "
            "with `/monitor`",
            parse_mode=constants.ParseMode.MARKDOWN,
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

    # Visual Confirmation
    await update.message.reply_text(
        f"Holy shit it is time for 🔥AVALON🔥\n"
        f"━━━━━━━━━━━━━━\n"
        f"I will tag everyone who reacted to this message 15 mins before game starts so everyone comes on time",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction or not reaction.user:
        return

    user_id = reaction.user.id
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
        scheduled_time = (
            datetime.now(timezone.utc) + timedelta(hours=DELAY_HOURS)
        ).isoformat()
        cur.execute(
            "INSERT OR REPLACE INTO pending_dm (user_id, chat_id, message_id, scheduled_at, sent) VALUES (?, ?, ?, ?, 0)",
            (user_id, chat_id, message_id, scheduled_time),
        )
    else:
        cur.execute(
            "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )

    conn.commit()
    conn.close()


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
            mention_text = f'Hey <a href="tg://user?id={user_id}">user</a>, thanks for the reaction!'
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
        except Exception:
            cur.execute(
                "DELETE FROM pending_dm WHERE user_id = ? AND message_id = ?",
                (user_id, message_id),
            )

    conn.commit()
    conn.close()


def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # This handles:
    # 1. /monitor
    # 2. /monitor@MessageReactorsBot
    # 3. Typing @MessageReactorsBot and selecting 'monitor' from the pop-up list
    # 4. The bot being mentioned with the word monitor
    app.add_handler(CommandHandler("monitor", monitor_trigger))
    app.add_handler(
        MessageHandler(
            filters.Mention(BOT_USERNAME) & filters.Regex(r"monitor"), monitor_trigger
        )
    )

    app.add_handler(MessageReactionHandler(on_reaction))
    app.job_queue.run_repeating(check_pending_mentions, interval=2)

    print("Bot is running...")
    app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])


if __name__ == "__main__":
    main()
