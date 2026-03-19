import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.config import BOT_TOKEN, WEBHOOK_PATH, PORT, WEBAPP_URL
from bot.db.models import init_db
from bot.handlers import channel, group, private, admin
from bot.services.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    await init_db()
    webhook_url = f"{WEBAPP_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")


def create_app() -> web.Application:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Register routers — channel first (channel_post), then admin, group, private
    dp.include_router(channel.router)
    dp.include_router(admin.router)
    dp.include_router(group.router)
    dp.include_router(private.router)

    dp.startup.register(on_startup)

    app = web.Application()

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app["bot"] = bot

    # Start daily summary scheduler
    async def on_app_startup(app):
        app["scheduler_task"] = asyncio.create_task(start_scheduler(bot))

    async def on_app_cleanup(app):
        task = app.get("scheduler_task")
        if task:
            task.cancel()

    app.on_startup.append(on_app_startup)
    app.on_cleanup.append(on_app_cleanup)

    return app


def main():
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
