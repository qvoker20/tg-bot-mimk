from __future__ import annotations

import os

from redis import Redis
from rq import Queue


def get_redis_connection() -> Redis:
    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "0"))
    password = os.getenv("REDIS_PASSWORD") or None
    return Redis(host=host, port=port, db=db, password=password)


def get_default_queue() -> Queue:
    return Queue("erp-default", connection=get_redis_connection())


def get_heavy_queue() -> Queue:
    return Queue("erp-heavy", connection=get_redis_connection())
