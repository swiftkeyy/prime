from __future__ import annotations

from fastapi import FastAPI

from web.platega_routes import router as platega_router
from web.telegram_webhook import router as telegram_router


def create_app(*, bot, dp, settings, sessionmaker, redis, engine, username_checker) -> FastAPI:
    app = FastAPI(title="PRIME NICK", version="1.0.0")
    app.state.bot = bot
    app.state.dp = dp
    app.state.settings = settings
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis
    app.state.engine = engine
    app.state.username_checker = username_checker

    app.include_router(telegram_router)
    app.include_router(platega_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "prime_nick"}

    return app
