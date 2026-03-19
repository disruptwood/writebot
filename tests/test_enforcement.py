from bot.services.enforcement import (
    evaluate_member,
    is_due_for_midnight_kick,
    is_missing_today,
    select_midnight_kick_members,
    split_evening_warning_members,
)


def _snapshot(
    user_id: int,
    joined_date: str,
    last_post_date: str | None,
) -> dict:
    return {
        "user_id": user_id,
        "username": None,
        "first_name": f"user-{user_id}",
        "last_name": None,
        "joined_date": joined_date,
        "last_post_date": last_post_date,
    }


class TestEnforcementRules:
    def test_missing_today(self):
        assert is_missing_today("2024-01-15", "2024-01-15") is False
        assert is_missing_today("2024-01-14", "2024-01-15") is True
        assert is_missing_today(None, "2024-01-15") is True

    def test_new_member_is_not_due_for_kick_on_first_day(self):
        assert is_due_for_midnight_kick("2024-01-15", None, "2024-01-15") is False

    def test_second_day_without_posts_is_due_for_kick(self):
        assert is_due_for_midnight_kick("2024-01-14", None, "2024-01-15") is True

    def test_post_yesterday_keeps_member_safe(self):
        assert is_due_for_midnight_kick("2024-01-10", "2024-01-14", "2024-01-15") is False

    def test_post_day_before_yesterday_is_not_enough(self):
        assert is_due_for_midnight_kick("2024-01-10", "2024-01-13", "2024-01-15") is True

    def test_evaluate_member_combines_flags(self):
        state = evaluate_member(_snapshot(1, "2024-01-14", None), "2024-01-15")
        assert state.missing_today is True
        assert state.due_for_midnight_kick is True

    def test_split_evening_warning_members(self):
        missing, due = split_evening_warning_members(
            [
                _snapshot(1, "2024-01-15", None),
                _snapshot(2, "2024-01-10", "2024-01-14"),
                _snapshot(3, "2024-01-10", "2024-01-13"),
                _snapshot(4, "2024-01-10", "2024-01-15"),
            ],
            "2024-01-15",
        )
        assert [member.user_id for member in missing] == [1, 2, 3]
        assert [member.user_id for member in due] == [3]

    def test_select_midnight_kick_members(self):
        due = select_midnight_kick_members(
            [
                _snapshot(1, "2024-01-15", None),
                _snapshot(2, "2024-01-10", "2024-01-14"),
                _snapshot(3, "2024-01-10", "2024-01-13"),
            ],
            "2024-01-15",
        )
        assert [member.user_id for member in due] == [3]
