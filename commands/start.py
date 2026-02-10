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


def _get_notify_time(game_time: str) -> str:
    hh_str, mm_str = game_time.split(":", 1)
    total_minutes = int(hh_str) * 60 + int(mm_str) - 15
    total_minutes %= 24 * 60

    notify_hh = total_minutes // 60
    notify_mm = total_minutes % 60
    notify_time: str = f"{notify_hh:02d}:{notify_mm:02d}"
    return notify_time


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    raw_time: str | None = _get_named_arg(args, "reminder")
    raw_threshold: str | None = _get_named_arg(args, "threshold")
    if not raw_time or not raw_threshold:
        await update.message.reply_text(
            "Please issue a command with the format `/start reminder=HH:MM threshold=X`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return
    game_time: str | None = _normalize_hhmm(raw_time)
    if not game_time:
        await update.message.reply_text(
            "Please issue a command containing a valid time in the format HH:MM",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return
    if (
        not raw_threshold.isdigit()
        or int(raw_threshold) <= 0
        or int(raw_threshold) > 10
    ):
        await update.message.reply_text(
            "Please issue a command containing a valid threshold between 1 and 10",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return
    threshold: int = int(raw_threshold)

    time_line = f"⏰ **Game Starts At:** `{game_time}`\n" if game_time else ""
    game_message_text = (
        f"🔥 **AVALON** 🔥\n"
        f"━━━━━━━━━━━━━━\n"
        f"{time_line}"
        f"🚨 **Target:** `{threshold}` players needed\n\n"
        f"👇 **REACT WITH ANY EMOJI TO JOIN!**"
    )

    sent_message = await update.message.reply_text(
        game_message_text, parse_mode=constants.ParseMode.MARKDOWN
    )

    chat_id = sent_message.chat_id
    message_id = sent_message.message_id

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    notify_time: str = _get_notify_time(game_time)
    print(notify_time)

    cur.execute(
        "INSERT OR REPLACE INTO monitored_message (id, chat_id, message_id, notify_time, threshold) VALUES (1, ?, ?, ?, ?)",
        (chat_id, message_id, notify_time, threshold),
    )
    cur.execute("DELETE FROM pending_dm WHERE sent = 0")
    conn.commit()
    conn.close()
