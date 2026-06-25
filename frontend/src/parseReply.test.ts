import { describe, expect, it } from "vitest";
import { parseReply } from "./parseReply";

describe("parseReply", () => {
  it("extrai message e options de um objeto válido", () => {
    const r = parseReply({ message: "Como você está?", options: ["Bem", "Mal"] });
    expect(r.text).toBe("Como você está?");
    expect(r.options).toEqual(["Bem", "Mal"]);
  });

  it("limpa espaços e ignora opções vazias", () => {
    const r = parseReply({ message: "  Oi  ", options: ["a", "  ", "b"] });
    expect(r.text).toBe("Oi");
    expect(r.options).toEqual(["a", "b"]);
  });

  it("limita a 4 opções", () => {
    const r = parseReply({ message: "x", options: ["a", "b", "c", "d", "e"] });
    expect(r.options).toEqual(["a", "b", "c", "d"]);
  });

  it("tolera options ausente ou com tipo inesperado", () => {
    expect(parseReply({ message: "só texto" }).options).toEqual([]);
    expect(parseReply({ message: "x", options: "a|b" }).options).toEqual([]);
  });

  it("retorna vazios quando o objeto não tem os campos esperados", () => {
    const r = parseReply({});
    expect(r.text).toBe("");
    expect(r.options).toEqual([]);
  });
});
