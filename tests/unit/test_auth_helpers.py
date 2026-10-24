from webmusicfolder.auth import RateLimiter, passwords_match


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_passwords_match():
    assert passwords_match("abc", "abc")
    assert not passwords_match("abc", "abd")
    assert not passwords_match("", "abc")
    assert passwords_match("pässword", "pässword")


def test_rate_limiter_blocks_and_expires():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(4):
        limiter.record_failure("1.1.1.1")
    assert not limiter.blocked("1.1.1.1")
    limiter.record_failure("1.1.1.1")
    assert limiter.blocked("1.1.1.1")
    assert not limiter.blocked("2.2.2.2")
    clock.now = 61
    assert not limiter.blocked("1.1.1.1")


def test_rate_limiter_reset():
    limiter = RateLimiter()
    for _ in range(5):
        limiter.record_failure("ip")
    limiter.reset("ip")
    assert not limiter.blocked("ip")
