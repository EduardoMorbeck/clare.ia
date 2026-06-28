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
  lambda_env = merge(
    {
      # Onde a aplicação busca as chaves de provedor no cold start (3.4). O
      # ssm_config.hydrate_env_from_ssm() lê todos os parâmetros sob este prefixo
      # e os injeta em os.environ; sem ele, o app cai no fallback do .env (que não
      # existe no pacote Lambda). Mantém os segredos fora do código e da env var.
      # Nenhuma chave de provedor é "chumbada" aqui — todas vêm do SSM.
      SSM_PARAM_PREFIX = "/${var.project_name}/"
    },
    # Só no LocalStack: o boto3 precisa de um endpoint que o container da função
    # alcance. Na AWS real a var fica vazia e nada é injetado (endpoints padrão).
    var.lambda_aws_endpoint_url != "" ? { AWS_ENDPOINT_URL = var.lambda_aws_endpoint_url } : {}
  )
}
