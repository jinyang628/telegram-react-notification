from datetime import timedelta, timezone

DELAY_HOURS = 0.001
DB_PATH = "reactions.db"
POLL_INTERVAL = 10800 # 3 hours
# POLL_INTERVAL = 60
SGT_TZ = timezone(timedelta(hours=8))
