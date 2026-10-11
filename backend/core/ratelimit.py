"""Общий для всех процессов (API + воркеры) ограничитель частоты запросов к API Яндекс Диска.

Простое окно: ключ окна = floor(now * qps). При превышении — короткий сон.
"""

import time


class RateLimiter:
    def __init__(self, redis_client, qps, key_prefix="ydl:rl"):
        self._r = redis_client
        self.qps = max(1, int(qps))
        self.key_prefix = key_prefix

    def acquire(self, timeout=120):
        deadline = time.time() + timeout
        while True:
            window = f"{self.key_prefix}:{int(time.time() * self.qps)}"
            value = self._r.incr(window)
            if value == 1:
                self._r.expire(window, int(2.0 / self.qps) + 1)
            if value <= self.qps:
                return
            if time.time() > deadline:
                raise TimeoutError("Не удалось пройти rate limit за отведённое время")
            time.sleep(0.05)
