# 0001 — Arquitetura serverless que escala a zero

- **Status:** Aceito
- **Data:** 2026-06-30

## Contexto

O clare.ia é um projeto pessoal de portfólio. Duas restrições moldam tudo:

1. **Custo ~R$ 0.** Não há orçamento recorrente. O projeto pode ficar meses sem
   nenhum acesso e não pode gerar fatura por estar "ligado".
2. **Tráfego imprevisível e baixo.** É uma vitrine — picos esporádicos (quando
   alguém abre o link numa entrevista), zero no resto do tempo.

A aplicação é um backend FastAPI (Python) + um frontend React estático.

## Decisão

Adotar uma arquitetura **100% serverless e que escala a zero**:

- **Frontend:** build estático do Vite no **S3**, servido pelo **CloudFront**.
- **Backend:** FastAPI rodando no **AWS Lambda** (via **Mangum**, adaptador
  ASGI→Lambda), exposto pelo **API Gateway**.
- **Segredos:** **SSM Parameter Store** (ver [ADR-0005](0005-segredos-no-ssm-geridos-fora-de-banda.md)).
- **Observabilidade/guarda-corpos:** CloudWatch Logs + AWS Budget.

"Escala a zero" significa: quando ninguém usa, **nada está rodando** e o custo é
zero. Só há cobrança por invocação/transferência — que, no volume de portfólio,
fica dentro do free tier.

## Consequências

**Positivas**
- Custo praticamente nulo. Lambda tem **1M de requisições/mês grátis de forma
  permanente**; S3/CloudFront ficam em centavos; um AWS Budget alerta no 1º centavo.
- Sem servidores para manter, patchear ou escalar manualmente.
- Demonstra domínio do padrão serverless, o foco de portfólio do projeto.

**Negativas / trade-offs**
- **Cold start:** a primeira invocação após ociosidade tem latência extra. Aceitável
  para esta aplicação (não é de baixa latência crítica).
- O **API Gateway REST** tem free tier de **apenas 12 meses** (não permanente como a
  Lambda). No volume atual o custo segue ~R$ 0, mas é um ponto de atenção futuro.
- O handler precisa do Mangum traduzindo evento do API Gateway ↔ ASGI; e o estado
  some entre invocações (sem persistência — o que aqui é uma escolha de produto).

## Alternativas consideradas

- **ECS/Fargate + ALB** ou **EC2 24/7**: descartados — um ALB/instância "sempre
  ligado" custa dezenas de reais/mês mesmo sem tráfego, violando a restrição de custo.
- **App Runner:** escala a zero de forma limitada, mas mais caro e menos "free tier"
  que Lambda para este perfil.
- **REST API (v1) vs. HTTP API (v2) no API Gateway:** optou-se pelo **REST v1** porque
  o HTTP API não é validável no LocalStack com a licença atual (ver
  [ADR-0003](0003-terraform-com-localstack.md)). O Mangum entende ambos os payloads,
  então o backend não muda.
