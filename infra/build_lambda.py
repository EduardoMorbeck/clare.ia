"""Empacota o backend FastAPI para a AWS Lambda (passo 3.3.c).

Por que um script e não só o Terraform? O `archive_file` do Terraform sabe
zipar uma pasta, mas não sabe INSTALAR dependências. E há uma pegadinha: as
libs (pydantic-core, etc.) trazem código compilado específico de plataforma.
Empacotar as wheels do Windows quebraria no Lambda — que roda em Linux x86_64
(inclusive no LocalStack, que executa a função num container Linux).

A solução é pedir ao pip as wheels *manylinux* (Linux) explicitamente, mesmo
rodando o build no Windows (ver PLATFORM_PIP_ARGS).

Fluxo: este script monta `infra/build/lambda_pkg/` (deps + main.py + providers.py)
e o Terraform (`archive_file`) zipa essa pasta. Rode-o ANTES do `tflocal apply`.
É cross-platform de propósito (Windows agora, runner Linux do CI na Fase 5).

BUILD REPRODUZÍVEL (Fase 6): instala do lock pinado+hasheado
(requirements-lambda.txt, gerado por lock_lambda_deps.py) e remove tudo que varia
entre builds/máquinas — .pyc (--no-compile), wrappers em bin/, RECORD e mtimes.
Assim o .zip é byte-idêntico a cada build: o source_code_hash (lambda.tf) só muda
quando o código muda, e o Terraform para de re-deployar a Lambda à toa.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent
REPO_ROOT = INFRA_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
PKG_DIR = INFRA_DIR / "build" / "lambda_pkg"

# Código-fonte da aplicação que vai na raiz do zip (ao lado das deps).
SOURCE_FILES = ["main.py", "providers.py", "ssm_config.py", "logging_config.py"]

PYTHON_VERSION = "3.12"

# Lock totalmente pinado (gerado por lock_lambda_deps.py a partir do .in).
LAMBDA_REQUIREMENTS = BACKEND_DIR / "requirements-lambda.txt"

# Flags que forçam o pip a baixar wheels Linux (manylinux/cp312) em vez das do
# Windows. SÃO A DEFINIÇÃO de "a plataforma do Lambda" para este projeto — o
# lock_lambda_deps.py importa esta MESMA lista para resolver o lock com os flags
# idênticos aos do install real (senão o lock poderia divergir do que sobe).
PLATFORM_PIP_ARGS = [
    "--platform", "manylinux2014_x86_64",
    "--python-version", PYTHON_VERSION,
    "--implementation", "cp",
    "--only-binary=:all:",
]


def main() -> None:
    # 1) Limpa o pacote anterior para um build reprodutível.
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    # 2) Instala as dependências como wheels Linux (manylinux), não Windows.
    # --require-hashes: o lock traz o sha256 de cada wheel; se o arquivo baixado
    # não bater (versão trocada, wheel adulterada, mirror comprometido), o pip
    # FALHA o build em vez de empacotar algo divergente. Exige que TODO pacote
    # esteja pinado com hash — garantido por lock_lambda_deps.py.
    #
    # --no-compile: por padrão o pip pré-compila .pyc com o interpretador da
    # máquina de build (3.13 aqui, 3.12 no runner do CI). Esses .pyc (a) são
    # inúteis no Lambda — o runtime 3.12 ignora bytecode de outra versão e
    # recompila no cold start — e (b) tornariam o pacote NÃO-reprodutível entre
    # máquinas (Windows vs. runner). Sem eles o conteúdo é idêntico em qualquer
    # build, e o .zip encolhe quase pela metade.
    cmd = [
        sys.executable, "-m", "pip", "install",
        *PLATFORM_PIP_ARGS,
        "--require-hashes",
        "--no-compile",
        "--target", str(PKG_DIR),
        "-r", str(LAMBDA_REQUIREMENTS),
    ]
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # 3) Copia o código da aplicação para a raiz do pacote.
    for name in SOURCE_FILES:
        shutil.copy2(BACKEND_DIR / name, PKG_DIR / name)
        print(f"copiado: {name}")

    # 4) Remove artefatos do instalador que são específicos da MÁQUINA de build
    # (não do runtime) e que quebrariam a reprodutibilidade:
    #   - bin/ : wrappers de console-script (no Windows são .exe; no Linux, shell
    #     scripts). O Lambda invoca main.handler, nunca esses CLIs — e o conteúdo
    #     deles varia a cada build e entre SOs.
    #   - */*.dist-info/RECORD : manifesto que lista o hash de cada arquivo
    #     instalado (inclusive os bin/), logo também varia. É usado só por
    #     `pip uninstall`; o runtime e o importlib.metadata não precisam dele.
    # O resto do dist-info (METADATA, entry_points) fica — libs leem a própria
    # versão via importlib.metadata.
    strip_installer_cruft(PKG_DIR)

    # 5) Normaliza os mtimes. O provider archive grava no .zip o mtime de cada
    # arquivo, e o pip/shutil carimbam a hora da instalação — então, sem isto,
    # cada build geraria um .zip diferente (source_code_hash instável) e o
    # Terraform re-deployaria a Lambda à toa. Fixar um instante constante torna
    # o .zip reprodutível: mesmo conteúdo -> mesmo hash -> deploy só quando o
    # código muda de verdade.
    normalize_mtimes(PKG_DIR)

    print(f"\nPacote pronto em: {PKG_DIR}")


# Instante fixo para todos os arquivos do pacote (2020-01-01 UTC). Qualquer data
# >= 1980 serve (limite do formato .zip); o valor em si é irrelevante, só precisa
# ser constante entre builds.
FIXED_MTIME = 1577836800


def strip_installer_cruft(root: Path) -> None:
    bin_dir = root / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
        print("removido: bin/ (wrappers de console-script)")
    records = list(root.glob("*.dist-info/RECORD"))
    for record in records:
        record.unlink()
    print(f"removidos {len(records)} arquivos RECORD")


def normalize_mtimes(root: Path) -> None:
    count = 0
    for path in root.rglob("*"):
        os.utime(path, (FIXED_MTIME, FIXED_MTIME))
        count += 1
    print(f"mtime normalizado em {count} itens")


if __name__ == "__main__":
    main()
