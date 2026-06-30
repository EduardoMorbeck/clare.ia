# 0003 — Terraform validado no LocalStack antes da AWS real

- **Status:** Aceito
- **Data:** 2026-06-30

## Contexto

A infraestrutura precisa ser versionada (IaC) e reproduzível. Mas há a restrição de
custo (~R$ 0) e o autor está aprendendo os serviços: errar **na AWS real** pode gerar
recursos esquecidos "ligados" e, portanto, fatura.

## Decisão

Usar **Terraform** como IaC, descrevendo toda a infra em `infra/` (organização *flat*,
um arquivo por assunto: `lambda.tf`, `apigw.tf`, `frontend.tf`, `ssm.tf`, `iam.tf`,
`oidc.tf`, ...). Antes de tocar na AWS real, **validar o ciclo `apply`/`destroy` no
LocalStack** (emulador da AWS rodando em Docker).

O **state** fica num bucket **S3 remoto** com **trava nativa do S3** (Terraform 1.11+,
dispensa DynamoDB). O bloco `backend "s3"` é parcial; os valores concretos
(bucket/key/region) entram via `-backend-config` no `init`, então a mesma config serve
para LocalStack e AWS real.

## Consequências

**Positivas**
- Erra-se no emulador, **não na fatura**. O ciclo `destroy`/`apply` do zero foi
  validado localmente (recria toda a infra), o que dá confiança no IaC.
- Infra inteira versionada, revisável em PR e idempotente.
- State remoto + lock permitem que o CI (e não só a máquina local) aplique com segurança.

**Negativas / trade-offs**
- O LocalStack **não emula tudo**. Com a licença freemium atual:
  - **HTTP API (apigatewayv2) não está incluído** → usa-se **REST API v1**
    (ver [ADR-0001](0001-arquitetura-serverless-escala-a-zero.md)).
  - **CloudFront não está incluído** → os recursos de CDN ficam atrás de uma variável
    (`enable_cloudfront`, `count`-gated): desligados localmente, ligados na AWS real.
- Há diferenças sutis entre emulador e nuvem que só aparecem no primeiro deploy real
  (ex.: endpoints, comportamento do boto3 dentro da Lambda).

## Alternativas consideradas

- **Aplicar direto na AWS real desde o início:** rejeitado — risco de custo e de
  recursos órfãos durante o aprendizado.
- **CloudFormation/CDK:** Terraform foi escolhido por ser agnóstico de nuvem e o padrão
  de mercado mais demandado em vagas — alinhado ao objetivo de portfólio.
- **DynamoDB para o lock do state:** dispensado — a trava nativa do S3 cobre o caso de
  um único operador/pipeline e evita um recurso a mais.
