from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from functools import wraps
from typing import Any


class TransportAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(TransportAPIError):
    pass


class StationNotFoundError(TransportAPIError):
    pass


class AmbiguousStationError(TransportAPIError):
    def __init__(self, message: str, candidates: list):
        super().__init__(message)
        self.candidates = candidates


def retry_on_transient(max_retries: int = 3, base_delay: float = 1.0):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except TransportAPIError as e:
                    last_exception = e
                    if e.status_code and e.status_code < 500 and not isinstance(e, RateLimitError):
                        raise
                    if attempt == max_retries:
                        raise
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
