# Architecture Decision Records (ADRs)

Um **ADR** registra uma decisão de arquitetura significativa: o **contexto** em que
foi tomada, a **decisão** em si e as **consequências** (incluindo o que se abre mão).
A ideia é que, meses depois, qualquer pessoa entenda *por que* o sistema é assim —
sem precisar reconstruir o raciocínio a partir do código.

Estes ADRs são imutáveis: em vez de editar um antigo, cria-se um novo que o
**supersede**. Cada arquivo é numerado em ordem cronológica.

| # | Decisão | Status |
|---|---------|--------|
| [0001](0001-arquitetura-serverless-escala-a-zero.md) | Arquitetura serverless que escala a zero | Aceito |
| [0002](0002-oidc-em-vez-de-chave-estatica.md) | OIDC no CI/CD em vez de chave de acesso estática | Aceito |
| [0003](0003-terraform-com-localstack.md) | Terraform validado no LocalStack antes da AWS real | Aceito |
| [0004](0004-cloudfront-como-porta-unica.md) | CloudFront como porta única (sem CORS) | Aceito |
| [0005](0005-segredos-no-ssm-geridos-fora-de-banda.md) | Segredos no SSM, com o valor gerido fora de banda | Aceito |
| [0006](0006-build-reprodutivel-da-lambda.md) | Build reprodutível do pacote da Lambda | Aceito |
