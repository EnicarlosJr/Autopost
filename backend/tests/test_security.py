from app.core.security import create_access_token, hash_password, read_access_token, verify_password
from app.core.ratelimit import LoginLimiter

def test_password_hash_and_token_round_trip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s" * 40)
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)
    token = create_access_token("admin@localhost")
    assert read_access_token(token) == "admin@localhost"
    assert read_access_token("invalid-token") is None

def test_tokens_are_rejected_without_a_strong_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s" * 40)
    token = create_access_token("admin@localhost")
    monkeypatch.setenv("JWT_SECRET", "")
    assert read_access_token(token) is None

def test_login_limiter_blocks_after_repeated_failures():
    limiter = LoginLimiter(max_failures=3, window_seconds=60)
    for _ in range(3):
        assert limiter.retry_after("ip|a@b") == 0
        limiter.fail("ip|a@b")
    assert limiter.retry_after("ip|a@b") > 0
    limiter.reset("ip|a@b")
    assert limiter.retry_after("ip|a@b") == 0
