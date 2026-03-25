from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot import config
from bot.services import scheduler
from tests.conftest import TEST_CHANNEL


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

    async def fake_warning(bot, ch, evaluation_date: str):
        calls.append(("warning", ch.slug, evaluation_date))

    async def fake_kick(bot, ch, evaluation_date: str):
        calls.append(("kick", ch.slug, evaluation_date))

    async def fake_sync(bot, ch):
        calls.append(("sync", ch.slug, None))

    monkeypatch.setattr(scheduler.queries, "get_state", fake_get_state)
    monkeypatch.setattr(scheduler, "_send_evening_warning", fake_warning)
    monkeypatch.setattr(scheduler, "_run_midnight_enforcement", fake_kick)
    monkeypatch.setattr(scheduler, "_retry_member_sync", fake_sync)
    monkeypatch.setattr(config, "CHANNELS", [TEST_CHANNEL])

    await scheduler._run_due_jobs(FakeBot())

    assert calls == [
        ("warning", "test", "2024-01-15"),
        ("kick", "test", "2024-01-14"),
        ("sync", "test", None),
    ]


@pytest.mark.asyncio
async def test_run_due_jobs_skips_already_processed_jobs(monkeypatch):
    class FakeBot:
        pass

    calls = []
    slug = TEST_CHANNEL.slug
    states = {
        f"{slug}:{scheduler.STATE_LAST_WARNING_DATE}": "2024-01-15",
        f"{slug}:{scheduler.STATE_LAST_KICK_DATE}": "2024-01-14",
    }

    monkeypatch.setattr(
        scheduler,
        "_local_now",
        lambda: datetime(2024, 1, 15, 23, 15, tzinfo=ZoneInfo("Asia/Jerusalem")),
    )

    async def fake_get_state(key: str):
        return states.get(key)

    async def fake_warning(bot, ch, evaluation_date: str):
        calls.append(("warning", evaluation_date))

    async def fake_kick(bot, ch, evaluation_date: str):
        calls.append(("kick", evaluation_date))

    async def fake_sync(bot, ch):
        calls.append(("sync", None))

    monkeypatch.setattr(scheduler.queries, "get_state", fake_get_state)
    monkeypatch.setattr(scheduler, "_send_evening_warning", fake_warning)
    monkeypatch.setattr(scheduler, "_run_midnight_enforcement", fake_kick)
    monkeypatch.setattr(scheduler, "_retry_member_sync", fake_sync)
    monkeypatch.setattr(config, "CHANNELS", [TEST_CHANNEL])

    await scheduler._run_due_jobs(FakeBot())

    assert calls == [("sync", None)]
