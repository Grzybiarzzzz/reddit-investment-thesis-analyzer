"""Tests for dashboard API key auth and rate limiting."""
import time
from unittest.mock import MagicMock
import pytest
from src.api.auth import check_api_key, record_failed_attempt, is_locked_out, AUTH_MAX_ATTEMPTS, AUTH_LOCKOUT_SECONDS


def test_check_api_key_valid():
    assert check_api_key("secret123", "secret123") is True


def test_check_api_key_invalid():
    assert check_api_key("wrong", "secret123") is False


def test_check_api_key_empty_configured_key_disables_auth():
    assert check_api_key("anything", "") is True
    assert check_api_key("", "") is True


def test_lockout_after_max_attempts():
    ip = "192.168.1.100"
    for _ in range(AUTH_MAX_ATTEMPTS):
        record_failed_attempt(ip)
    assert is_locked_out(ip) is True


def test_no_lockout_before_max_attempts():
    ip = "192.168.1.200"
    for _ in range(AUTH_MAX_ATTEMPTS - 1):
        record_failed_attempt(ip)
    assert is_locked_out(ip) is False


def test_different_ips_independent():
    ip1 = "10.0.0.1"
    ip2 = "10.0.0.2"
    for _ in range(AUTH_MAX_ATTEMPTS):
        record_failed_attempt(ip1)
    assert is_locked_out(ip1) is True
    assert is_locked_out(ip2) is False
