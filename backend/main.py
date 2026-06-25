import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import PlainTextResponse

from providers import build_router_from_env

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ROUTER = build_router_from_env()

# Quantas mensagens (no máximo) do histórico são reenviadas ao modelo. Mantém
# custo e latência sob controle em conversas longas, preservando o fim recente.
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

# Tamanho máximo (em caracteres) de uma única mensagem. Protege contra custo
# descontrolado de tokens e abuso. Mensagens maiores são recusadas com HTTP 422.
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "4000"))

# Máximo de mensagens aceitas no corpo da requisição. O histórico ainda é
# truncado em MAX_HISTORY_MESSAGES antes de ir ao modelo; este limite só evita
# que um POST direto à API envie um corpo gigante (memória/parsing).
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "100"))

# Teto de tokens de saída que o cliente pode pedir. Sem isto, um POST direto à
# API poderia pedir um valor enorme e estourar o custo por requisição.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))
# Valor usado quando o cliente não especifica (nunca acima do teto configurado).
DEFAULT_OUTPUT_TOKENS = min(2048, MAX_OUTPUT_TOKENS)

# Limite de requisições por IP no endpoint de chat (formato do slowapi).
CHAT_RATE_LIMIT = os.getenv("CHAT_RATE_LIMIT", "30/minute")

# Quando o app roda atrás de um reverse proxy/CDN, o IP da conexão é o do
# proxy (igual para todos) — o que faria o rate limit virar um limite GLOBAL.
# Ative isto SOMENTE se houver um proxy de confiança à frente; caso contrário
# um cliente poderia forjar X-Forwarded-For para escapar do limite.
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in {
    "1",
    "true",
    "yes",
}

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]


def _client_ip(request: Request) -> str:
    """IP usado como chave do rate limit, honrando o proxy quando confiável."""
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # O primeiro IP da cadeia é o cliente original.
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)

app = FastAPI(title="clare.ia")
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: PlainTextResponse(
        "Muitas mensagens em pouco tempo. Respire fundo e tente de novo em instantes. 🌱",
        status_code=429,
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    # Permite que o frontend leia qual provedor de IA respondeu.
    expose_headers=["X-LLM-Provider"],
)

PERSONA = (
    "Você é o Clare.ia, um assistente de reflexão emocional acolhedor, calmo e "
    "respeitoso, que conversa em português do Brasil. Seu papel é ajudar a "
    "pessoa a organizar pensamentos e sentimentos e a refletir com mais clareza. "
    "IMPORTANTE: 'Clare.ia' é o SEU nome (da IA), nunca o da pessoa. Você NÃO sabe "
    "o nome de quem fala com você — então NUNCA a chame por um nome (não invente "
    "nenhum e jamais use 'Clare'/'Clare.ia' para se dirigir a ela). Trate-a de forma "
    "neutra, por 'você'. "
    "Você NÃO é um profissional de saúde e NÃO faz diagnósticos. Evite linguagem "
    "clínica definitiva (ex.: 'você tem transtorno X'). Prefira uma fala empática "
    "e exploratória. Quando fizer sentido, sugira com leveza e sem impor pequenas "
    "ações concretas e fáceis que a pessoa poderia experimentar para se sentir um "
    "pouco melhor ou lidar com a situação (sempre como convite, nunca como ordem). "
    "Demonstre curiosidade genuína: ao longo da conversa, faça perguntas leves e "
    "naturais para conhecer melhor a pessoa e o contexto dela, conduzindo o papo de um "
    "jeito humano e nada robótico — sem interrogar nem disparar várias perguntas de uma "
    "vez. "
    "Se a pessoa demonstrar sofrimento intenso ou risco à própria "
    "vida, acolha com cuidado e incentive procurar apoio profissional e a rede de "
    "apoio (no Brasil, o CVV pelo telefone 188)."
)

