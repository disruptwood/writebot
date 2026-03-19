from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.services import scheduler


@pytest.mark.asyncio
async def test_run_due_jobs_triggers_warning_kick_and_sync(monkeypatch):
    class FakeBot:
        pass

    calls = []
    states = {}

    monkeypatch.setattr(
        scheduler,
        "_local_now",
        lambda: datetime(2024, 1, 15, 22, 31, tzinfo=ZoneInfo("Asia/Jerusalem")),
    )

    async def fake_get_state(key: str):
        return states.get(key)

    async def fake_warning(bot, evaluation_date: str):
        calls.append(("warning", evaluation_date))

    async def fake_kick(bot, evaluation_date: str):
        calls.append(("kick", evaluation_date))

    async def fake_sync(bot):
        calls.append(("sync", None))

    monkeypatch.setattr(scheduler.queries, "get_state", fake_get_state)
    monkeypatch.setattr(scheduler, "_send_evening_warning", fake_warning)
    monkeypatch.setattr(scheduler, "_run_midnight_enforcement", fake_kick)
    monkeypatch.setattr(scheduler, "_retry_member_sync", fake_sync)

    await scheduler._run_due_jobs(FakeBot())

    assert calls == [
        ("warning", "2024-01-15"),
        ("kick", "2024-01-14"),
        ("sync", None),
    ]


@pytest.mark.asyncio
async def test_run_due_jobs_skips_already_processed_jobs(monkeypatch):
    class FakeBot:
        pass

    calls = []
    states = {
        scheduler.STATE_LAST_WARNING_DATE: "2024-01-15",
        scheduler.STATE_LAST_KICK_DATE: "2024-01-14",
    }

    monkeypatch.setattr(
        scheduler,
        "_local_now",
        lambda: datetime(2024, 1, 15, 23, 15, tzinfo=ZoneInfo("Asia/Jerusalem")),
    )

    async def fake_get_state(key: str):
        return states.get(key)

    async def fake_warning(bot, evaluation_date: str):
        calls.append(("warning", evaluation_date))

    async def fake_kick(bot, evaluation_date: str):
        calls.append(("kick", evaluation_date))

    async def fake_sync(bot):
        calls.append(("sync", None))

    monkeypatch.setattr(scheduler.queries, "get_state", fake_get_state)
    monkeypatch.setattr(scheduler, "_send_evening_warning", fake_warning)
    monkeypatch.setattr(scheduler, "_run_midnight_enforcement", fake_kick)
    monkeypatch.setattr(scheduler, "_retry_member_sync", fake_sync)

    await scheduler._run_due_jobs(FakeBot())

    assert calls == [("sync", None)]
