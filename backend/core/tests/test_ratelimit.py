import core.ratelimit as rl_mod


class FakeRedis:
    def __init__(self):
        self.d = {}

    def incr(self, key):
        value = self.d.get(key, 0) + 1
        self.d[key] = value
        return value

    def expire(self, key, ttl):
        return True


class FakeClock:
    """Детерминированные часы: sleep продвигает время."""

    def __init__(self, start=1000.0):
        self.t = start

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_allows_up_to_qps_in_one_window(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(rl_mod, "time", clock)
    fake = FakeRedis()
    rl = rl_mod.RateLimiter(fake, qps=10)
    for _ in range(10):
        rl.acquire(timeout=5)
    # всё уместилось в одно окно — время не шелохнулось
    assert clock.t == 1000.0


def test_throttles_over_qps(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(rl_mod, "time", clock)
    fake = FakeRedis()
    rl = rl_mod.RateLimiter(fake, qps=2)  # окно 0.5 c, 2 запроса на окно
    for _ in range(4):
        rl.acquire(timeout=10)
    # 3-й запрос дождался следующее окно — прошло не меньше одного окна
    assert clock.t - 1000.0 >= 0.5


def test_timeout(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(rl_mod, "time", clock)
    fake = FakeRedis()
    # предзаполняем текущее окно, чтобы лимит никогда не проходил
    fake.d[f"ydl:rl:{int(clock.t * 1)}"] = 10**9
    rl = rl_mod.RateLimiter(fake, qps=1)
    try:
        rl.acquire(timeout=0.3)
        raised = False
    except TimeoutError:
        raised = True
    assert raised
