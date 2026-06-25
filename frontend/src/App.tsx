import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { parseReply } from "./parseReply";
import "./App.css";

type Item = { role: "user" | "model"; text: string; options?: string[]; provider?: string };

const STARTERS: { label: string; text: string }[] = [
  { label: "Não sei explicar", text: "Não sei explicar direito o que estou sentindo..." },
  { label: "Só quero desabafar", text: "Só quero desabafar um pouco..." },
  { label: "Estou confuso(a)", text: "Estou confuso(a), minha cabeça está meio bagunçada..." },
  { label: "Ansioso(a), mas não sei por quê", text: "Estou ansioso(a), mas não sei explicar por quê..." },
  { label: "Aconteceu algo e não sei como me sinto", text: "Aconteceu uma coisa e não sei bem como me sinto sobre isso..." },
  { label: "Quero entender o que sinto", text: "Queria entender melhor o que estou sentindo..." },
];

// Converte uma resposta HTTP de erro numa mensagem acolhedora para a pessoa.
// O backend já manda textos prontos (ex.: o aviso de rate limit); para erros de
// validação (corpo JSON) usamos uma mensagem própria em vez de expor o JSON.
async function friendlyError(res: Response): Promise<string> {
  if (res.status === 429) {
    const body = await res.text().catch(() => "");
    return (
      body.trim() ||
      "Muitas mensagens em pouco tempo. Respire fundo e tente de novo em instantes. 🌱"
    );
  }
  if (res.status === 413) {
    return "Sua mensagem ficou longa demais. Tente dividir em algo mais curto. 🌱";
  }
  if (res.status === 422) {
    // Validação do servidor (mensagem muito longa, vazia, etc.). Mantemos um
    // texto neutro porque o 422 cobre mais de uma causa.
    return "Não consegui processar sua mensagem. Tente reformular ou encurtar um pouco. 🌱";
  }
  const body = await res.text().catch(() => "");
  const contentType = res.headers.get("content-type") || "";
  if (body.trim() && contentType.includes("text/plain")) return body.trim();
  return `Algo deu errado por aqui (erro ${res.status}). Tente de novo em instantes.`;
}

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const [canScroll, setCanScroll] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  // FLIP: posição vertical do input no render anterior + se a tela estava vazia.
  // Ao sair da tela inicial (centralizado) para a conversa (rodapé), animamos o
  // deslocamento em vez de deixá-lo saltar instantaneamente.
  const prevComposerTop = useRef<number | null>(null);
  const wasEmpty = useRef(true);

  function measureScroll() {
    const el = listRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAtBottom(distance < 80);
    setCanScroll(el.scrollHeight - el.clientHeight > 40);
  }

  useEffect(() => {
    measureScroll();
  }, [items, loading]);

  const isEmpty = items.length === 0;

  // Anima o input deslizando da posição central (tela inicial) para o rodapé
  // assim que a primeira mensagem é enviada, usando a técnica FLIP.
  useLayoutEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    const newTop = el.getBoundingClientRect().top;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (wasEmpty.current && !isEmpty && prevComposerTop.current != null && !reduceMotion) {
      const delta = prevComposerTop.current - newTop;
      if (Math.abs(delta) > 1) {
        el.style.transition = "none";
        el.style.transform = `translateY(${delta}px)`;
        // Força o reflow para que o transform inicial seja aplicado antes da transição.
        void el.offsetHeight;
        requestAnimationFrame(() => {
          el.style.transition = "transform 0.45s cubic-bezier(0.22, 1, 0.36, 1)";
          el.style.transform = "translateY(0)";
        });
      }
    }
    prevComposerTop.current = newTop;
    wasEmpty.current = isEmpty;
  });

  function scrollToBottom() {
    requestAnimationFrame(() => {
      const el = listRef.current;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
  }

  function autoGrow() {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  async function sendText(text: string) {
    if (!text || loading) return;

    const baseItems: Item[] = [...items, { role: "user", text }];
    setItems([...baseItems, { role: "model", text: "" }]);
    setLoading(true);
    scrollToBottom();

    const controller = new AbortController();
    abortRef.current = controller;

    // Mensagem amigável vinda do servidor (ex.: 429/422). Quando preenchida,
    // distingue um erro HTTP de uma falha de rede ("backend caiu").
    let serverMessage: string | null = null;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: baseItems }),
        signal: controller.signal,
      });
      if (!res.ok) {
        serverMessage = await friendlyError(res);
        throw new Error(serverMessage);
      }

      const provider = res.headers.get("X-LLM-Provider") || undefined;
      const { text: msg, options } = parseReply(await res.json());
      setItems((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "model", text: msg, options, provider };
        return next;
      });
      // Acompanha a resposta + opções recém-renderizadas, deslizando suavemente
      // até o fim da conversa.
      scrollToBottom();
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        // Interrompido pela pessoa antes da resposta chegar: remove a bolha
        // vazia do assistente (não há texto parcial sem streaming).
        setItems((prev) => prev.slice(0, -1));
      } else {
        console.error(err);
        const text =
          serverMessage ??
          "⚠️ Não consegui responder. Verifique se o backend está rodando.";
        setItems((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "model", text };
          return next;
        });
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    requestAnimationFrame(autoGrow);
    sendText(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const composer = (
    <div className="composer-wrap" ref={composerRef}>
      <div className="composer">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            autoGrow();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Digite sua mensagem..."
          rows={1}
        />
        {loading ? (
          <button className="send-btn" onClick={stop} aria-label="Parar resposta">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            className="send-btn"
            onClick={sendMessage}
            disabled={!input.trim()}
            aria-label="Enviar"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className={`app ${isEmpty ? "is-empty" : ""}`}>
      {isEmpty ? (
        <div className="hero">
          <h1 className="hero-title">Oi, eu sou o Clare.ia 🌱</h1>
          <p className="hero-desc">
            Me conte como você está se sentindo ou pelo que está passando...
          </p>
          {composer}
          <div className="starters">
            {STARTERS.map((s) => (
              <button
                key={s.label}
                className="starter-chip"
                onClick={() => sendText(s.text)}
                disabled={loading}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="messages" ref={listRef} onScroll={measureScroll}>
            {items.map((item, i) => {
          const isLast = i === items.length - 1;
          const showOptions =
            item.role === "model" && isLast && !loading && !!item.options && item.options.length > 0;
          return (
            <Fragment key={i}>
              <div className={`bubble ${item.role}${item.role === "user" ? " msg-animate-user" : ""}`}>
                {item.role === "model" ? (
                  item.text ? (
                    <div className="msg-animate">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
                    </div>
                  ) : (
                    loading &&
                    isLast && (
                      <span className="typing" aria-label="Clare.ia está digitando" role="status">
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                      </span>
                    )
                  )
                ) : (
                  item.text
                )}
              </div>
              {showOptions && (
                <div className="reply-options">
                  {item.options!.map((opt, k) => (
                    <button
                      key={k}
                      className="starter-chip opt-animate"
                      style={{ animationDelay: `${0.4 + k * 0.1}s` }}
                      onClick={() => sendText(opt)}
                      disabled={loading}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
              {item.role === "model" && item.text && item.provider && item.provider !== "none" && (
                <span
                  className="provider-tag fade-in"
                  style={{
                    animationDelay: `${0.4 + (item.options?.length ?? 0) * 0.1}s`,
                  }}
                >
                  via {item.provider}
                </span>
              )}
            </Fragment>
          );
        })}
          </div>

          {canScroll && !atBottom && (
            <button className="scroll-down" onClick={scrollToBottom} aria-label="Ir para o fim da conversa">
              ↓
            </button>
          )}

          {composer}
        </>
      )}

      <p className="disclaimer">
        Ferramenta de reflexão — não substitui acompanhamento profissional
      </p>
    </div>
  );
}
