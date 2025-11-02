# app/infra/retry.py
import random
import time
import logging
from typing import Callable, TypeVar, Optional, Iterable

T = TypeVar("T")
logger = logging.getLogger(__name__)

def _sleep_with_jitter(base: float, factor: float, attempt: int, cap: float) -> float:
    # exponential backoff met jitter
    delay = min(base * (factor ** attempt), cap)
    jitter = random.uniform(0, delay * 0.25)
    return delay + jitter

def retry_on(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base: float = 0.2,
    factor: float = 2.0,
    cap: float = 2.0,
    is_retryable: Optional[Callable[[Exception], bool]] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> T:
    last_exc: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # type: ignore
            if is_retryable and not is_retryable(e):
                raise
            last_exc = e
            if i == attempts - 1:
                break
            sleep_s = _sleep_with_jitter(base, factor, i, cap)
            if on_retry:
                on_retry(i + 1, e, sleep_s)
            else:
                logger.warning("retry #%s in %.2fs due to %s", i + 1, sleep_s, repr(e))
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc

def retryable(
    *,
    attempts: int = 3,
    base: float = 0.2,
    factor: float = 2.0,
    cap: float = 2.0,
    is_retryable: Optional[Callable[[Exception], bool]] = None,
):
    """Decorator versie."""
    def _wrap(func: Callable[..., T]) -> Callable[..., T]:
        def _inner(*args, **kwargs) -> T:
            return retry_on(
                lambda: func(*args, **kwargs),
                attempts=attempts,
                base=base,
                factor=factor,
                cap=cap,
                is_retryable=is_retryable,
            )
        return _inner
