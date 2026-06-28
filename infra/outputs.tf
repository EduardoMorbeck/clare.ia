# --- Saídas (valores úteis após o apply) ---
# Outputs aparecem no fim do `apply` e podem ser consultados com
# `terraform output`. Servem de "ponte" para scripts e para conferência rápida.

output "lambda_function_name" {
  description = "Nome da função Lambda do backend."
  value       = aws_lambda_function.api.function_name
}

output "api_base_url" {
  description = "URL base do backend (API Gateway). Ex.: <base>/health."
  value       = aws_api_gateway_stage.default.invoke_url
}

output "frontend_bucket" {
  description = "Bucket S3 que hospeda o build do frontend."
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_domain" {
  description = "Domínio do CloudFront para acessar o site (null se desligado)."
  # `one()` devolve o único elemento da lista (count=1) ou null (count=0).
  value = one(aws_cloudfront_distribution.frontend[*].domain_name)
}
