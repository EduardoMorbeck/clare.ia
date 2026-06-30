# --- OIDC: identidade do GitHub Actions na AWS (Fase 5) ---
# Aposenta a access key estática. Em vez de guardar um segredo de longa duração no
# repo, o GitHub Actions prova quem é a cada execução via um token OIDC de ~1h, e a
# AWS troca esse token por credenciais temporárias (sts:AssumeRoleWithWebIdentity).
#
# São 3 peças:
#   1) um OIDC *provider* (cadastra o GitHub como fonte de identidade confiável);
#   2) duas *roles* com trust policy travada no repo + evento;
#   3) as permissões de cada role (o "menor privilégio" possível p/ este pipeline).
#
# BOOTSTRAP (ovo-e-galinha): este arquivo é aplicado UMA vez com a chave estática
# atual (profile clare-deploy). A chave só é deletada DEPOIS do CI provar que assume
# estas roles (passo 5.7). Account id NUNCA é chumbado (repo público) — vem do
# data.aws_caller_identity.current, já declarado em frontend.tf.

locals {
  # owner/repo do GitHub. Usado nas condições das trust policies. Não é segredo
  # (o repo é público), então pode ficar no código versionado.
  github_repo = "EduardoMorbeck/clare.ia"
}

# ----------------------------------------------------------------------------
# 1) OIDC provider: "confio em tokens emitidos por token.actions.githubusercontent.com"
# ----------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  # A "audience" que o GitHub coloca no token quando usamos a action oficial
  # aws-actions/configure-aws-credentials. A AWS exige que bata.
  client_id_list = ["sts.amazonaws.com"]

  # Thumbprint do certificado do emissor. Para ESTE provider específico do GitHub a
  # AWS já valida o token contra uma lista interna de CAs confiáveis e ignora este
  # valor na prática — mantemos o thumbprint público documentado por compatibilidade.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# ----------------------------------------------------------------------------
# 2) Trust policies (QUEM pode assumir cada role) — o cadeado de verdade
# ----------------------------------------------------------------------------
# A claim `sub` do token descreve o job. Formato definido pelo GitHub:
#   push/merge na main -> repo:OWNER/REPO:ref:refs/heads/main
#   evento de PR       -> repo:OWNER/REPO:pull_request
# Travar nessas strings é o que impede um PR malicioso de dar apply.

# Role de PLAN: só assumível por jobs disparados por Pull Request.
data "aws_iam_policy_document" "gha_plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.github_repo}:pull_request"]
    }
  }
}

# Role de APPLY: só assumível por jobs rodando NA branch main (merge/push).
data "aws_iam_policy_document" "gha_apply_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "gha_plan" {
  name               = "${var.project_name}-gha-plan"
  assume_role_policy = data.aws_iam_policy_document.gha_plan_trust.json
}

resource "aws_iam_role" "gha_apply" {
  name               = "${var.project_name}-gha-apply"
  assume_role_policy = data.aws_iam_policy_document.gha_apply_trust.json
}

# ----------------------------------------------------------------------------
# 3a) Acesso ao STATE remoto (as DUAS roles precisam) — ler o state + o lockfile
# ----------------------------------------------------------------------------
# Até o `plan` adquire o lock nativo do S3 (escreve/apaga o objeto .tflock), então
# este acesso de escrita ao lock vale para plan e apply. Escopado SÓ ao state deste
# projeto. O nome do bucket carrega o account id -> derivado do caller identity.
data "aws_iam_policy_document" "tf_state_access" {
  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}"]
  }
  statement {
    sid     = "ReadWriteStateAndLock"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}/clare-ia/prod/terraform.tfstate",
      "arn:aws:s3:::${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}/clare-ia/prod/terraform.tfstate.tflock",
    ]
  }
}

resource "aws_iam_role_policy" "plan_state" {
  name   = "${var.project_name}-tf-state"
  role   = aws_iam_role.gha_plan.id
  policy = data.aws_iam_policy_document.tf_state_access.json
}

