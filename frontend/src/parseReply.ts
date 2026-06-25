export type Reply = { text: string; options: string[]; error: boolean };

/**
 * Normaliza a resposta JSON do backend (`{ message, options, error }`) para o
 * formato que a UI consome. É tolerante: campos ausentes ou com tipo inesperado
 * viram valores vazios em vez de quebrar a renderização.
 */
export function parseReply(data: unknown): Reply {
  const obj = (data ?? {}) as Record<string, unknown>;
  const text = typeof obj.message === "string" ? obj.message.trim() : "";
  const options = Array.isArray(obj.options)
    ? obj.options
        .map((o) => String(o).trim())
        .filter(Boolean)
        .slice(0, 4)
    : [];
  return { text, options, error: obj.error === true };
}
