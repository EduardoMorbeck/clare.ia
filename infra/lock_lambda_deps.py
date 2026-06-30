"""Gera o lock pinado das dependências da Lambda (Fase 6 — dívida do CD).

PROBLEMA QUE RESOLVE
--------------------
O requirements-lambda.in fixa só os pacotes de TOPO (fastapi, openai, ...). As
dezenas de dependências transitivas (starlette, pydantic-core, httpx, certifi,
urllib3, ...) ficavam soltas. Como o build_lambda.py instala do PyPI a cada
build, o pip podia resolver versões diferentes ao longo do tempo → o conteúdo do
.zip mudava → o `source_code_hash` (infra/lambda.tf) mudava → o Terraform
re-deployava a Lambda à toa a cada merge, mesmo sem nenhuma mudança de código.

A CORREÇÃO
----------
Travar TODA a árvore (topo + transitivas) numa versão exata, com o sha256 de
cada wheel. Com isso o build vira reprodutível: mesma entrada → mesmo .zip →
mesmo hash → re-deploy só quando o código realmente muda.

COMO O LOCK É RESOLVIDO PARA A PLATAFORMA CERTA
-----------------------------------------------
O Lambda roda Linux (manylinux/cp312); o dev roda Windows. Resolver na máquina
local pegaria as wheels erradas. Por isso usamos o resolvedor do próprio pip em
modo relatório (`pip install --dry-run --report`) com EXATAMENTE os mesmos flags
de plataforma que o build_lambda.py usa no install real (PLATFORM_PIP_ARGS,
importados de lá) — a resolução bate com o runtime por construção, sem precisar
de uv, pip-tools nem Docker. O relatório traz versão + sha256 de cada wheel, que
escrevemos no requirements-lambda.txt no formato que o `pip --require-hashes` lê.

USO
---
    python infra/lock_lambda_deps.py     # edite o .in antes; isto regenera o .txt
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# build_lambda.py mora no mesmo diretório (infra/) e define a "plataforma do
# Lambda". Importá-lo garante que o lock e o install usem flags idênticos.
from build_lambda import BACKEND_DIR, PLATFORM_PIP_ARGS

IN_FILE = BACKEND_DIR / "requirements-lambda.in"
OUT_FILE = BACKEND_DIR / "requirements-lambda.txt"


def resolve() -> list[dict]:
    """Roda o resolvedor do pip para a plataforma do Lambda e devolve o report."""
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.json"
        cmd = [
            sys.executable, "-m", "pip", "install",
            # --dry-run: só resolve, não instala. --report: cospe o JSON da
            # resolução. --ignore-installed: ignora o que já está no venv local
            # (senão o pip omitiria do report os pacotes "já satisfeitos").
            "--dry-run",
            "--ignore-installed",
            "--report", str(report_path),
            *PLATFORM_PIP_ARGS,
            # --platform exige um --target, mesmo no dry-run (nada é escrito lá).
            "--target", str(Path(tmp) / "_unused"),
            "-r", str(IN_FILE),
        ]
        print(">>", " ".join(cmd))
        subprocess.run(cmd, check=True)
        return json.loads(report_path.read_text(encoding="utf-8"))["install"]


def main() -> None:
    installs = resolve()

    # (nome_para_ordenar, nome_original, versao, sha256)
    rows = []
    for item in installs:
        meta = item["metadata"]
        sha = item["download_info"]["archive_info"]["hashes"]["sha256"]
        rows.append((meta["name"].lower(), meta["name"], meta["version"], sha))
    rows.sort()

    lines = [
        "# LOCK GERADO AUTOMATICAMENTE — NÃO EDITE À MÃO.",
        "# Fonte de verdade: requirements-lambda.in. Para regenerar:",
        "#     python infra/lock_lambda_deps.py",
        "#",
        "# Versões + sha256 de TODA a árvore (topo + transitivas), resolvidas para",
        "# a plataforma do Lambda (manylinux2014_x86_64 / cp312). Lido pelo",
        "# build_lambda.py com --require-hashes (build reprodutível e verificável).",
        "",
    ]
    for _, name, version, sha in rows:
        lines.append(f"{name}=={version} \\")
        lines.append(f"    --hash=sha256:{sha}")

    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{len(rows)} pacotes pinados em: {OUT_FILE}")


if __name__ == "__main__":
    main()
