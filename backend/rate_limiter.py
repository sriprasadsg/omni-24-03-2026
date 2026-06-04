"""Shared SlowAPI limiter instance used across routers."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute", "2000/hour"],
    headers_enabled=True,
)
