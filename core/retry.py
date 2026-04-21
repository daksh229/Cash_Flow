"""
Retry Decorator
===============
Exponential backoff retry for transient failures. Uses the domain
exception hierarchy to decide what is retryable:
  - ExternalServiceError -> retry
  - anything in `retry_on` -> retry
  - everything else -> raise immediately

Usage:
    from core.retry import retry
    from core.exceptions import ExternalServiceError

    @retry(attempts=3, base_delay=0.5)
    def write_mlflow_run(...): ...
"""

import functools
import logging
import random
import time

from core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


def retry(attempts=3, base_delay=0.5, max_delay=30.0, retry_on=None, jitter=True):
    retry_on = tuple(retry_on or ()) + (ExternalServiceError,)

    def _decorator(fn):
        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            delay = base_delay
            last_err = None
            for i in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except retry_on as e:
                    last_err = e
                    if i == attempts:
                        logger.error(
                            "retry exhausted fn=%s attempts=%d last=%s",
                            fn.__name__, i, e,
                        )
                        raise
                    sleep = delay + (random.random() * delay if jitter else 0)
                    sleep = min(sleep, max_delay)
                    logger.warning(
                        "retry fn=%s attempt=%d/%d error=%s sleeping=%.2fs",
                        fn.__name__, i, attempts, e, sleep,
                    )
                    time.sleep(sleep)
                    delay = min(delay * 2, max_delay)
            raise last_err  # pragma: no cover
        return _wrapped
    return _decorator
