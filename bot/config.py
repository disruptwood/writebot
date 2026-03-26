import json
import os
from dataclasses import dataclass, field


@dataclass
class ChannelConfig:
    slug: str
    channel_id: int
    discussion_group_id: int
    reminder_chat_id: int
    name: str
    invite_link_name: str
    private_commands: bool = False
    manual_member_ids: list[int] = field(default_factory=list)


def _parse_int_list(raw: str) -> list[int]:
    if not raw.strip():
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _build_channels() -> list[ChannelConfig]:
    raw = os.environ.get("CHANNELS_JSON", "").strip()
    if raw:
        items = json.loads(raw)
        channels = []
        for item in items:
            group_id = int(item["discussion_group_id"])
            channels.append(ChannelConfig(
                slug=item["slug"],
                channel_id=int(item["channel_id"]),
                discussion_group_id=group_id,
                reminder_chat_id=int(item.get("reminder_chat_id") or group_id),
                name=item.get("name", item["slug"]),
                invite_link_name=item.get("invite_link_name", f"{item['slug']}-main"),
                private_commands=bool(item.get("private_commands", False)),
                manual_member_ids=[int(x) for x in item.get("manual_member_ids", [])],
            ))
        return channels

    # Legacy fallback: single channel from individual env vars
    channel_id = int(os.environ["CHANNEL_ID"])
    group_id = int(os.environ["DISCUSSION_GROUP_ID"])
    return [ChannelConfig(
        slug="default",
        channel_id=channel_id,
        discussion_group_id=group_id,
        reminder_chat_id=int(os.environ.get("REMINDER_CHAT_ID", str(group_id))),
        name="WriteBot Channel",
        invite_link_name=os.environ.get("BOT_INVITE_LINK_NAME", "writebot-main"),
        private_commands=True,
        manual_member_ids=_parse_int_list(os.environ.get("MANUAL_MEMBER_IDS", "")),
    )]


BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost:8080")
DB_PATH = os.environ.get("DB_PATH", "data/writebot.db")
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", "8080"))
TIMEZONE = os.environ.get("TZ", "Asia/Jerusalem")
INITIAL_ADMIN_ID = int(os.environ.get("INITIAL_ADMIN_ID", "0"))

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

CHANNELS: list[ChannelConfig] = _build_channels()

# Lookup indexes
_CHANNEL_BY_CHANNEL_ID: dict[int, ChannelConfig] = {ch.channel_id: ch for ch in CHANNELS}
_CHANNEL_BY_GROUP_ID: dict[int, ChannelConfig] = {ch.discussion_group_id: ch for ch in CHANNELS}
ALL_CHANNEL_IDS: set[int] = {ch.channel_id for ch in CHANNELS}
ALL_GROUP_IDS: set[int] = {ch.discussion_group_id for ch in CHANNELS}


def get_channel_by_channel_id(chat_id: int) -> ChannelConfig | None:
    return _CHANNEL_BY_CHANNEL_ID.get(chat_id)


def get_channel_by_group_id(chat_id: int) -> ChannelConfig | None:
    return _CHANNEL_BY_GROUP_ID.get(chat_id)


def get_primary_channel() -> ChannelConfig | None:
    for ch in CHANNELS:
        if ch.private_commands:
            return ch
    return CHANNELS[0] if CHANNELS else None


# Legacy compat (used by old env vars fallback)
CHANNEL_ID = CHANNELS[0].channel_id if CHANNELS else 0
DISCUSSION_GROUP_ID = CHANNELS[0].discussion_group_id if CHANNELS else 0

STRINGS = {
    "welcome": (
        "Привет! Я бот писательского канала.\n"
        "Я слежу за публикациями в канале и напоминаю о дедлайне.\n\n"
        "Минимум один пост за два дня. В 22:30 по Израилю я предупреждаю тех, кто ещё не писал сегодня.\n\n"
        "📋 Команды:\n"
        "/start — Приветственное сообщение\n"
        "/mystats — Мой стрик\n\n"
        "В группе канала:\n"
        "/stats — Кто сегодня написал\n"
        "/missing — Кто ещё не писал\n"
        "/streak — Твой стрик\n"
        "/leaderboard — Таблица лидеров"
    ),
    "stats": "📊 Сегодня написали: {today_count}/{total} участников",
    "stats_empty": "Сегодня ещё никто не писал. Будьте первым!",
    "streak": "🔥 {name}: стрик {current} дн. (рекорд: {longest})",
    "no_streak": "У {name} пока нет стрика. Время начать!",
    "missing_header": "Сегодня ещё не писали:",
    "leaderboard_header": "🏆 Топ стриков:",
    "warning_missing": (
        "До 00:00 по Израилю сегодня ещё не писали:\n"
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
