"""Testes do ProviderRouter — foco na lógica de fallback (sem rede)."""
from providers import LLMProvider, ProviderRouter

import pytest


class _FakeProvider(LLMProvider):
    def __init__(self, name, raw=None, fail=False):
        self.name = name
        self._raw = raw
        self._fail = fail

    def generate_json(self, messages, system_instruction, temperature, max_output_tokens):
        if self._fail:
            raise RuntimeError(f"{self.name} caiu")
        return self._raw


def test_usa_primeiro_provedor_disponivel():
    router = ProviderRouter([
        _FakeProvider("a", '{"message": "olá"}'),
        _FakeProvider("b", '{"message": "não deveria"}'),
    ])
    name, raw = router.generate_json([], "sys", 0.7, 256)
    assert name == "a"
    assert raw == '{"message": "olá"}'


def test_fallback_quando_primeiro_falha():
    router = ProviderRouter([
        _FakeProvider("a", fail=True),
        _FakeProvider("b", '{"message": "resposta do b"}'),
    ])
    name, raw = router.generate_json([], "sys", 0.7, 256)
    assert name == "b"
    assert raw == '{"message": "resposta do b"}'


def test_todos_falham_retorna_none():
    router = ProviderRouter([
        _FakeProvider("a", fail=True),
        _FakeProvider("b", fail=True),
    ])
    name, raw = router.generate_json([], "sys", 0.7, 256)
    assert name is None
    assert raw is None


def test_router_vazio_levanta_erro():
    with pytest.raises(RuntimeError):
        ProviderRouter([])
