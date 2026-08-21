import pytest

from app.modules.auth_manager.auth_manager import LOGIN_LOCKOUT_SECONDS, LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP, LOGIN_MAX_FAILURES_PER_IP, LoginThrottle
from app.service.exceptions import RateLimitError


def make_throttle():
    clock = {"now": 0.0}
    throttle = LoginThrottle(clock=lambda: clock["now"])
    return throttle, clock


def test_locks_pair_after_max_failures():
    throttle, _ = make_throttle()
    for _ in range(LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP):
        throttle.check("10.0.0.1", "admin")
        throttle.record_failure("10.0.0.1", "admin")
    with pytest.raises(RateLimitError):
        throttle.check("10.0.0.1", "admin")
    throttle.check("10.0.0.2", "admin")
    throttle.check("10.0.0.1", "someone-else")


def test_lock_expires():
    throttle, clock = make_throttle()
    for _ in range(LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP):
        throttle.record_failure("10.0.0.1", "admin")
    clock["now"] = LOGIN_LOCKOUT_SECONDS + 1
    throttle.check("10.0.0.1", "admin")


def test_success_clears_pair_and_account_counters():
    throttle, _ = make_throttle()
    for _ in range(LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP - 1):
        throttle.record_failure("10.0.0.1", "admin")
    throttle.record_success("10.0.0.1", "admin")
    for _ in range(LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP - 1):
        throttle.record_failure("10.0.0.1", "admin")
    throttle.check("10.0.0.1", "admin")


def test_ip_cap_locks_across_accounts():
    throttle, _ = make_throttle()
    for index in range(LOGIN_MAX_FAILURES_PER_IP):
        throttle.record_failure("10.0.0.9", f"user-{index}")
    with pytest.raises(RateLimitError):
        throttle.check("10.0.0.9", "another-user")


def test_username_is_case_insensitive():
    throttle, _ = make_throttle()
    for _ in range(LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP):
        throttle.record_failure("10.0.0.1", "Admin")
    with pytest.raises(RateLimitError):
        throttle.check("10.0.0.1", "admin")
