# --- Configuração base do Terraform e dos provedores ---
# Este bloco define qual versão do Terraform e quais "providers" (plugins que
# sabem falar com uma API específica) o projeto usa.
terraform {
  required_version = ">= 1.5"

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
