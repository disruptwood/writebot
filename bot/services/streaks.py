"""Pure streak calculation — no DB, no I/O, fully testable."""

from datetime import date, timedelta


def calculate_streak(sorted_date_strings: list[str], today: str | None = None) -> tuple[int, int]:
    """Calculate current and longest streak from sorted ISO date strings.

    Args:
        sorted_date_strings: List of "YYYY-MM-DD" strings in ascending order.
        today: Today's date as "YYYY-MM-DD". If None, uses date.today().

    Returns:
        (current_streak, longest_streak) tuple.
    """
    if not sorted_date_strings:
        return 0, 0

    dates = [date.fromisoformat(d) for d in sorted_date_strings]
    today_date = date.fromisoformat(today) if today else date.today()

    # Calculate longest streak
    longest = 1
    current_run = 1
    for i in range(1, len(dates)):
        if dates[i] - dates[i - 1] == timedelta(days=1):
            current_run += 1
            longest = max(longest, current_run)
        elif dates[i] != dates[i - 1]:  # skip duplicates
            current_run = 1

    # Calculate current streak (must include today or yesterday)
    last_date = dates[-1]
    gap = (today_date - last_date).days

    if gap > 1:
        # Streak is broken — last post was more than 1 day ago
        return 0, longest

    # Walk backwards to find current streak length
    current = 1
    for i in range(len(dates) - 2, -1, -1):
        if dates[i + 1] - dates[i] == timedelta(days=1):
            current += 1
        elif dates[i] != dates[i + 1]:
            break

    longest = max(longest, current)
    return current, longest
