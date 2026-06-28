# clare.ia

[![CI](https://github.com/EduardoMorbeck/clare.ia/actions/workflows/ci.yml/badge.svg)](https://github.com/EduardoMorbeck/clare.ia/actions/workflows/ci.yml)

Assistente de **reflexão emocional** em português do Brasil. Conversa de forma
acolhedora para ajudar a pessoa a organizar pensamentos e sentimentos.

> Esta é uma ferramenta de reflexão e **não substitui acompanhamento
> profissional**. Em caso de sofrimento intenso, procure ajuda — no Brasil, o
> CVV atende pelo telefone **188**.

## Arquitetura

- **Backend** — FastAPI com resposta em **JSON estruturado** (`{ message,
  options }`) e uma camada de provedores de IA com *fallback* automático
  (`backend/`). A ordem padrão é **Gemini → Groq → Mistral → Cerebras**: o
  primeiro provedor com chave configurada e disponível responde; se ele falhar,
  o próximo assume. Cada provedor é acionado em modo JSON nativo
  (`response_mime_type` no Gemini, `response_format` nos demais). O provedor que
  respondeu é informado ao frontend pelo header `X-LLM-Provider`.
- **Frontend** — React 18 + Vite + TypeScript (`frontend/`). Chat com sugestões
  de resposta dinâmicas (vindas do campo `options`), indicação do provedor em
  uso e botão para interromper a requisição.

A persona e os guardrails de segurança são definidos **no servidor** e não podem
ser sobrescritos pelo cliente.

### Segurança e privacidade

- **Persona e guardrails no servidor** — o cliente não consegue sobrescrevê-los.
- **Guardrail de crise determinístico** — se a mensagem da pessoa contém sinais
  de risco à própria vida, o backend garante a presença do contato do **CVV
  (188)** na resposta, mesmo que o modelo não o inclua.
- **Rate limiting por IP** e **limite de tamanho por mensagem** protegem contra
  abuso e custo descontrolado (configuráveis — veja a tabela abaixo).
- **Privacidade** — as mensagens são processadas por serviços de IA externos
  (Mistral/Gemini/Groq/Cerebras). Não há persistência no servidor; o histórico
  vive apenas na aba do navegador e some ao recarregar a página.

## Pré-requisitos

- Pelo menos uma chave de API entre Mistral, Gemini, Groq e Cerebras.
- **Com Docker** (caminho recomendado): Docker + Docker Compose.
- **Sem Docker** (setup manual): Python 3.11+ e Node.js 18+.

## Configuração

Copie o template de variáveis de ambiente para a raiz do projeto e preencha as
chaves:

```bash
cp .env.example .env
```

Variáveis disponíveis (veja `.env.example`):

| Variável | Descrição | Padrão |
| --- | --- | --- |
| `LLM_PROVIDERS` | Ordem de fallback dos provedores | `gemini,cerebras,groq,mistral` |
| `MISTRAL_API_KEY` / `MISTRAL_MODEL` | Chave e modelo da Mistral | — / `mistral-small-latest` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Chave e modelo do Gemini | — / `gemini-2.5-flash` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Chave e modelo do Groq | — / `openai/gpt-oss-20b` |
| `CEREBRAS_API_KEY` / `CEREBRAS_MODEL` | Chave e modelo da Cerebras | — / `zai-glm-4.7` |
| `ALLOWED_ORIGINS` | Origens permitidas no CORS (separadas por vírgula) | `http://localhost:5173` |
| `MAX_HISTORY_MESSAGES` | Máximo de mensagens do histórico reenviadas ao modelo | `20` |
| `MAX_MESSAGE_CHARS` | Tamanho máximo (caracteres) de uma mensagem | `4000` |
| `MAX_MESSAGES` | Máximo de mensagens aceitas no corpo da requisição | `100` |
| `MAX_OUTPUT_TOKENS` | Teto de tokens de saída que o cliente pode pedir | `2048` |
| `CHAT_RATE_LIMIT` | Limite de requisições por IP no `/api/chat` (formato slowapi) | `30/minute` |
| `TRUST_PROXY_HEADERS` | Usa `X-Forwarded-For` no rate limit (ative só atrás de proxy de confiança) | `false` |

> Mantenha o `.env.example` apenas com placeholders — chaves reais vão somente no
> `.env` (que está no `.gitignore`).

## Executando com Docker

Com o `.env` preenchido, suba tudo com um comando na raiz do projeto:

```bash
docker compose up --build
```

Isso usa o `docker-compose.override.yml` (mesclado automaticamente) e sobe o
ambiente de **desenvolvimento**, com *hot-reload* no backend e no frontend:

| Serviço | URL |
| --- | --- |
| App (frontend, Vite) | http://localhost:5173 |
| Backend (FastAPI, Swagger em `/docs`) | http://localhost:8000 |

O Compose aguarda o backend ficar *healthy* (passar no `/health`) antes de subir o
frontend. Editar arquivos `.py` ou do frontend recarrega na hora — o código é
montado como volume. Para parar: `Ctrl+C` e depois `docker compose down`.

### Produção

Para subir a versão de produção — frontend buildado e servido pelo **Nginx**, que
também faz o proxy reverso de `/api` para o backend —, ignore o override:

```bash
docker compose -f docker-compose.yml up --build
```

| Serviço | URL |
| --- | --- |
| App (Nginx servindo o build) | http://localhost:8080 |

Nesse modo o backend **não** expõe porta ao host (só é acessível pela rede interna,
via Nginx). Como o `TRUST_PROXY_HEADERS` é ativado para o Nginx à frente, o rate
limit por IP usa o IP real do cliente (`X-Forwarded-For`).

## Backend (setup manual)

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash); no Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py                  # sobe em http://127.0.0.1:8000
```

### Testes

```bash
pip install -r requirements-dev.txt
pytest
```

## Frontend (setup manual)

```bash
cd frontend
npm install
npm run dev                     # sobe em http://localhost:5173
npm test                        # roda os testes (vitest)
```

O Vite faz proxy de `/api` para o backend em `http://localhost:8000`.
