import random
import sqlite3

from telegram import constants
from telegram.ext import ContextTypes

from constants import DB_PATH


async def nag_non_reactors_job(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Get the current monitored message and threshold
    cur.execute(
        "SELECT chat_id, message_id, threshold FROM monitored_message WHERE id = 1"
    )
    monitored = cur.fetchone()
    if not monitored or monitored[2] <= 0:  # threshold is 0 or not set
        conn.close()
        return

    chat_id, message_id, threshold = monitored

    # 2. Count how many people have reacted
    cur.execute("SELECT COUNT(*) FROM pending_dm WHERE message_id = ?", (message_id,))
    current_count = cur.fetchone()[0]

    # 3. If we haven't reached the threshold, find people to nag
    if current_count < threshold:
        # Get all users who have spoken in this chat but NOT reacted
        cur.execute(
            """
            SELECT user_id, full_name FROM seen_users 
            WHERE chat_id = ? 
            AND user_id NOT IN (SELECT user_id FROM pending_dm WHERE message_id = ?)
        """,
            (chat_id, message_id),
        )

        candidates = cur.fetchall()

        if candidates:
            # Pick 3 random people (or fewer if not enough candidates)
            to_nag = random.sample(candidates, min(len(candidates), 3))

            mentions = [f'<a href="tg://user?id={u[0]}">{u[1]}</a>' for u in to_nag]
            needed = threshold - current_count

            text = (
                f"📢 <b>WE NEED MORE PLAYERS!</b>\n"
                f"Currently: {current_count}/{threshold} (Need {needed} more)\n\n"
                f"Yo {', '.join(mentions)}, why haven't you reacted yet? 🤨\n"
                f"React to the pinned message to join the 🔥AVALON🔥 game!"
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=constants.ParseMode.HTML,
                reply_to_message_id=message_id,
            )

    conn.close()
