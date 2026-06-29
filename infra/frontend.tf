# --- Frontend: S3 (arquivos estáticos) + CloudFront (CDN/HTTPS) ---
# Padrão recomendado pela AWS: o bucket fica PRIVADO e só o CloudFront consegue
# lê-lo, via Origin Access Control (OAC). Ninguém acessa o S3 direto; tudo passa
# pelo CDN (cache + HTTPS + domínio único).

# Descobre o account id da conta autenticada (sem chumbar o número no código —
# importante porque o repo é público). No LocalStack devolve um id de teste.
data "aws_caller_identity" "current" {}

# Bucket que guarda o build do Vite (index.html, assets/...).
# Nome de bucket é GLOBAL na AWS: o sufixo com o account id garante unicidade
# (`clare-ia-frontend` sozinho colidiria com qualquer outra conta que já o tenha).
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"
}

# Bloqueia todo acesso público direto ao bucket (o acesso é só via CloudFront).
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# OAC: identidade que o CloudFront usa para assinar as requisições ao S3.
# Os recursos abaixo usam `count` (0 ou 1) porque o CloudFront não existe no
# LocalStack — ficam desligados localmente e ligam na AWS real (Fase 4).
resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = var.enable_cloudfront ? 1 : 0
  name                              = "${var.project_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Distribuição CloudFront: o "CDN" que serve o site.
resource "aws_cloudfront_distribution" "frontend" {
  count               = var.enable_cloudfront ? 1 : 0
  enabled             = true
  default_root_object = "index.html"

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  # 2º origin: o API Gateway. Assim o CloudFront vira a PORTA ÚNICA — o frontend
  # chama "/api/..." no próprio domínio do CDN e o CloudFront repassa ao backend
  # (mesma origem → sem CORS). `origin_path = /prod` injeta o stage, então o
  # "/api/chat" do navegador vira "/prod/api/chat" no API Gateway.
  origin {
    domain_name = "${aws_api_gateway_rest_api.http.id}.execute-api.${var.aws_region}.amazonaws.com"
    origin_id   = "apigw"
    origin_path = "/${var.api_stage_name}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only" # API Gateway só fala HTTPS
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Roteia "/api/*" para o backend. Vem ANTES do default (que serve o S3).
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "apigw"
    viewer_protocol_policy = "redirect-to-https"
    # API aceita qualquer verbo (o chat é POST); GET/HEAD podem ser cacheados.
    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods  = ["GET", "HEAD"]

    # Policies gerenciadas da AWS (IDs são constantes globais):
    #  - CachingDisabled: nunca cacheia respostas da API.
    #  - AllViewerExceptHostHeader: encaminha headers/query/body do cliente, MENOS
    #    o Host (o API Gateway recusa um Host que não seja o dele).
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  # SPA: erros 403/404 do S3 voltam o index.html (o React Router cuida da rota).
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Política do bucket: permite SÓ a este CloudFront ler os objetos.
# Também condicional — sem CloudFront não há a quem conceder acesso, e o bucket
# permanece privado (o que é o correto localmente).
data "aws_iam_policy_document" "frontend_bucket" {
  count = var.enable_cloudfront ? 1 : 0

  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  count  = var.enable_cloudfront ? 1 : 0
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket[0].json
}
