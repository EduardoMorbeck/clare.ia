# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# - PYTHONUNBUFFERED: logs saem na hora (sem buffer), bom pra docker logs.
# - PYTHONDONTWRITEBYTECODE: não gera .pyc dentro do container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instala as dependências primeiro (camada cacheada enquanto requirements não muda).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia só o código da aplicação (o .dockerignore cuida de excluir .venv etc.).
COPY main.py providers.py ./

# Roda como usuário não-root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# host 0.0.0.0 para aceitar conexões de fora do container; sem --reload em produção.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
