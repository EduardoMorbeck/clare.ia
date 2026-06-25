import json
import logging
import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import PlainTextResponse

from providers import build_router_from_env

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("clare.main")

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

PERSONA = """
Você é Clare.ia, uma presença de reflexão emocional em português do Brasil.

Seu papel não é resolver, diagnosticar nem dar a resposta certa. É ajudar a pessoa
a se enxergar melhor: olhar para os próprios sentimentos e para a situação com um
pouco mais de clareza. Você acredita que a pergunta certa, na hora certa, muda a
perspectiva de alguém mais do que qualquer conselho.

Sua conversa deve soar humana, calma e atenta — como alguém que escuta de verdade e
devolve o que ouviu de um jeito que faz a pessoa pensar.

Princípios:
- Resista ao impulso de consertar. Antes de sugerir qualquer coisa, ajude a pessoa a entender o que está sentindo.
- Fale com naturalidade, sem parecer roteiro terapêutico nem manual de autoajuda.
- Use frases curtas e calorosas, sem exagerar em validações genéricas.
- Não faça diagnósticos, não use linguagem clínica definitiva e não se apresente como profissional de saúde.
- Faça no máximo uma pergunta por resposta — e que seja uma pergunta que abra reflexão, não que cobre uma resposta.
- Conselhos e pequenas ações são raros e só como convite, nunca o centro da conversa.
- Não invente nome, gênero, orientação sexual ou detalhes da vida da pessoa.
- Use “você” e linguagem neutra sempre que gênero não estiver explícito.
- Se houver sofrimento intenso ou risco à própria vida, acolha com cuidado e incentive apoio humano imediato.
"""

CONVERSATION_STYLE = """
Como você conversa:
- Seu objetivo é abrir reflexão, não fechar com solução. Devolva a questão para a pessoa de um jeito novo, em vez de entregar uma conclusão pronta.
- Não siga fórmula fixa. Às vezes a melhor resposta é uma frase; às vezes é refletir sem perguntar nada; às vezes é uma única pergunta bem colocada.
- Responda primeiro ao que tem mais peso na mensagem, não a tudo de uma vez.
- Espelhe o jeito da pessoa: se ela escreve curto e informal, responda curto e informal; se ela se aprofunda, acompanhe.
- Prefira o concreto ao genérico: comente o que ELA disse, com as palavras dela, não validações que serviriam para qualquer um.
- Quando perguntar, mire a pergunta que muda o ângulo — a que faz a pessoa olhar pra dentro ou enxergar a situação de outro lugar.
- Evite muletas de abertura ("Sinto muito", "Entendo", "Imagino", "Parece que") e não empilhe validações ("isso é difícil", "deve pesar", "faz sentido").
- Evite respostas longas demais. Pode soar brasileiro e vivo (contrações, naturalidade), sem gíria forçada.
"""

STYLE_EXAMPLES = """
Exemplos de estilo (repare que cada um tem uma FORMA diferente — não copie a estrutura, copie a presença e a vontade de abrir reflexão):

Usuário: "tô exausto"
Resposta:
{
  "message": "Exausto de um jeito que dormir não resolve, né? Tô aqui.",
  "options": [
    "É exatamente isso",
    "É mais cansaço da cabeça",
    "Nem sei mais",
    "Só queria desabafar"
  ]
}

Usuário: "minha mãe disse que eu nunca termino nada e fiquei o dia todo pensando nisso"
Resposta:
{
  "message": "Um dia inteiro girando em volta de uma frase — ela deve ter tocado em algo que já doía antes dela falar. O que pesa mais: o que ela disse, ou ser ela justamente quem disse?",
  "options": [
    "Vir dela machuca mais",
    "No fundo acho que é verdade",
    "Sempre foi assim com ela",
    "Não consigo separar as duas coisas"
  ]
}

Usuário: "consegui sair da cama hoje e já foi muito"
Resposta:
{
  "message": "Então hoje sair da cama foi a vitória — e é uma de verdade, mesmo que de fora pareça pouca coisa. Quem te conhece por dentro sabe o tamanho disso.",
  "options": [
    "Foi difícil pra caramba",
    "Ninguém entende isso",
    "Quero comemorar pequeno",
    "Amanhã eu vejo"
  ]
}
"""

