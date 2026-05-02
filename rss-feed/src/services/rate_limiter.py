import asyncio
import time


class RateLimiter:
    def __init__(self, delay_seconds: float = 1.0):
        self.delay_seconds = delay_seconds
        self._domain_last_request: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_domain_lock(self, domain: str) -> asyncio.Lock:
        async with self._global_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = asyncio.Lock()
            return self._domain_locks[domain]

    async def acquire(self, domain: str) -> None:
        """Wait until delay_seconds have passed since the last request to domain."""
        lock = await self._get_domain_lock(domain)
        async with lock:
            now = time.monotonic()
            last = self._domain_last_request.get(domain, 0.0)
            elapsed = now - last
            if elapsed < self.delay_seconds:
                await asyncio.sleep(self.delay_seconds - elapsed)
            self._domain_last_request[domain] = time.monotonic()

    async def notify_retry_after(self, domain: str, retry_after: float) -> None:
        """Extend the next-request delay by a Retry-After value from a 429 response."""
        now = time.monotonic()
        # Set last_request so that acquire() will wait retry_after seconds from now.
        # acquire() waits (delay_seconds - elapsed); elapsed = now - last.
        # To force wait = retry_after: last = now + retry_after - delay_seconds.
        self._domain_last_request[domain] = now + retry_after - self.delay_seconds
