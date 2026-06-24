import { Fragment, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

type Item = { role: "user" | "model"; text: string; options?: string[] };

const STARTERS: { label: string; text: string }[] = [
  { label: "Não sei explicar", text: "Não sei explicar direito o que estou sentindo..." },
  { label: "Só quero desabafar", text: "Só quero desabafar um pouco..." },
  { label: "Estou confuso(a)", text: "Estou confuso(a), minha cabeça está meio bagunçada..." },
  { label: "Ansioso(a), mas não sei por quê", text: "Estou ansioso(a), mas não sei explicar por quê..." },
  { label: "Aconteceu algo e não sei como me sinto", text: "Aconteceu uma coisa e não sei bem como me sinto sobre isso..." },
  { label: "Quero entender o que sinto", text: "Queria entender melhor o que estou sentindo..." },
];

const OPCOES_MARK = "[[OPCOES]]";

function parseOptions(raw: string): { text: string; options: string[] } {
  const idx = raw.indexOf(OPCOES_MARK);
  if (idx >= 0) {
    const text = raw.slice(0, idx).trimEnd();
    const options = raw
      .slice(idx + OPCOES_MARK.length)
      .split("|")
      .map((s) => s.trim())
      .filter(Boolean);
    return { text, options };
  }
  const partial = raw.lastIndexOf("[[");
  if (partial >= 0 && OPCOES_MARK.startsWith(raw.slice(partial).trimEnd())) {
    return { text: raw.slice(0, partial).trimEnd(), options: [] };
  }
  return { text: raw, options: [] };
}

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const [canScroll, setCanScroll] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

    let acc = "";
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: baseItems }),
      });
      if (!res.ok || !res.body) throw new Error(`Erro ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        const { text: msg, options } = parseOptions(acc);
        setItems((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "model", text: msg, options };
          return next;
        });
      }
    } catch (err) {
      console.error(err);
      setItems((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "model",
          text: "⚠️ Não consegui responder. Verifique se o backend está rodando.",
        };
        return next;
      });
    } finally {
      setLoading(false);
    }
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

  return (
    <div className="app">
      <header className="header">
        <span className="header-title">clare.ia</span>
        <span className="header-note">
          Esta é uma ferramenta de reflexão e não substitui acompanhamento profissional
        </span>
      </header>

      <div className="messages" ref={listRef} onScroll={measureScroll}>
        {items.length === 0 && (
          <div className="empty">
            <p className="empty-greeting">
              Oi, eu sou o Clare.ia 🌱
              <br />
              Como você quer começar?
            </p>
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
            <p className="empty-hint">…ou escreva do seu jeito no campo abaixo</p>
          </div>
        )}

        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          const showOptions =
            item.role === "model" && isLast && !loading && !!item.options && item.options.length > 0;
          return (
            <Fragment key={i}>
              <div className={`bubble ${item.role}`}>
                {item.role === "model" ? (
                  item.text ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
                  ) : (
                    loading && isLast && "…"
                  )
                ) : (
                  item.text
                )}
              </div>
              {showOptions && (
                <div className="reply-options">
                  {item.options!.map((opt, k) => (
                    <button key={k} className="starter-chip" onClick={() => sendText(opt)} disabled={loading}>
                      {opt}
                    </button>
                  ))}
                </div>
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

      <div className="composer-wrap">
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
          <button
            className="send-btn"
            onClick={sendMessage}
            disabled={loading || !input.trim()}
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
        </div>
      </div>
    </div>
  );
}
