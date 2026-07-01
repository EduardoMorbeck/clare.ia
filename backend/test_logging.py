"""Testes do logging estruturado: o formatter JSON e o middleware de request.

Cobrem o contrato que importa em produção: (1) cada linha é um JSON válido com
os campos operacionais certos e (2) o middleware NUNCA vaza conteúdo do usuário.
"""
import json
import logging

from fastapi.testclient import TestClient

import main
from logging_config import JsonFormatter


def _format(record: logging.LogRecord) -> dict:
    """Formata um record com o JsonFormatter e devolve o dict já parseado."""
    return json.loads(JsonFormatter().format(record))


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="clare.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="oi %s",
        args=("mundo",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emite_json_com_campos_fixos():
    out = _format(_record())
    assert out["level"] == "INFO"
    assert out["logger"] == "clare.test"
    assert out["message"] == "oi mundo"  # msg + args interpolados
    assert "timestamp" in out


def test_formatter_promove_extras_a_chaves():
    out = _format(_record(provider="groq", duration_ms=12.3, status=200))
    assert out["provider"] == "groq"
    assert out["duration_ms"] == 12.3
    assert out["status"] == 200


def test_formatter_usa_aws_request_id_como_request_id():
    out = _format(_record(aws_request_id="lambda-inv-123"))
    assert out["request_id"] == "lambda-inv-123"


def test_formatter_prioriza_request_id_explicito():
    out = _format(_record(request_id="req-abc", aws_request_id="lambda-inv-123"))
    assert out["request_id"] == "req-abc"


def test_middleware_loga_metadados_da_requisicao(caplog):
    client = TestClient(main.app)
    with caplog.at_level(logging.INFO, logger="clare.main"):
        resp = client.get("/health")
    assert resp.status_code == 200

    req_logs = [r for r in caplog.records if r.getMessage() == "request"]
    assert len(req_logs) == 1
    log = req_logs[0]
    assert log.method == "GET"
    assert log.path == "/health"
    assert log.status == 200
    assert isinstance(log.duration_ms, float)
    assert log.request_id  # sempre há um id de correlação


def test_middleware_nao_vaza_conteudo_do_usuario(caplog):
    """Garante que o texto enviado pelo usuário NUNCA aparece nos logs."""
    segredo = "meu-segredo-emocional-super-privado"
    client = TestClient(main.app)
    with caplog.at_level(logging.INFO, logger="clare.main"):
        # role inválido → 422 na validação, ANTES de chamar qualquer provedor (sem
        # rede). O segredo vai no corpo mesmo assim: se o middleware o registrasse,
        # o teste pegaria. Ele não deve — só loga metadados.
        client.post("/api/chat", json={"messages": [{"role": "x", "text": segredo}]})

    todo_o_log = "\n".join(JsonFormatter().format(r) for r in caplog.records)
    assert segredo not in todo_o_log
