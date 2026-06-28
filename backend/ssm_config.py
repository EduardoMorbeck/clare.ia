"""Hidratação das chaves de provedor a partir do SSM Parameter Store (passo 3.4).

Por que existir? Na nuvem (e no LocalStack) os segredos NÃO ficam no código nem
em env var "chumbada": vivem como SecureString no SSM, sob o prefixo /clare-ia/.
Este módulo lê esses parâmetros no cold start e os injeta em `os.environ`, de
modo que `providers.build_router_from_env()` continue lendo via `os.getenv` SEM
saber de onde veio a chave. Assim a camada de provedores não muda.

Gatilho e precedência (combinados no desenho do 3.4):
  - Gatilho: a env var `SSM_PARAM_PREFIX`. AUSENTE -> no-op (dev local usa só o
    `.env`, sem depender de AWS). PRESENTE -> busca no SSM sob esse prefixo.
  - Precedência: o `.env` é carregado ANTES (baseline/fallback); o SSM SOBRESCREVE
    por cima quando presente, pois na nuvem ele é a fonte da verdade.
  - Robustez: qualquer falha (sem credencial, endpoint inacessível, prefixo vazio)
    é logada e ENGOLIDA — nunca derruba o import da aplicação.

boto3 não entra no pacote do Lambda: o runtime Python do Lambda já o traz. Para
dev/testes locais ele está no requirements-dev.txt. boto3 honra `AWS_ENDPOINT_URL`
nativamente, então apontar para o LocalStack não exige nenhum branch aqui.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("clare.ssm")


def hydrate_env_from_ssm() -> list[str]:
    """Carrega os parâmetros sob `SSM_PARAM_PREFIX` para dentro de `os.environ`.

    O nome de cada parâmetro é `<prefixo><NOME_DA_CHAVE>` (ex.:
    `/clare-ia/GEMINI_API_KEY`); só o "leaf" (NOME_DA_CHAVE) vira a env var, que é
    exatamente o que `build_router_from_env` espera.

    Retorna a lista de nomes de chaves carregadas (útil para log/teste). Em caso
    de no-op ou falha, retorna lista vazia.
    """
    prefix = os.getenv("SSM_PARAM_PREFIX")
    if not prefix:
        logger.debug("SSM_PARAM_PREFIX ausente — pulando SSM, usando apenas o .env.")
        return []

    try:
        import boto3
        from botocore.config import Config

        # Fail-fast: um problema de rede com o SSM NUNCA pode prender o cold start
        # até o timeout do Lambda. Timeouts curtos + sem retry fazem a função cair
        # rápido no fallback (.env / env var) em vez de pendurar a requisição.
        client = boto3.client(
            "ssm",
            config=Config(
                connect_timeout=2,
                read_timeout=3,
                retries={"max_attempts": 1},
            ),
        )
        loaded: list[str] = []
        paginator = client.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(
            Path=prefix, WithDecryption=True, Recursive=True
        ):
            for param in page["Parameters"]:
                # Extrai o "leaf": o segmento após o último '/'. Normalizamos o
                # prefixo para tolerar tanto "/clare-ia" quanto "/clare-ia/".
                leaf = param["Name"].rsplit("/", 1)[-1]
                os.environ[leaf] = param["Value"]
                loaded.append(leaf)
    except Exception as exc:  # noqa: BLE001 — qualquer falha é não-fatal de propósito.
        logger.warning(
            "Falha ao ler parâmetros do SSM em '%s' (seguindo com o .env): %s",
            prefix,
            exc,
        )
        return []

    if loaded:
        logger.info("Chaves carregadas do SSM (%s): %s", prefix, loaded)
    else:
        logger.warning("Nenhum parâmetro encontrado no SSM sob '%s'.", prefix)
    return loaded
