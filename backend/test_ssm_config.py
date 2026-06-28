"""Testes da hidratação de env a partir do SSM (3.4) — sem AWS, sem rede.

Injetamos um cliente boto3 falso via monkeypatch para exercitar os três caminhos:
prefixo ausente (no-op), leitura bem-sucedida e falha engolida.
"""
import boto3
import pytest

import ssm_config
from ssm_config import hydrate_env_from_ssm


class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **kwargs):
        # Devolve as páginas pré-montadas, ignorando os argumentos (Path etc.).
        yield from self._pages


class _FakeSsmClient:
    def __init__(self, params):
        # params: lista de (Name, Value) -> uma única página.
        self._pages = [{"Parameters": [{"Name": n, "Value": v} for n, v in params]}]

    def get_paginator(self, name):
        assert name == "get_parameters_by_path"
        return _FakePaginator(self._pages)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Garante um ambiente previsível: sem prefixo e sem as chaves de provedor.
    monkeypatch.delenv("SSM_PARAM_PREFIX", raising=False)
    for key in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_prefixo_ausente_e_noop(monkeypatch):
    # Sem SSM_PARAM_PREFIX, nada deve ser lido nem alterado.
    def _boom(*a, **k):  # se chamado, o teste falha de propósito.
        raise AssertionError("boto3.client não deveria ser chamado sem prefixo")

    monkeypatch.setattr(boto3, "client", _boom)
    assert hydrate_env_from_ssm() == []
    assert "GEMINI_API_KEY" not in os_environ()


def test_carrega_chaves_do_ssm(monkeypatch):
    monkeypatch.setenv("SSM_PARAM_PREFIX", "/clare-ia/")
    fake = _FakeSsmClient([
        ("/clare-ia/GEMINI_API_KEY", "chave-gemini"),
        ("/clare-ia/GROQ_API_KEY", "chave-groq"),
    ])
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    loaded = hydrate_env_from_ssm()

    assert set(loaded) == {"GEMINI_API_KEY", "GROQ_API_KEY"}
    assert os_environ()["GEMINI_API_KEY"] == "chave-gemini"
    assert os_environ()["GROQ_API_KEY"] == "chave-groq"


def test_ssm_sobrescreve_baseline(monkeypatch):
    # Precedência combinada: SSM ganha de um valor pré-existente (ex.: do .env).
    monkeypatch.setenv("SSM_PARAM_PREFIX", "/clare-ia/")
    monkeypatch.setenv("GEMINI_API_KEY", "valor-do-dotenv")
    fake = _FakeSsmClient([("/clare-ia/GEMINI_API_KEY", "valor-do-ssm")])
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    hydrate_env_from_ssm()

    assert os_environ()["GEMINI_API_KEY"] == "valor-do-ssm"


def test_falha_do_boto3_e_engolida(monkeypatch):
    # Endpoint inacessível / sem credencial não pode derrubar o import.
    monkeypatch.setenv("SSM_PARAM_PREFIX", "/clare-ia/")
    monkeypatch.setenv("GEMINI_API_KEY", "valor-do-dotenv")

    def _explode(*a, **k):
        raise RuntimeError("sem credencial / endpoint inacessível")

    monkeypatch.setattr(boto3, "client", _explode)

    assert hydrate_env_from_ssm() == []
    # O baseline do .env permanece intacto.
    assert os_environ()["GEMINI_API_KEY"] == "valor-do-dotenv"


def os_environ():
    # Pequeno helper para deixar as asserts legíveis sem importar os no topo.
    return ssm_config.os.environ
