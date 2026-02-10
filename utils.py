import html
import sqlite3
from datetime import datetime, timedelta, timezone

from telegram import Update, constants
from telegram.ext import ContextTypes

from constants import DB_PATH, DELAY_HOURS, SGT_TZ


async def track_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves every user who speaks so we can nag them later if they haven't reacted."""
    if not update.effective_user or update.effective_user.is_bot:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    full_name = html.escape(update.effective_user.first_name)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO seen_users (user_id, chat_id, full_name) VALUES (?, ?, ?)",
        (user_id, chat_id, full_name),
    )
    conn.commit()
    conn.close()


def _next_sgt_occurrence_utc(hh: int, mm: int) -> datetime:
    now_utc = datetime.now(timezone.utc)
    now_sgt = now_utc.astimezone(SGT_TZ)
    candidate_sgt = now_sgt.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate_sgt <= now_sgt:
        candidate_sgt = candidate_sgt + timedelta(days=1)
    return candidate_sgt.astimezone(timezone.utc)


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
    cur.execute(
        "SELECT chat_id, message_id, notify_time FROM monitored_message WHERE id = 1"
    )
    row = cur.fetchone()

    if not row or row[1] != message_id:
        conn.close()
        return
    notify_time = row[2]

    if reaction.new_reaction:
        if notify_time:
            try:
                hh_str, mm_str = notify_time.split(":", 1)
                sched_dt = _next_sgt_occurrence_utc(int(hh_str), int(mm_str))
            except Exception:
                sched_dt = datetime.now(timezone.utc) + timedelta(hours=DELAY_HOURS)
        else:
            sched_dt = datetime.now(timezone.utc) + timedelta(hours=DELAY_HOURS)

        sched = sched_dt.strftime("%Y-%m-%d %H:%M:%S")
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
