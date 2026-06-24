# clare.ia

Assistente de **reflexão emocional** em português do Brasil. Conversa de forma
acolhedora para ajudar a pessoa a organizar pensamentos e sentimentos.

> Esta é uma ferramenta de reflexão e **não substitui acompanhamento
> profissional**. Em caso de sofrimento intenso, procure ajuda — no Brasil, o
> CVV atende pelo telefone **188**.

## Arquitetura

- **Backend** — FastAPI com resposta em streaming e uma camada de provedores de
  IA com *fallback* automático (`backend/`). A ordem padrão é
  **Mistral → Gemini → Groq**: o primeiro provedor com chave configurada e
  disponível responde; se ele falhar ao abrir o stream, o próximo assume.
- **Frontend** — React 18 + Vite + TypeScript (`frontend/`). Chat com streaming,
  sugestões de resposta dinâmicas e botão para interromper a geração.

A persona e os guardrails de segurança são definidos **no servidor** e não podem
ser sobrescritos pelo cliente.

## Pré-requisitos

- Python 3.11+
- Node.js 18+
- Pelo menos uma chave de API entre Mistral, Gemini e Groq.

## Configuração

Copie o template de variáveis de ambiente para a raiz do projeto e preencha as
chaves:

```bash
cp .env.example .env
```

Variáveis disponíveis (veja `.env.example`):

| Variável | Descrição | Padrão |
| --- | --- | --- |
| `LLM_PROVIDERS` | Ordem de fallback dos provedores | `mistral,gemini,groq` |
| `MISTRAL_API_KEY` / `MISTRAL_MODEL` | Chave e modelo da Mistral | — / `mistral-small-latest` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Chave e modelo do Gemini | — / `gemini-2.5-flash-lite` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Chave e modelo do Groq | — / `llama-3.3-70b-versatile` |
| `ALLOWED_ORIGINS` | Origens permitidas no CORS (separadas por vírgula) | `http://localhost:5173` |
| `MAX_HISTORY_MESSAGES` | Máximo de mensagens do histórico reenviadas ao modelo | `20` |

> Mantenha o `.env.example` apenas com placeholders — chaves reais vão somente no
> `.env` (que está no `.gitignore`).

## Backend

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

## Frontend

```bash
cd frontend
npm install
npm run dev                     # sobe em http://localhost:5173
```

O Vite faz proxy de `/api` para o backend em `http://localhost:8000`.
