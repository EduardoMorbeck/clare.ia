import { describe, expect, it } from "vitest";
import { parseOptions } from "./parseOptions";

describe("parseOptions", () => {
  it("separa texto e opções quando a marca está completa", () => {
    const r = parseOptions("Como você está?\n[[OPCOES]] Bem | Mais ou menos | Mal");
    expect(r.text).toBe("Como você está?");
    expect(r.options).toEqual(["Bem", "Mais ou menos", "Mal"]);
  });

  it("ignora segmentos vazios entre as barras", () => {
    const r = parseOptions("Oi\n[[OPCOES]] a | | b |");
    expect(r.options).toEqual(["a", "b"]);
  });

  it("esconde a marca parcial durante o streaming", () => {
    expect(parseOptions("Texto em andamento [[OP").text).toBe("Texto em andamento");
    expect(parseOptions("Texto em andamento [[OP").options).toEqual([]);
  });

  it("retorna o texto puro quando não há marca", () => {
    const r = parseOptions("Só um texto comum, sem opções.");
    expect(r.text).toBe("Só um texto comum, sem opções.");
    expect(r.options).toEqual([]);
  });

  it("não confunde colchetes comuns no meio do texto com a marca", () => {
    const r = parseOptions("Li um livro [parte 2] ontem");
    expect(r.text).toBe("Li um livro [parte 2] ontem");
    expect(r.options).toEqual([]);
  });
});
