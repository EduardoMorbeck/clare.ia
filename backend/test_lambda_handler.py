"""Testa o caminho do Lambda localmente, sem AWS.

A ideia: o API Gateway entrega ao Lambda um *evento* (um dicionário JSON), não
uma requisição HTTP de verdade. Aqui montamos um evento desses à mão e o
passamos para o `handler` (o Mangum). Se o FastAPI responder corretamente, é
prova de que toda a tradução evento → ASGI → resposta funciona — exatamente o
que acontecerá na nuvem, mas rodando na sua máquina e no CI.
"""
import json
from types import SimpleNamespace

import main


def _api_gateway_event(method: str, path: str) -> dict:
    """Monta um evento mínimo no formato do API Gateway HTTP API (payload v2.0)."""
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "test.local"},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.1",
            },
            "stage": "$default",
            "requestId": "test-request-id",
            "apiId": "test-api",
            "domainName": "test.local",
        },
        "isBase64Encoded": False,
    }


# O segundo argumento que a AWS passa ao handler é o "context" (metadados da
# execução). O Mangum lê alguns campos dele, então fornecemos um objeto simples.
_LAMBDA_CONTEXT = SimpleNamespace(
    function_name="clare-test",
    memory_limit_in_mb=128,
    invoked_function_arn="arn:aws:lambda:local:0:function:clare-test",
    aws_request_id="test-request-id",
)


def test_handler_responde_health():
    event = _api_gateway_event("GET", "/health")

    response = main.handler(event, _LAMBDA_CONTEXT)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "ok"
    # /health expõe os provedores ativos; deve haver ao menos um configurado.
    assert isinstance(body["providers"], list)
