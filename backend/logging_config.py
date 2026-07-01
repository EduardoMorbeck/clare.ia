"""Logging estruturado (uma linha = um objeto JSON) para o backend.

Por que JSON? No Lambda, tudo que a aplicação escreve em stdout/stderr vai parar
no CloudWatch Logs. Texto solto é difícil de filtrar; JSON deixa cada campo
(nível, provedor, latência) consultável no CloudWatch Logs Insights sem regex
frágil. O mesmo formato vale localmente (uvicorn/pytest), então o que você vê na
sua máquina é o que aparece na nuvem.

PRIVACIDADE: por decisão de projeto, os logs NUNCA registram o conteúdo das
mensagens do usuário (nem metadados derivados dele) — só dados operacionais
(rota, status, latência, provedor). Ver o middleware em main.py.
"""
from __future__ import annotations

import json
import logging
import os

# Atributos que o próprio logging já põe em todo LogRecord. Usamos este conjunto
# para separar os "extras" (campos passados via logger.info(..., extra={...})) do
# ruído padrão, e assim promover só os extras a chaves de 1º nível no JSON.
_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "aws_request_id", "taskName"}


class JsonFormatter(logging.Formatter):
    """Serializa cada LogRecord como um objeto JSON de uma linha.

    Campos fixos: timestamp, level, logger, message. Qualquer campo passado em
    `extra={...}` vira uma chave de 1º nível (ex.: provider, duration_ms), o que
    permite consultá-lo diretamente no CloudWatch Logs Insights.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Extras estruturados passados pelo chamador.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        # Correlação: um request_id explícito (do middleware) tem prioridade; na
        # falta dele, usamos o id de invocação que o runtime do Lambda injeta em
        # cada record (ausente localmente).
        if "request_id" not in payload:
            request_id = getattr(record, "aws_request_id", None)
            if request_id:
                payload["request_id"] = request_id

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str | int | None = None) -> None:
    """Instala o formatter JSON e ajusta o nível do root logger.

    Idempotente e sensível ao ambiente:
    - No Lambda, o runtime já instalou um handler no root — só trocamos o
      formatter dele (não adicionamos outro, senão os logs sairiam duplicados).
    - Localmente (uvicorn/pytest) não há handler ainda: adicionamos um que
      escreve em stdout.
    """
    level = level or os.getenv("LOG_LEVEL", "INFO")
    root = logging.getLogger()
    root.setLevel(level)

    formatter = JsonFormatter()
    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
