from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import Redis

from config import Settings
from database.session import create_engine, create_sessionmaker
from handlers import admin, discovery, documents, errors, filters, menu, payments, prime, profile, promo, search, start, support
from middlewares.antiflood import AntiFloodMiddleware
from middlewares.logging import LoggingMiddleware
from middlewares.user_register import UserRegisterMiddleware
from services.username_checker import build_checker

logger = logging.getLogger(__name__)


def create_runtime(settings: Settings):
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(with_destiny=True))
    dp = Dispatcher(storage=storage)

    engine = create_engine(settings.DATABASE_URL)
    sessionmaker = create_sessionmaker(engine)
    username_checker = build_checker(settings)

    dp["settings"] = settings
    dp["redis"] = redis
    dp["engine"] = engine
    dp["sessionmaker"] = sessionmaker
    dp["username_checker"] = username_checker

    dp.update.outer_middleware(LoggingMiddleware())
    dp.message.middleware(AntiFloodMiddleware(redis))
    dp.callback_query.middleware(AntiFloodMiddleware(redis))
    dp.message.middleware(UserRegisterMiddleware(sessionmaker, settings))
    dp.callback_query.middleware(UserRegisterMiddleware(sessionmaker, settings))
    dp.pre_checkout_query.middleware(UserRegisterMiddleware(sessionmaker, settings))

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(search.router)
    dp.include_router(discovery.router)
    dp.include_router(filters.router)
    dp.include_router(profile.router)
    dp.include_router(prime.router)
    dp.include_router(payments.router)
    dp.include_router(promo.router)
    dp.include_router(documents.router)
    dp.include_router(support.router)
    dp.include_router(admin.router)
    dp.include_router(errors.router)

    return bot, dp, redis, engine, sessionmaker, username_checker
