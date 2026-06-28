# --- IAM: identidade e permissões da Lambda ---
# Toda Lambda executa "vestindo" uma IAM Role. A role tem duas partes:
#   1) trust policy  -> QUEM pode assumir a role (aqui: o serviço Lambda).
#   2) permissões    -> O QUE a role pode fazer (aqui: escrever logs; SSM vem depois).

# Quem pode assumir a role: o próprio serviço Lambda da AWS.
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Permissão mínima para a Lambda gravar logs no CloudWatch (cria o log group,
# o log stream e escreve os eventos). É a política gerenciada padrão da AWS.
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Permissão de LEITURA dos segredos no SSM, escopada SÓ ao prefixo do projeto
# (/clare-ia/*) — princípio do menor privilégio. kms:Decrypt é necessário para
# ler parâmetros SecureString (que são cifrados com KMS).
data "aws_iam_policy_document" "lambda_ssm" {
  statement {
    sid     = "ReadProjectParameters"
    actions = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/${var.project_name}/*",
    ]
  }
  statement {
    sid       = "DecryptSecureStrings"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_ssm" {
  name   = "${var.project_name}-ssm-read"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_ssm.json
}
