import sqlite3

from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, MessageReactionHandler, filters)


# ---------- MONITOR LOGIC ----------
async def monitor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ **Reply to a message** with `/monitor` to track it.",
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

    await update.message.reply_text(
        f"🔥 **AVALON MONITOR ACTIVE** 🔥\n"
        f"━━━━━━━━━━━━━━\n"
        f"I am now tracking reactions on the message above!",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


# ---------- KILL COMMAND ----------
async def kill_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears all monitoring data and pending notifications."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Remove the monitored message
    cur.execute("DELETE FROM monitored_message")
    # Clear all unsent notifications
    cur.execute("DELETE FROM pending_dm WHERE sent = 0")

    conn.commit()
    conn.close()

    print("DEBUG: Monitoring killed by user.")
    await update.message.reply_text(
        "🛑 **MONITORING KILLED** 🛑\n"
        f"━━━━━━━━━━━━━━\n"
        "1. Current monitored message cleared.\n"
        "2. All pending notifications cancelled.\n\n"
        "Use `/monitor` on a new message to start again.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
