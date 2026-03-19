from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class ComplianceState:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    joined_date: str | None
    last_post_date: str | None
    missing_today: bool
    due_for_midnight_kick: bool


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def is_missing_today(last_post_date: str | None, evaluation_date: str) -> bool:
    return last_post_date != evaluation_date


def is_due_for_midnight_kick(
    joined_date: str | None,
    last_post_date: str | None,
    evaluation_date: str,
) -> bool:
    joined = _parse_iso_date(joined_date)
    evaluation = date.fromisoformat(evaluation_date)
    if joined is None:
        return False

    # Users get their first two calendar days in the channel before removal.
    if joined > evaluation - timedelta(days=1):
        return False

    last_post = _parse_iso_date(last_post_date)
    if last_post is None:
        return True

    return last_post < evaluation - timedelta(days=1)


def evaluate_member(snapshot: dict, evaluation_date: str) -> ComplianceState:
    last_post_date = snapshot.get("last_post_date")
    joined_date = snapshot.get("joined_date")
    return ComplianceState(
        user_id=snapshot["user_id"],
        username=snapshot.get("username"),
        first_name=snapshot.get("first_name"),
        last_name=snapshot.get("last_name"),
        joined_date=joined_date,
        last_post_date=last_post_date,
        missing_today=is_missing_today(last_post_date, evaluation_date),
        due_for_midnight_kick=is_due_for_midnight_kick(
            joined_date,
            last_post_date,
            evaluation_date,
        ),
    )


def split_evening_warning_members(
    snapshots: list[dict],
    evaluation_date: str,
) -> tuple[list[ComplianceState], list[ComplianceState]]:
    missing = []
    due_for_kick = []

    for snapshot in snapshots:
        state = evaluate_member(snapshot, evaluation_date)
        if not state.missing_today:
            continue
        missing.append(state)
        if state.due_for_midnight_kick:
            due_for_kick.append(state)

    return missing, due_for_kick


def select_midnight_kick_members(
    snapshots: list[dict],
    evaluation_date: str,
) -> list[ComplianceState]:
    due = []
    for snapshot in snapshots:
        state = evaluate_member(snapshot, evaluation_date)
        if state.due_for_midnight_kick:
            due.append(state)
    return due
