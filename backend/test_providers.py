"""Testes do ProviderRouter — foco na lógica de fallback (sem rede)."""
from providers import LLMProvider, ProviderRouter

import pytest


class _FakeProvider(LLMProvider):
    def __init__(self, name, chunks=None, fail_on_open=False, fail_mid=False):
        self.name = name
        self._chunks = chunks or []
        self._fail_on_open = fail_on_open
        self._fail_mid = fail_mid

    def stream_chat(self, messages, system_instruction, temperature, max_output_tokens):
        if self._fail_on_open:
            raise RuntimeError(f"{self.name} caiu ao abrir")
        for i, chunk in enumerate(self._chunks):
            if self._fail_mid and i == 1:
                raise RuntimeError(f"{self.name} caiu no meio")
            yield chunk


def _run(router):
    return "".join(router.stream_chat([], "sys", 0.7, 256))


def test_usa_primeiro_provedor_disponivel():
    router = ProviderRouter([
        _FakeProvider("a", ["Olá", " mundo"]),
        _FakeProvider("b", ["não", " deveria"]),
    ])
    assert _run(router) == "Olá mundo"


def test_fallback_quando_primeiro_falha_ao_abrir():
    router = ProviderRouter([
        _FakeProvider("a", fail_on_open=True),
        _FakeProvider("b", ["resposta", " do b"]),
    ])
    assert _run(router) == "resposta do b"


def test_falha_no_meio_nao_troca_de_provedor_e_avisa():
    router = ProviderRouter([
        _FakeProvider("a", ["começo", "X", "fim"], fail_mid=True),
        _FakeProvider("b", ["nunca usado"]),
    ])
    out = _run(router)
    assert out.startswith("começo")
    assert "nunca usado" not in out
    assert "⚠️" in out


def test_todos_falham_retorna_mensagem_amigavel():
    router = ProviderRouter([
        _FakeProvider("a", fail_on_open=True),
        _FakeProvider("b", fail_on_open=True),
    ])
    out = _run(router)
    assert "⚠️" in out


def test_router_vazio_levanta_erro():
    with pytest.raises(RuntimeError):
        ProviderRouter([])
