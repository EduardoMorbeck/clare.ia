"""Testes do guardrail de crise e da validação de entrada (sem rede)."""
import pytest
from pydantic import ValidationError

import main


def test_detecta_risco_em_frases_de_alto_sinal():
    assert main.RISK_PATTERNS.search("às vezes penso em me matar")
    assert main.RISK_PATTERNS.search("não quero mais viver")
    assert main.RISK_PATTERNS.search("queria sumir de vez")


def test_nao_aciona_em_conversa_comum():
    assert not main.RISK_PATTERNS.search("tive um dia difícil no trabalho")
    assert not main.RISK_PATTERNS.search("estou ansioso com a prova de amanhã")


def test_insere_cvv_antes_das_opcoes_quando_ausente():
    resp = "Sinto muito que esteja assim.\n[[OPCOES]] Quero falar mais | Prefiro parar"
    out = main._ensure_support_note(resp)
    assert "188" in out
    # A nota deve vir ANTES da linha de opções, não depois.
    assert out.index("188") < out.index("[[OPCOES]]")


def test_nao_duplica_cvv_se_modelo_ja_mencionou():
    resp = "Procure o CVV no 188, viu?\n[[OPCOES]] Ok | Vou pensar"
    out = main._ensure_support_note(resp)
    assert out.count("188") == 1


def test_anexa_nota_quando_nao_ha_marca_de_opcoes():
    out = main._ensure_support_note("Estou aqui com você.")
    assert out.endswith(main.SUPPORT_NOTE)


def test_rejeita_max_output_tokens_acima_do_teto():
    with pytest.raises(ValidationError):
        main.ChatConfig(max_output_tokens=main.MAX_OUTPUT_TOKENS + 1)


def test_rejeita_temperature_fora_da_faixa():
    with pytest.raises(ValidationError):
        main.ChatConfig(temperature=5.0)


def test_rejeita_lista_de_mensagens_grande_demais():
    msgs = [{"role": "user", "text": "oi"}] * (main.MAX_MESSAGES + 1)
    with pytest.raises(ValidationError):
        main.ChatRequest(messages=msgs)


def test_rejeita_role_invalido():
    with pytest.raises(ValidationError):
        main.ChatRequest(messages=[{"role": "system", "text": "oi"}])
