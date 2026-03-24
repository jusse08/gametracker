import pytest

from app.main import validate_runtime_security_config


def test_runtime_security_config_rejects_placeholder_secret_key(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_DEFAULTS", raising=False)
    monkeypatch.setenv("SECRET_KEY", "REPLACE_WITH_A_LONG_RANDOM_SECRET_KEY")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "valid-test-password")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_runtime_security_config()


def test_runtime_security_config_rejects_placeholder_superadmin_password(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_DEFAULTS", raising=False)
    monkeypatch.setenv("SECRET_KEY", "valid-test-secret")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "REPLACE_WITH_A_STRONG_SUPERADMIN_PASSWORD")

    with pytest.raises(RuntimeError, match="SUPERADMIN_PASSWORD"):
        validate_runtime_security_config()


def test_runtime_security_config_allows_explicit_override(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULTS", "true")
    monkeypatch.setenv("SECRET_KEY", "REPLACE_WITH_A_LONG_RANDOM_SECRET_KEY")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "REPLACE_WITH_A_STRONG_SUPERADMIN_PASSWORD")

    validate_runtime_security_config()


def test_runtime_security_config_rejects_origin_without_scheme(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_DEFAULTS", raising=False)
    monkeypatch.setenv("SECRET_KEY", "valid-test-secret")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "valid-test-password")
    monkeypatch.setenv("ALLOWED_ORIGINS", "localhost:3000")

    with pytest.raises(RuntimeError, match="Invalid origin format"):
        validate_runtime_security_config()


def test_runtime_security_config_rejects_partial_wildcard_origin(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_DEFAULTS", raising=False)
    monkeypatch.setenv("SECRET_KEY", "valid-test-secret")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "valid-test-password")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://*.example.com")

    with pytest.raises(RuntimeError, match="wildcard"):
        validate_runtime_security_config()
