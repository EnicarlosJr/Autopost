"""Produção: segredos fortes obrigatórios."""
import pytest
import app.main as main


def test_production_refuses_example_secrets(monkeypatch):
    monkeypatch.setattr(main, "PRODUCTION", True)
    monkeypatch.setenv("JWT_SECRET", "replace-with-a-random-secret-of-at-least-32-characters")
    monkeypatch.setenv("ADMIN_PASSWORD", "troque-por-uma-senha-longa")
    monkeypatch.setenv("APP_PUBLIC_URL", "http://localhost:8000")
    with pytest.raises(RuntimeError) as error:
        main.check_production_secrets()
    assert "JWT_SECRET" in str(error.value) and "ADMIN_PASSWORD" in str(error.value) and "https://" in str(error.value)
    monkeypatch.setenv("JWT_SECRET", "q8Zr1xV0mN3pL7tK2wY9bC4dF6gH5jS0aE1uI8oPzX")
    monkeypatch.setenv("ADMIN_PASSWORD", "Uma-Senha-Bem-Longa-2026")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://listas.exemplo.com.br")
    main.check_production_secrets()


def test_local_is_not_checked(monkeypatch):
    monkeypatch.setattr(main, "PRODUCTION", False)
    monkeypatch.setenv("JWT_SECRET", "x")
    main.check_production_secrets()
