export const OPCOES_MARK = "[[OPCOES]]";

/**
 * Separa o texto da resposta das sugestões de resposta rápida.
 *
 * O modelo termina cada mensagem com uma linha `[[OPCOES]] a | b | c`. Durante o
 * streaming essa marca pode chegar parcial (ex.: `[[OP`); nesse caso escondemos
 * o fragmento do texto e ainda não emitimos opções.
 */
export function parseOptions(raw: string): { text: string; options: string[] } {
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
