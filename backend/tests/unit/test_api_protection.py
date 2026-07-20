from security.api_protection import ApiProtector


def test_rate_limit_is_bounded_per_client():
    protector = ApiProtector(api_key=None, requests_per_minute=2)

    assert protector._rate_limit_exceeded("client-a", 1.0) is False
    assert protector._rate_limit_exceeded("client-a", 2.0) is False
    assert protector._rate_limit_exceeded("client-a", 3.0) is True
    assert protector._rate_limit_exceeded("client-b", 3.0) is False


def test_rate_limit_window_expires():
    protector = ApiProtector(api_key=None, requests_per_minute=1)

    assert protector._rate_limit_exceeded("client", 1.0) is False
    assert protector._rate_limit_exceeded("client", 61.0) is False
