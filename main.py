import logging
import os
import sqlite3
import threading

from dotenv import load_dotenv
from flask import Flask
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          MessageReactionHandler, filters)

from commands.kill import kill_game
from commands.nag import nag_non_reactors_job
from commands.start import start_game
from constants import DB_PATH, POLL_INTERVAL
from utils import check_pending_mentions, on_reaction, track_users

# Create a tiny Flask app for Render's health check
flask_app = Flask(__name__)

logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = os.getenv("PORT")
BOT_USERNAME = "@MessageReactorsBot"


@flask_app.route("/status")
def health_check():
    return "Bot is alive!", 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS pending_dm (
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            full_name TEXT,
            scheduled_at TEXT,
            sent INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, message_id)
        )""")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS seen_users (user_id INTEGER, chat_id INTEGER, full_name TEXT, PRIMARY KEY (user_id, chat_id))"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS nagged_users (user_id INTEGER, chat_id INTEGER, message_id INTEGER, PRIMARY KEY (user_id, message_id))"
    )
    cur.execute("PRAGMA table_info(pending_dm)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS monitored_message (id INTEGER PRIMARY KEY CHECK (id = 1), chat_id INTEGER, message_id INTEGER, notify_time TEXT, threshold INTEGER)"
    )
    cur.execute("PRAGMA table_info(monitored_message)")
    conn.commit()
    conn.close()


def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_game))
    app.add_handler(CommandHandler("kill", kill_game))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_users))
    app.add_handler(
        MessageHandler(
            filters.Mention(BOT_USERNAME) & filters.Regex(r"start"), start_game
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Mention(BOT_USERNAME) & filters.Regex(r"kill"), kill_game
        )
    )
    app.add_handler(MessageReactionHandler(on_reaction))
    app.job_queue.run_repeating(check_pending_mentions, interval=POLL_INTERVAL)
    app.job_queue.run_repeating(nag_non_reactors_job, interval=POLL_INTERVAL)

    app.run_polling(allowed_updates=["message", "callback_query", "message_reaction"])


if __name__ == "__main__":
    main()
