"""Tests for discussion group command handlers (/stats, /missing, /streak, /leaderboard)."""


from bot import config
from bot.db import queries
from bot.handlers.group import cmd_stats, cmd_missing, cmd_streak, cmd_leaderboard, _display_name
from tests.conftest import make_message, make_user, make_chat


GROUP_CHAT = make_chat(
    chat_id=config.DISCUSSION_GROUP_ID,
    chat_type="supergroup",
    title="Test Discussion",
)


def _group_message(from_user=None, text="/stats"):
    return make_message(
        chat=GROUP_CHAT,
        from_user=from_user or make_user(),
        text=text,
    )


class TestDisplayName:
    def test_with_username(self):
        assert _display_name({"username": "alice"}) == "@alice"

    def test_with_first_name(self):
        assert _display_name({"username": None, "first_name": "Alice"}) == "Alice"

    def test_fallback_to_id(self):
        assert _display_name({"username": None, "first_name": None, "user_id": 42}) == "id:42"


class TestCmdStats:
    async def test_stats_empty(self):
        msg = _group_message()
        await cmd_stats(msg)
        msg.reply.assert_called_once()
        assert config.STRINGS["stats_empty"] in msg.reply.call_args[0][0]

    async def test_stats_with_writers(self):
        await queries.upsert_member(100, "alice", "Alice")
        await queries.upsert_member(200, "bob", "Bob")

        from bot.handlers.group import _today
        today = _today()
        await queries.upsert_daily_participation(100, today, 50)

        msg = _group_message()
        await cmd_stats(msg)

        response = msg.reply.call_args[0][0]
        assert "1/2" in response
        assert "@alice" in response


class TestCmdMissing:
    async def test_nobody_missing(self):
        await queries.upsert_member(100, "alice", "Alice")

        from bot.handlers.group import _today
        today = _today()
        await queries.upsert_daily_participation(100, today, 50)

        msg = _group_message()
        await cmd_missing(msg)

        response = msg.reply.call_args[0][0]
        assert "Все написали" in response

    async def test_some_missing(self):
        await queries.upsert_member(100, "alice", "Alice")
        await queries.upsert_member(200, "bob", "Bob")

        from bot.handlers.group import _today
        today = _today()
        await queries.upsert_daily_participation(100, today, 50)

        msg = _group_message()
        await cmd_missing(msg)

        response = msg.reply.call_args[0][0]
        assert "@bob" in response
        assert "@alice" not in response


class TestCmdStreak:
    async def test_no_streak(self):
        user = make_user(user_id=100, first_name="Alice")
        msg = _group_message(from_user=user)

        await cmd_streak(msg)

        response = msg.reply.call_args[0][0]
        assert "Alice" in response
        assert "нет стрика" in response

    async def test_with_streak(self):
        user = make_user(user_id=100, first_name="Alice")
        await queries.update_streak(100, "alice", "Alice", 5, 10, "2024-01-15")

        msg = _group_message(from_user=user)
        await cmd_streak(msg)

        response = msg.reply.call_args[0][0]
        assert "5" in response
        assert "10" in response

    async def test_no_from_user_ignored(self):
        msg = _group_message()
        msg.from_user = None

        await cmd_streak(msg)

        msg.reply.assert_not_called()


class TestCmdLeaderboard:
    async def test_empty_leaderboard(self):
        msg = _group_message()
        await cmd_leaderboard(msg)

        response = msg.reply.call_args[0][0]
        assert "нет стриков" in response

    async def test_leaderboard_with_data(self):
        await queries.update_streak(100, "alice", "Alice", 5, 5, "2024-01-15")
        await queries.update_streak(200, "bob", "Bob", 3, 7, "2024-01-15")

        msg = _group_message()
        await cmd_leaderboard(msg)

        response = msg.reply.call_args[0][0]
        assert "Топ" in response
        assert "@alice" in response
        assert "@bob" in response
        # Alice should be first (higher current streak)
        assert response.index("@alice") < response.index("@bob")

    async def test_zero_streak_excluded(self):
        await queries.update_streak(100, "alice", "Alice", 0, 5, "2024-01-10")

        msg = _group_message()
        await cmd_leaderboard(msg)

        response = msg.reply.call_args[0][0]
        assert "нет стриков" in response
