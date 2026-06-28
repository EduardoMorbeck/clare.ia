"""Empacota o backend FastAPI para a AWS Lambda (passo 3.3.c).

Por que um script e não só o Terraform? O `archive_file` do Terraform sabe
zipar uma pasta, mas não sabe INSTALAR dependências. E há uma pegadinha: as
libs (pydantic-core, etc.) trazem código compilado específico de plataforma.
Empacotar as wheels do Windows quebraria no Lambda — que roda em Linux x86_64
(inclusive no LocalStack, que executa a função num container Linux).

A solução é pedir ao pip as wheels *manylinux* (Linux) explicitamente, mesmo
rodando o build no Windows:

    pip install --platform manylinux2014_x86_64 --python-version 3.12
                --implementation cp --only-binary=:all: --target build/lambda_pkg ...

Fluxo: este script monta `infra/build/lambda_pkg/` (deps + main.py + providers.py)
e o Terraform (`archive_file`) zipa essa pasta. Rode-o ANTES do `tflocal apply`.
É cross-platform de propósito (Windows agora, runner Linux do CI na Fase 5).
"""
import shutil
import subprocess
import sys
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent
REPO_ROOT = INFRA_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
PKG_DIR = INFRA_DIR / "build" / "lambda_pkg"

# Código-fonte da aplicação que vai na raiz do zip (ao lado das deps).
SOURCE_FILES = ["main.py", "providers.py", "ssm_config.py"]

PYTHON_VERSION = "3.12"


def main() -> None:
    # 1) Limpa o pacote anterior para um build reprodutível.
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    # 2) Instala as dependências como wheels Linux (manylinux), não Windows.
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--platform", "manylinux2014_x86_64",
        "--python-version", PYTHON_VERSION,
        "--implementation", "cp",
        "--only-binary=:all:",
        "--target", str(PKG_DIR),
        "-r", str(BACKEND_DIR / "requirements-lambda.txt"),
    ]
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # 3) Copia o código da aplicação para a raiz do pacote.
    for name in SOURCE_FILES:
        shutil.copy2(BACKEND_DIR / name, PKG_DIR / name)
        print(f"copiado: {name}")

    print(f"\nPacote pronto em: {PKG_DIR}")


if __name__ == "__main__":
    main()