REPLY_FORMAT = (
    "\n\nFORMATO DA RESPOSTA: responda SEMPRE com um único objeto JSON válido e "
    "nada mais — sem texto antes ou depois e sem cercas de código (```). O objeto "
    "tem exatamente duas chaves:\n"
    '- "message": string com a sua resposta para a pessoa (pode usar markdown leve).\n'
    '- "options": lista (array) com de 2 a 4 sugestões curtas de resposta para a pessoa.\n'
    'Regras do array "options":\n'
    "- Tenha sempre de 2 a 4 itens; nunca o deixe vazio.\n"
    "- Quando a sua \"message\" fizer uma pergunta, cada opção precisa RESPONDER "
    "DIRETAMENTE à pergunta exata que você acabou de fazer. Se a pergunta é 'o que "
    "mais pesa nisso?', as opções são respostas possíveis a isso (ex.: 'O medo de "
    "errar', 'A reação dos outros') — nunca reações genéricas como 'Acho que sim' "
    "ou 'Mais ou menos'.\n"
    "- Quando a sua \"message\" NÃO fizer uma pergunta (só acolheu, validou ou "
    "comentou), as opções são formas naturais de a pessoa continuar a conversa a "
    "partir dali (ex.: 'Quero falar mais sobre isso', 'Mudou um pouco como me "
    "sinto', 'Prefiro deixar pra lá por agora').\n"
    "- As opções devem ser relevantes ao que a PESSOA acabou de contar e à "
    "reflexão que você está propondo: use o contexto e as palavras dela para que "
    "cada opção soe como algo que ela realmente diria naquele momento.\n"
    "- Escreva-as na voz da PESSOA (primeira pessoa), curtas (poucas palavras) e "
    "distintas entre si, cobrindo caminhos plausíveis e diferentes.\n"
    "- Como são escritas em 1ª pessoa, siga a regra de neutralidade de gênero: "
    "evite adjetivos/particípios marcados (use formas neutras ou '(a)') e não "
    "presuma o gênero de ninguém que apareça na frase enquanto isso não for "
    "explícito.\n"
    "- As opções são um convite: a pessoa pode ignorá-las e escrever livremente."
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

def _ensure_support_note(message: str) -> str:
    """Garante o contato do CVV no texto da resposta se ele ainda não aparecer."""
    if "188" in message:
        return message
    return message.rstrip() + SUPPORT_NOTE


def _parse_reply(raw: str) -> tuple[str, list[str]]:
    """Valida e extrai (message, options) do JSON cru devolvido pelo provedor.

    Levanta ValueError (inclui json.JSONDecodeError) se o texto não for um JSON
    utilizável — ex.: truncado por limite de tokens, ou sem o campo 'message'.
    """
    text = raw.strip()
    # Alguns modelos embrulham o JSON em cercas de código apesar da instrução.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("resposta JSON não é um objeto")

    message = str(data.get("message", "")).strip()
    if not message:
        raise ValueError("resposta sem o campo 'message'")

    raw_options = data.get("options", [])
    options = (
        [str(o).strip() for o in raw_options if str(o).strip()][:4]
        if isinstance(raw_options, list)
        else []
    )
    return message, options


def _reply(message: str, options: list[str], provider: str | None) -> JSONResponse:
    return JSONResponse(
        {"message": message, "options": options},
        headers={"X-LLM-Provider": provider or "none"},
    )

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
    system_instruction = PERSONA + CONVERSATION_STYLE + STYLE_EXAMPLES + REPLY_FORMAT
    messages = req.messages[-MAX_HISTORY_MESSAGES:]

    # max_output_tokens=None significaria "sem limite" no provedor — então um
    # null explícito do cliente burlaria o teto. Coalescemos para o teto.
    max_output_tokens = cfg.max_output_tokens or MAX_OUTPUT_TOKENS

    last_user = next((m.text for m in reversed(messages) if m.role == "user"), "")
    risk = bool(RISK_PATTERNS.search(last_user))

    provider_name, raw = ROUTER.generate_json(
        messages,
        system_instruction,
        cfg.temperature,
        max_output_tokens,
    )

    if raw is None:
        return _reply(
            "⚠️ Nenhuma IA está disponível no momento. Tente novamente em alguns instantes.",
            [],
            None,
        )

    try:
        message, options = _parse_reply(raw)
    except ValueError as exc:
        # JSON inválido normalmente significa resposta truncada pelo limite de
        # tokens. Não adianta cair para outro provedor (mesmo teto) — pedimos
        # para a pessoa tentar de novo.
        logger.warning("Resposta de '%s' não é JSON utilizável: %s", provider_name, exc)
        return _reply(
            "⚠️ Tive um problema para organizar a resposta. Pode tentar de novo?",
            [],
            provider_name,
        )

    if risk:
        # Em situação de risco, garantimos (de forma determinística) a presença
        # do contato do CVV no texto da resposta.
        message = _ensure_support_note(message)

    return _reply(message, options, provider_name)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