OPCOES = (
    "\n\nTODA mensagem sua DEVE terminar com de 2 a 4 sugestões curtas de resposta "
    "para a pessoa. Coloque-as na ÚLTIMA linha da mensagem, exatamente neste formato "
    "e sem nada depois:\n"
    "[[OPCOES]] sugestão 1 | sugestão 2 | sugestão 3\n"
    "Regras das opções:\n"
    "- A linha [[OPCOES]] é obrigatória em toda resposta sua, sem exceção. Use-a no "
    "máximo uma vez por mensagem e sempre como última linha.\n"
    "- Quando você fizer uma pergunta, cada sugestão precisa RESPONDER DIRETAMENTE à "
    "pergunta exata que você acabou de fazer. Se a pergunta é 'o que mais pesa "
    "nisso?', as opções são respostas possíveis a isso (ex.: 'O medo de errar', 'A "
    "reação dos outros') — nunca reações genéricas como 'Acho que sim' ou 'Mais ou "
    "menos'.\n"
    "- Quando você NÃO fizer uma pergunta (só acolheu, validou ou comentou), as "
    "sugestões são formas naturais de a pessoa continuar a conversa a partir dali "
    "(ex.: 'Quero falar mais sobre isso', 'Mudou um pouco como me sinto', 'Prefiro "
    "deixar pra lá por agora').\n"
    "- As sugestões devem ser relevantes ao que a PESSOA acabou de contar e à "
    "reflexão que você está propondo: use o contexto e as palavras dela para que "
    "cada opção soe como algo que ela realmente diria naquele momento.\n"
    "- Escreva-as na voz da PESSOA (primeira pessoa), curtas (poucas palavras) e "
    "distintas entre si, cobrindo caminhos plausíveis e diferentes.\n"
    "- As sugestões são um convite: a pessoa pode ignorá-las e escrever livremente."
)

# Sinais de risco à própria vida na ÚLTIMA mensagem da pessoa. Lista deliberadamente
# de alta especificidade para minimizar falsos positivos — se acionar, garantimos
# (de forma determinística, sem depender só do modelo) que o contato do CVV apareça.
RISK_PATTERNS = re.compile(
    r"(me matar|tirar minha vida|dar fim (à|a) (minha )?vida|acabar com tudo|"
    r"não quero (mais )?viver|cansad[oa] de viver|melhor (se eu )?morr|"
    r"queria (sumir|morrer|não existir)|me machucar|me cortar|"
    r"suic[íi]d|automutila)",
    re.IGNORECASE,
)

SUPPORT_NOTE = (
    "\n\nSe você está passando por um momento muito difícil, por favor não enfrente "
    "isso sozinho(a): o **CVV** atende 24h, de graça e em sigilo, pelo telefone "
    "**188** ou em cvv.org.br. Se houver risco imediato, ligue **192** (SAMU)."
)

MARK = "[[OPCOES]]"

def _ensure_support_note(full: str) -> str:
    """Insere a nota do CVV antes da linha [[OPCOES]] se ela ainda não aparecer."""
    if "188" in full:
        return full
    idx = full.find(MARK)
    if idx >= 0:
        return full[:idx].rstrip() + SUPPORT_NOTE + "\n\n" + full[idx:]
    return full.rstrip() + SUPPORT_NOTE

class Message(BaseModel):
    role: Literal["user", "model"]
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

class ChatConfig(BaseModel):
    temperature: float | None = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=DEFAULT_OUTPUT_TOKENS, ge=1, le=MAX_OUTPUT_TOKENS)

class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=MAX_MESSAGES)
    config: ChatConfig | None = ChatConfig()

@app.get("/health")
def health():
    return {"status": "ok", "providers": ROUTER.names}

@app.post("/api/chat")
@limiter.limit(CHAT_RATE_LIMIT)
def chat(request: Request, req: ChatRequest):
    cfg = req.config or ChatConfig()
    # A persona (e seus guardrails de segurança) é sempre definida no servidor —
    # o cliente nunca pode sobrescrevê-la.
    system_instruction = PERSONA + OPCOES
    messages = req.messages[-MAX_HISTORY_MESSAGES:]

    # max_output_tokens=None significaria "sem limite" no provedor — então um
    # null explícito do cliente burlaria o teto. Coalescemos para o teto.
    max_output_tokens = cfg.max_output_tokens or MAX_OUTPUT_TOKENS

    last_user = next((m.text for m in reversed(messages) if m.role == "user"), "")
    risk = bool(RISK_PATTERNS.search(last_user))

    provider_name, gen = ROUTER.open_stream(
        messages,
        system_instruction,
        cfg.temperature,
        max_output_tokens,
    )

    def generate():
        if risk:
            # Em situação de risco, garantimos a presença do CVV. Bufferizamos a
            # resposta (caso raro) para inserir a nota na posição correta, antes
            # das opções de resposta — vale abrir mão do streaming pela segurança.
            yield _ensure_support_note("".join(gen))
        else:
            yield from gen

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"X-LLM-Provider": provider_name or "none"},
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
