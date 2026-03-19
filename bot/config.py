import os


def _parse_int_list(env_name: str) -> list[int]:
    raw_value = os.environ.get(env_name, "").strip()
    if not raw_value:
        return []

    values = []
    for chunk in raw_value.split(","):
        item = chunk.strip()
        if not item:
            continue
        values.append(int(item))
    return values


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
DISCUSSION_GROUP_ID = int(os.environ["DISCUSSION_GROUP_ID"])
REMINDER_CHAT_ID = int(os.environ.get("REMINDER_CHAT_ID", str(DISCUSSION_GROUP_ID)))
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost:8080")
DB_PATH = os.environ.get("DB_PATH", "data/writebot.db")
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", "8080"))
TIMEZONE = os.environ.get("TZ", "Asia/Jerusalem")
INITIAL_ADMIN_ID = int(os.environ.get("INITIAL_ADMIN_ID", "0"))
BOT_INVITE_LINK_NAME = os.environ.get("BOT_INVITE_LINK_NAME", "writebot-main")
MANUAL_MEMBER_IDS = _parse_int_list("MANUAL_MEMBER_IDS")

EVENING_WARNING_HOUR = 22
EVENING_WARNING_MINUTE = 30
MIDNIGHT_ENFORCEMENT_HOUR = 0
MIDNIGHT_ENFORCEMENT_MINUTE = 0

WEBHOOK_ALLOWED_UPDATES = [
    "message",
    "channel_post",
    "edited_channel_post",
    "chat_member",
    "chat_join_request",
]

STRINGS = {
    "welcome": (
        "Привет! Я бот писательского канала.\n"
        "Я слежу за публикациями в канале и напоминаю о дедлайне.\n\n"
        "Минимум один пост за два дня. В 22:30 по Израилю я предупреждаю тех, кто ещё не писал сегодня."
    ),
    "stats": "📊 Сегодня написали: {today_count}/{total} участников",
    "stats_empty": "Сегодня ещё никто не писал. Будьте первым!",
    "streak": "🔥 {name}: стрик {current} дн. (рекорд: {longest})",
    "no_streak": "У {name} пока нет стрика. Время начать!",
    "missing_header": "⏰ Сегодня ещё не писали:",
    "leaderboard_header": "🏆 Топ стриков:",
    "warning_missing": (
        "⏰ До 00:00 по Израилю сегодня ещё не писали:\n"
        "{mentions}"
    ),
    "warning_kick_tonight": (
        "⚠️ Если до 00:00 не появится пост, бот удалит из канала:\n"
        "{mentions}"
    ),
    "kicked_for_inactivity": (
        "🚪 Удалены за два дня без поста:\n"
        "{mentions}"
    ),
    "not_admin": "Эта команда только для админов.",
    "admin_added": "✅ {name} добавлен как админ.",
    "admin_removed": "❌ {name} убран из админов.",
    "invite_link": "Основная ссылка для входа через join request:\n{invite_link}",
}