resource "aws_iam_role_policy" "apply_state" {
  name   = "${var.project_name}-tf-state"
  role   = aws_iam_role.gha_apply.id
  policy = data.aws_iam_policy_document.tf_state_access.json
}

# ----------------------------------------------------------------------------
# 3b) Permissões de LEITURA da role de plan
# ----------------------------------------------------------------------------
# `terraform plan` faz refresh: lê o estado real de todos os recursos. ReadOnlyAccess
# (gerenciada pela AWS) cobre o Describe/Get/List de tudo, sem PODER alterar nada —
# é a fronteira certa para um job disparado por PR de terceiros.
resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.gha_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# A role de APPLY também recebe ReadOnlyAccess. O `terraform apply` faz um refresh
# (lê TODOS os recursos) antes de aplicar; leitura ampla garante que o refresh nunca
# falhe por uma permissão de leitura faltando. A fronteira que importa segue intacta:
# a ESCRITA é escopada (data.aws_iam_policy_document.tf_apply) e a role só é assumível
# no push para a main. Ler não altera nada.
resource "aws_iam_role_policy_attachment" "apply_readonly" {
  role       = aws_iam_role.gha_apply.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# ----------------------------------------------------------------------------
# 3c) Permissões de ESCRITA da role de apply (o menor privilégio possível aqui)
# ----------------------------------------------------------------------------
data "aws_iam_policy_document" "tf_apply" {
  # API Gateway: rest api, resources, methods, integrations, deployment, stage.
  statement {
    sid       = "ApiGateway"
    actions   = ["apigateway:*"]
    resources = ["arn:aws:apigateway:${var.aws_region}::/*"]
  }

  # CloudFront é um serviço GLOBAL: os ARNs não permitem escopo prático por região
  # ou nome. A fronteira aqui é o TRUST (só merge na main assume esta role).
  statement {
    sid       = "CloudFront"
    actions   = ["cloudfront:*"]
    resources = ["*"]
  }

  # Lambda: só as funções do projeto.
  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-*"]
  }

  # SSM: só os parâmetros do projeto.
  statement {
    sid       = "Ssm"
    actions   = ["ssm:*"]
    resources = ["arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/*"]
  }

  # KMS p/ os SecureString — restrito a quem usa o KMS ATRAVÉS do SSM.
  statement {
    sid       = "KmsViaSsm"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }

  # S3: o bucket do frontend (config do bucket + upload dos objetos do site).
  statement {
    sid     = "FrontendBucket"
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}",
      "arn:aws:s3:::${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}/*",
    ]
  }

  # IAM: gerir as roles/políticas DO PROJETO — inclui a role da Lambda e as próprias
  # roles de CI/o OIDC provider (este arquivo está na mesma config).
  # >>> STATEMENT DE MAIOR PRIVILÉGIO <<< quem dá apply pode mexer em identidades.
  # Escopado por prefixo de nome; é o trade-off consciente de gerenciar a infra de
  # deploy como código. PassRole (da role da Lambda) está coberto por iam:* no ARN.
  statement {
    sid     = "ProjectIam"
    actions = ["iam:*"]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.project_name}-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com",
    ]
  }
}

resource "aws_iam_role_policy" "apply_perms" {
  name   = "${var.project_name}-tf-apply"
  role   = aws_iam_role.gha_apply.id
  policy = data.aws_iam_policy_document.tf_apply.json
}

# ----------------------------------------------------------------------------
# Saídas: os ARNs das roles. NÃO são segredo, mas carregam o account id; em vez de
# chumbá-los no deploy.yml (repo público), vamos guardá-los como *repository
# variables* no GitHub (passo 5.3) e referenciar via ${{ vars.* }}.
# ----------------------------------------------------------------------------
output "gha_plan_role_arn" {
  description = "ARN da role assumida pelo GitHub Actions em Pull Requests (terraform plan)."
  value       = aws_iam_role.gha_plan.arn
}

output "gha_apply_role_arn" {
  description = "ARN da role assumida pelo GitHub Actions no merge para main (terraform apply)."
  value       = aws_iam_role.gha_apply.arn
}
