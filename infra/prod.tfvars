# Config do ambiente de PRODUÇÃO (AWS real) — Fase 5 / CD.
#
# VERSIONADO de propósito (exceção no .gitignore): NÃO contém segredo nenhum.
# É o -var-file que o GitHub Actions usa no plan/apply. As chaves dos provedores
# LLM NÃO entram aqui: elas vivem como SecureString no SSM, foram semeadas uma vez
# localmente e o Terraform IGNORA o valor delas (ver lifecycle ignore_changes em
# ssm.tf). Por isso o CD roda sem nunca ver os segredos.
#
# Diferenças vs. LocalStack (localstack.tfvars):
#  - CloudFront LIGADO (a licença do LocalStack não o inclui; na AWS real, sim).
#  - lambda_aws_endpoint_url VAZIO (boto3 usa os endpoints padrão da AWS).

enable_cloudfront       = true
lambda_aws_endpoint_url = ""
