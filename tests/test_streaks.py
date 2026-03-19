"""Unit tests for streak calculation — pure logic, no DB."""

from bot.services.streaks import calculate_streak


class TestCalculateStreak:
    def test_empty(self):
        assert calculate_streak([], "2024-01-15") == (0, 0)

    def test_single_day_today(self):
        assert calculate_streak(["2024-01-15"], "2024-01-15") == (1, 1)

    def test_single_day_yesterday(self):
        """Yesterday's post still counts as active streak."""
        assert calculate_streak(["2024-01-14"], "2024-01-15") == (1, 1)

    def test_single_day_two_days_ago(self):
        """Two days ago — streak is broken."""
        assert calculate_streak(["2024-01-13"], "2024-01-15") == (0, 1)

    def test_consecutive_days(self):
        dates = ["2024-01-13", "2024-01-14", "2024-01-15"]
        assert calculate_streak(dates, "2024-01-15") == (3, 3)

    def test_gap_in_middle(self):
        dates = ["2024-01-10", "2024-01-11", "2024-01-14", "2024-01-15"]
        assert calculate_streak(dates, "2024-01-15") == (2, 2)

    def test_longer_history(self):
        dates = [
            "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
            # gap
            "2024-01-10", "2024-01-11",
        ]
        assert calculate_streak(dates, "2024-01-11") == (2, 5)

    def test_streak_broken_longest_preserved(self):
        dates = [
            "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
            # gap
            "2024-01-10",
        ]
        # Today is Jan 12 — streak broken (gap > 1 day from last post)
        assert calculate_streak(dates, "2024-01-12") == (0, 4)

    def test_today_continues_streak(self):
        dates = ["2024-01-14", "2024-01-15"]
        assert calculate_streak(dates, "2024-01-15") == (2, 2)

    def test_yesterday_continues_streak(self):
        """Streak is still alive if last post was yesterday."""
        dates = ["2024-01-13", "2024-01-14"]
        assert calculate_streak(dates, "2024-01-15") == (2, 2)

    def test_duplicate_dates(self):
        """Multiple posts on same day should not inflate streak."""
        dates = ["2024-01-14", "2024-01-14", "2024-01-15", "2024-01-15"]
        assert calculate_streak(dates, "2024-01-15") == (2, 2)

    def test_long_streak(self):
        dates = [f"2024-01-{d:02d}" for d in range(1, 32)]
        assert calculate_streak(dates, "2024-01-31") == (31, 31)
