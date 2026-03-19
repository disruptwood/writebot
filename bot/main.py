import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.config import BOT_TOKEN, DISCUSSION_GROUP_ID, PORT, WEBAPP_URL, WEBHOOK_ALLOWED_UPDATES, WEBHOOK_PATH
from bot.db.models import init_db
from bot.handlers import admin, channel, group, membership, private
from bot.services.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

USE_POLLING = os.environ.get("USE_POLLING", "1") == "1"


def _setup_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(membership.router)
    dp.include_router(channel.router)
    dp.include_router(admin.router)
    dp.include_router(group.router)
    dp.include_router(private.router)
    return dp


# ── Webhook mode ──────────────────────────────────────────────

async def on_startup_webhook(bot: Bot):
    await init_db()
    webhook_url = f"{WEBAPP_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, allowed_updates=WEBHOOK_ALLOWED_UPDATES)
    logger.info("Webhook set to %s", webhook_url)


def create_app() -> web.Application:
    bot = Bot(token=BOT_TOKEN)
    dp = _setup_dispatcher()
    dp.startup.register(on_startup_webhook)

    app = web.Application()

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app["bot"] = bot

    async def on_app_startup(app):
        app["scheduler_task"] = asyncio.create_task(start_scheduler(bot))

    async def on_app_cleanup(app):
        task = app.get("scheduler_task")
        if task:
            task.cancel()

    app.on_startup.append(on_app_startup)
    app.on_cleanup.append(on_app_cleanup)

    return app


# ── Polling mode ──────────────────────────────────────────────

async def run_polling():
    bot = Bot(token=BOT_TOKEN)
    dp = _setup_dispatcher()

    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)

    # ONE-TIME TEST: remove after verifying deploy pipeline
    await bot.send_message(DISCUSSION_GROUP_ID, "тест")
    logger.info("Sent test message to discussion group")

    scheduler_task = asyncio.create_task(start_scheduler(bot))
    logger.info("Starting polling mode")

    try:
        await dp.start_polling(bot, allowed_updates=WEBHOOK_ALLOWED_UPDATES)
    finally:
        scheduler_task.cancel()
        await bot.session.close()


# ── Entry point ───────────────────────────────────────────────

def main():
    if USE_POLLING:
        asyncio.run(run_polling())
    else:
        app = create_app()
        web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
