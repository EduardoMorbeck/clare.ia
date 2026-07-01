# 0006 — Build reprodutível do pacote da Lambda

- **Status:** Aceito
- **Data:** 2026-06-30

## Contexto

O pacote da Lambda é montado por `infra/build_lambda.py` (instala as dependências como
wheels Linux + copia o código) e zipado pelo `archive_file` do Terraform. O
`source_code_hash` do `aws_lambda_function` é o `sha256` desse zip: o Terraform
re-deploya a função quando o hash muda.

O problema: o hash **variava a cada build mesmo sem mudança de código**, fazendo o CD
re-deployar a Lambda **à toa** em todo merge. Investigando (dois builds comparados
arquivo a arquivo), descobriram-se **quatro** fontes de não-determinismo — não só uma.

## Decisão

Tornar o build **reprodutível byte a byte**, atacando as quatro fontes:

1. **Dependências transitivas soltas** → **lock pinado com hash.**
   `requirements-lambda.in` (pacotes de topo, fonte de verdade) → `lock_lambda_deps.py`
   gera `requirements-lambda.txt` com **toda** a árvore pinada (`==`) e com `sha256`,
   resolvida para a plataforma do Lambda via `pip install --dry-run --report` usando os
   **mesmos flags** do install real. O build instala com `--require-hashes`.
2. **`.pyc` da máquina de build** → **`--no-compile`.** O pip, por padrão, pré-compila
   bytecode com o interpretador local (3.13 no dev, 3.12 no CI) — inútil no runtime 3.12
   e não-portável entre máquinas.
3. **`bin/` e `*.dist-info/RECORD` específicos de host** → **removidos antes de zipar.**
   Wrappers de console-script (`.exe` no Windows, shell no Linux) e o manifesto que
   registra o hash deles. Inúteis no Lambda (que invoca `main.handler`).
4. **`mtime` de instalação gravado no zip** → **normalizado** para um instante fixo
   (`os.utime`). O provider `archive` 2.8.0 **não** normaliza os timestamps.

**Teste de aceite:** dois builds consecutivos produzem `source_code_hash` **idêntico**,
verificado localmente com um config Terraform descartável (só o `data archive_file`,
sem AWS).

## Consequências

**Positivas**
- O CD só re-deploya a Lambda **quando o código realmente muda** — fim do deploy
  cosmético e dos diffs ruidosos.
- **Integridade de supply-chain:** `--require-hashes` faz o build **falhar** se uma
  wheel baixada não bater com o hash do lock (versão trocada, mirror comprometido).
- Build **idêntico entre Windows (dev) e o runner Linux (CI)**.
- Pacote ~47% menor (5880 → 3088 arquivos), sem os `.pyc`.

**Negativas / trade-offs**
- Atualizar dependência exige **dois passos**: editar o `.in` e rodar
  `lock_lambda_deps.py` para regenerar o `.txt`.
- O lock é específico da plataforma-alvo (`manylinux2014_x86_64` / `cp312`); mudar o
  runtime exige regenerar o lock.

## Alternativas consideradas

- **`pip-compile` (pip-tools) / `uv` / Docker** para gerar o lock: todos exigiriam
  ferramenta extra. O `pip --report` reaproveita o pip já presente e resolve com os
  flags idênticos aos do install — fidelidade ao runtime por construção.
- **Ignorar o re-deploy cosmético:** rejeitado — era a última dívida técnica do CD e
  poluía cada `plan`, dificultando ver mudanças reais.
