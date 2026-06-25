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


def test_insere_cvv_quando_ausente():
    out = main._ensure_support_note("Sinto muito que esteja assim.")
    assert "188" in out
    assert out.endswith(main.SUPPORT_NOTE)


def test_nao_duplica_cvv_se_modelo_ja_mencionou():
    out = main._ensure_support_note("Procure o CVV no 188, viu?")
    assert out.count("188") == 1


def test_parse_reply_extrai_message_e_options():
    msg, opts = main._parse_reply('{"message": "Como você está?", "options": ["Bem", "Mal"]}')
    assert msg == "Como você está?"
    assert opts == ["Bem", "Mal"]


def test_parse_reply_remove_cercas_de_codigo():
    raw = '```json\n{"message": "Oi", "options": ["a"]}\n```'
    msg, opts = main._parse_reply(raw)
    assert msg == "Oi"
    assert opts == ["a"]


def test_parse_reply_limpa_e_limita_options():
    raw = '{"message": "x", "options": ["a", " ", "b", "c", "d", "e"]}'
    _, opts = main._parse_reply(raw)
    assert opts == ["a", "b", "c", "d"]


def test_parse_reply_falha_em_json_truncado():
    with pytest.raises(ValueError):
        main._parse_reply('{"message": "truncad')


def test_parse_reply_falha_sem_message():
    with pytest.raises(ValueError):
        main._parse_reply('{"options": ["a"]}')


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
