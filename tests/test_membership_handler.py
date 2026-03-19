from types import SimpleNamespace

import pytest
import pytest_asyncio

from bot import config
from bot.db.models import init_db
from bot.db.queries import get_member
from bot.handlers.membership import on_chat_join_request


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    config.DB_PATH = str(tmp_path / "test.db")
    await init_db()
    yield


@pytest.mark.asyncio
async def test_join_request_is_only_recorded_as_pending():
    join_request = SimpleNamespace(
        chat=SimpleNamespace(id=config.CHANNEL_ID),
        from_user=SimpleNamespace(
            id=100,
            username="alice",
            first_name="Alice",
            last_name="Writer",
            is_bot=False,
        ),
    )

    await on_chat_join_request(join_request)

    member = await get_member(100)
    assert member is not None
    assert member["status"] == "pending"
    assert member["is_active"] == 0
    assert member["is_channel_admin"] == 0
