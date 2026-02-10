import sqlite3

from telegram import Update, constants
from telegram.ext import ContextTypes

from constants import DB_PATH


async def kill_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears all monitoring data and pending notifications."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("DELETE FROM monitored_message")
    cur.execute("DELETE FROM pending_dm WHERE sent = 0")

    conn.commit()
    conn.close()

    await update.message.reply_text(
        "🛑 **MONITORING KILLED** 🛑\n"
        f"━━━━━━━━━━━━━━\n"
        "1. Current monitored message cleared.\n"
        "2. All pending notifications cancelled.\n\n"
        "Use `/monitor` on a new message to start again.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
