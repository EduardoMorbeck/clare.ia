# --- Variáveis de entrada (parametrizam a infra) ---
# Variáveis evitam valores "chumbados" no código e permitem trocar de ambiente
# (local x AWS real) sem editar os recursos.

variable "aws_region" {
  description = "Região da AWS onde os recursos são criados."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefixo de nomes dos recursos, para identificá-los facilmente."
  type        = string
  default     = "clare-ia"
}

variable "lambda_runtime" {
  description = "Runtime da função Lambda (deve casar com a versão do Python do projeto)."
  type        = string
  default     = "python3.12"
}

variable "api_stage_name" {
  description = "Nome do stage do API Gateway (aparece na URL, ex.: /prod/health)."
  type        = string
  default     = "prod"
}

variable "enable_cloudfront" {
  description = <<-EOT
    Liga a distribuição CloudFront (e a política de bucket que depende dela).
    A licença do LocalStack NÃO inclui o CloudFront, então localmente fica
    `false` (só o S3 é validado). Na AWS real (Fase 4), defina `true`.
  EOT
  type        = bool
  default     = false
}

variable "lambda_aws_endpoint_url" {
  description = <<-EOT
    Endpoint AWS que a Lambda usa para chamar outros serviços (ex.: SSM) via boto3.
    Na AWS real, deixe VAZIO (o boto3 usa os endpoints padrão da AWS). No LocalStack,
    o container da função NÃO enxerga o `localhost` do host: aponte para o gateway
    do LocalStack acessível de dentro da rede Docker
    (ex.: "http://localhost.localstack.cloud:4566"). Só é injetado se não-vazio.
  EOT
  type        = string
  default     = ""
}

variable "provider_key_names" {
  description = <<-EOT
    Nomes dos parâmetros SSM de chaves de provedor que SEMPRE existem na infra,
    independentemente de termos os valores em mãos. O `for_each` do
    aws_ssm_parameter.provider_keys itera por esta lista (estática, não-sensível) —
    nunca pelas chaves do mapa de segredos — para que o pipeline de CD possa rodar
    sem os valores sem destruir os parâmetros. Os VALORES vêm do tfvars local na 1ª
    semeadura e depois são ignorados (lifecycle ignore_changes em ssm.tf).
  EOT
  type        = list(string)
  default     = ["GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY"]
}

variable "provider_api_keys" {
  description = <<-EOT
    Mapa nome->valor das chaves de API dos provedores LLM, gravadas como
    SecureString no SSM Parameter Store. Defina os valores reais em um
    terraform.tfvars (NUNCA versionado). Veja example.tfvars como modelo.
    Ex.: { GEMINI_API_KEY = "...", GROQ_API_KEY = "..." }
  EOT
  type        = map(string)
  default     = {}
  sensitive   = true
}
