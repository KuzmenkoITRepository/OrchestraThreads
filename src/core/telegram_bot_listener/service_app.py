from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from core.telegram_bot_listener.http_handlers import TelegramBotHttpHandlers

if TYPE_CHECKING:
    from core.telegram_bot_listener.service_runtime import TelegramBotListenerService


def build_app(service: TelegramBotListenerService) -> web.Application:
    app = web.Application()
    handlers = TelegramBotHttpHandlers(service)
    app.router.add_get("/healthz", handlers.healthz)
    app.router.add_post("/api/v1/messages", handlers.send_message)
    app.router.add_post("/api/v1/buttons", handlers.send_buttons)
    app.router.add_post("/api/v1/surveys", handlers.create_survey)
    app.router.add_get("/api/v1/history", handlers.history)
    return app


def service_site(service: TelegramBotListenerService) -> web.TCPSite:
    assert service._runner is not None
    return web.TCPSite(service._runner, host=service.config.host, port=service.config.port)
