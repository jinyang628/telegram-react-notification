import sqlite3

from telegram import Update, constants
from telegram.ext import ContextTypes

from constants import DB_PATH


def _normalize_hhmm(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    if ":" not in v:
        return None
    hh_str, mm_str = v.split(":", 1)
    if not (hh_str.isdigit() and mm_str.isdigit()):
        return None
    hh = int(hh_str)
    mm = int(mm_str)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return f"{hh:02d}:{mm:02d}"


def _get_named_arg(args: list[str], key: str) -> str | None:
    """Helper to find a value for a specific key in ['key=value', ...]"""
    for arg in args:
        if arg.lower().startswith(f"{key.lower()}="):
            try:
                return arg.split("=", 1)[1]
            except IndexError:
                return None
    return None


async def monitor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ **Reply to a message** with `/monitor reminder=HH:MM threshold=X`"
        )
        return

    args = context.args

    raw_time = _get_named_arg(args, "reminder")
    if not raw_time and len(args) > 0 and ":" in args[0] and "=" not in args[0]:
        raw_time = args[0]

    notify_time = _normalize_hhmm(raw_time)

    raw_threshold = _get_named_arg(args, "threshold")
    if not raw_threshold:
        for arg in args:
            if arg.isdigit():
                raw_threshold = arg
                break

    threshold = int(raw_threshold) if (raw_threshold and raw_threshold.isdigit()) else 7

    target_msg = update.message.reply_to_message
    chat_id = target_msg.chat_id
    message_id = target_msg.message_id

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO monitored_message (id, chat_id, message_id, notify_time, threshold) VALUES (1, ?, ?, ?, ?)",
        (chat_id, message_id, notify_time, threshold),
    )
    cur.execute("DELETE FROM pending_dm WHERE sent = 0")
    conn.commit()
    conn.close()

    await update.message.reply_text(
        (
            f"🔥 **AVALON SCHEDULED** 🔥\n"
            f"━━━━━━━━━━━━━━\n"
            f"\n🚨 **Minimum Players Needed:** `{threshold}`"
            if threshold > 0
            else ""
        ),
        parse_mode=constants.ParseMode.MARKDOWN,
    )
