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
    variables = {
      # PROVISÓRIO (3.3.c): o app exige ao menos uma chave de provedor no import,
      # senão levanta RuntimeError. Esta chave fictícia só permite o cold start e
      # o /health; o /api/chat real falharia. No passo 3.4 estas chaves passam a
      # ser lidas do SSM Parameter Store, e este bloco sai.
      GEMINI_API_KEY = "localstack-dummy"
    }
  }
}
