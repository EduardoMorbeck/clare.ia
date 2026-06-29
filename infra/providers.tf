# --- Configuração base do Terraform e dos provedores ---
# Este bloco define qual versão do Terraform e quais "providers" (plugins que
# sabem falar com uma API específica) o projeto usa.
terraform {
  required_version = ">= 1.5"

  # Backend remoto: o state vive num bucket S3 (durável, versionado, compartilhável
  # com o CI da Fase 5). Bloco PARCIAL de propósito (chaves vazias): os valores
  # concretos (bucket/key/region) entram via `-backend-config=backend.aws.hcl` no
  # `init`. Assim a MESMA config serve para a AWS real e para o LocalStack (onde o
  # `tflocal` injeta o backend automaticamente). `use_lockfile` (Terraform 1.11+)
  # faz a trava nativa no próprio S3 — dispensa o DynamoDB.
  backend "s3" {}

  required_providers {
    # Provider da AWS: cria/gerencia recursos (Lambda, S3, IAM, ...).
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    # Provider "archive": gera arquivos .zip a partir de uma pasta — usado para
    # empacotar o código da Lambda. É um utilitário local, não fala com a AWS.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

# Provider AWS. Ao rodar via `tflocal`, os endpoints e as credenciais são
# automaticamente redirecionados para o LocalStack (http://localhost:4566) —
# por isso o bloco é idêntico ao que usaríamos na AWS real.
provider "aws" {
  region = var.aws_region
}
