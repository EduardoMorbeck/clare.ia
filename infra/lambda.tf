# --- Função Lambda (backend FastAPI) ---
# O pacote é montado por `build_lambda.py` em build/lambda_pkg (deps Linux +
# main.py + providers.py). RODE `python infra/build_lambda.py` ANTES do apply.

# Empacota a pasta do build em um .zip. O `archive` provider recalcula o zip
# automaticamente quando o conteúdo da pasta muda.
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/build/lambda_pkg"
  output_path = "${path.module}/build/lambda.zip"
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-api"
  role          = aws_iam_role.lambda.arn
  runtime       = var.lambda_runtime
  handler       = "main.handler" # main.py -> handler (Mangum)

  filename = data.archive_file.lambda.output_path
  # source_code_hash faz o Terraform redeployar quando o conteúdo do zip muda.
  source_code_hash = data.archive_file.lambda.output_base64sha256

  timeout     = 30
  memory_size = 256

  environment {
    variables = local.lambda_env
  }
}

locals {
  # Origem permitida no CORS. Quando o CloudFront está ligado (AWS real), o front
  # door é o domínio dele (HTTPS) — referenciamos o atributo do recurso, então o
  # Terraform cria o CloudFront ANTES da Lambda e injeta o domínio certo numa única
  # passada (sem hardcode e sem 2º apply). Localmente (CF desligado) cai no Vite dev.
  frontend_origin = var.enable_cloudfront ? "https://${aws_cloudfront_distribution.frontend[0].domain_name}" : "http://localhost:5173"

  lambda_env = merge(
    {
      # Onde a aplicação busca as chaves de provedor no cold start (3.4). O
      # ssm_config.hydrate_env_from_ssm() lê todos os parâmetros sob este prefixo
      # e os injeta em os.environ; sem ele, o app cai no fallback do .env (que não
      # existe no pacote Lambda). Mantém os segredos fora do código e da env var.
      # Nenhuma chave de provedor é "chumbada" aqui — todas vêm do SSM.
      SSM_PARAM_PREFIX = "/${var.project_name}/"

      # CORS: sem isto o app cairia no default "http://localhost:5173" e o navegador
      # bloquearia o frontend servido pelo CloudFront. Lido por ALLOWED_ORIGINS em main.py.
      ALLOWED_ORIGINS = local.frontend_origin
    },
    # Só no LocalStack: o boto3 precisa de um endpoint que o container da função
    # alcance. Na AWS real a var fica vazia e nada é injetado (endpoints padrão).
    var.lambda_aws_endpoint_url != "" ? { AWS_ENDPOINT_URL = var.lambda_aws_endpoint_url } : {}
  )
}
