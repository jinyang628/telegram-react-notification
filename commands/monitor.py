import sqlite3

from telegram import Update, constants
from telegram.ext import ContextTypes

from constants import DB_PATH


def _extract_notify_time_sgt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str | None:
    """
    Returns an 'HH:MM' (24h) string if provided, else None.
    Accepts:
      - /monitor 21:30
      - @MessageReactorsBot monitor 21:30
    """
    if getattr(context, "args", None):
        candidate = context.args[0].strip()
        if candidate:
            return candidate

    text = (update.message.text or "").strip()
    if not text:
        return None

    # naive parse: look for the first token after the word "monitor"
    tokens = text.split()
    for i, tok in enumerate(tokens):
        if tok.lower().endswith("monitor") or tok.lower() == "monitor":
            if i + 1 < len(tokens):
                return tokens[i + 1].strip()
            return None
    return None


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
    raw_time: str | None = _extract_notify_time_sgt(update, context)
    notify_time_sgt: str | None = _normalize_hhmm(raw_time)
    if raw_time and not notify_time_sgt:
        await update.message.reply_text(
            "⚠️ Invalid time format.\n\n"
            "**Usage:** Reply to a message with `/monitor HH:MM` (24h) to set notify time.\n"
            "Example: `/monitor 21:30`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO monitored_message (id, chat_id, message_id, notify_time_sgt) VALUES (1, ?, ?, ?)",
        (chat_id, message_id, notify_time_sgt),
    )
    cur.execute("DELETE FROM pending_dm WHERE sent = 0")
    conn.commit()
    conn.close()

    when_line = (
        f"\n\n⏰ **Notify at:** `{notify_time_sgt}`"
        if notify_time_sgt
        else "\n\n⏰ **Notify:** default delay (no time set)"
    )
    await update.message.reply_text(
        f"🔥 **AVALON MONITOR ACTIVE** 🔥\n"
        f"━━━━━━━━━━━━━━\n"
        f"I am now tracking reactions on the message above!"
        f"{when_line}",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
