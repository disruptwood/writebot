import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
DISCUSSION_GROUP_ID = int(os.environ["DISCUSSION_GROUP_ID"])
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost:8080")
DB_PATH = os.environ.get("DB_PATH", "data/writebot.db")
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", "8080"))
TIMEZONE = os.environ.get("TZ", "Asia/Jerusalem")
# Hour in local timezone to post daily summary.
# 0 = midnight (summarize previous day), 23 = 11pm (summarize current day)
DAILY_SUMMARY_HOUR = int(os.environ.get("DAILY_SUMMARY_HOUR", "0"))
INITIAL_ADMIN_ID = int(os.environ.get("INITIAL_ADMIN_ID", "0"))

STRINGS = {
    "welcome": (
        "Привет! Я бот писательского канала.\n"
        "Я отслеживаю ежедневные публикации и считаю стрики.\n\n"
        "Напиши пост в канал до полуночи (Израиль), и я засчитаю день!"
    ),
    "stats": "📊 Сегодня написали: {today_count}/{total} участников",
    "stats_empty": "Сегодня ещё никто не писал. Будьте первым!",
    "streak": "🔥 {name}: стрик {current} дн. (рекорд: {longest})",
    "no_streak": "У {name} пока нет стрика. Время начать!",
    "missing_header": "⏰ Сегодня ещё не писали:",
    "leaderboard_header": "🏆 Топ стриков:",
    "daily_summary": (
        "📝 Итоги дня ({date}):\n"
        "Написали: {count}/{total}\n"
        "{streak_info}"
    ),
    "not_admin": "Эта команда только для админов.",
    "admin_added": "✅ {name} добавлен как админ.",
    "admin_removed": "❌ {name} убран из админов.",
    "kick_list": "Неактивные ({days}+ дней): {names}",
    "kicked": "👋 {name} удалён из канала.",
    "reinvited": "↩️ {name} разбанен и может вернуться.",
}
