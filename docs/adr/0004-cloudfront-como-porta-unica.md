# 0004 — CloudFront como porta única (sem CORS)

- **Status:** Aceito
- **Data:** 2026-06-30

## Contexto

O frontend (site estático) e o backend (API no Lambda) são servidos por origens
diferentes: o S3/CloudFront e o API Gateway. Se o navegador chamasse o API Gateway
**num domínio diferente** do site, cairíamos em **CORS** — seria preciso configurar
`Access-Control-Allow-Origin`, lidar com preflight `OPTIONS`, e manter a lista de
origens em sincronia entre frontend e backend.

## Decisão

Fazer o **CloudFront ser a porta única** de toda a aplicação. A distribuição tem
**duas origens**:

- **S3** (site estático) — comportamento *default*.
- **API Gateway** — comportamento de cache para o padrão `/api/*`, com `origin_path`
  = `/prod` (injeta o stage), `CachingDisabled` e encaminhamento dos headers do cliente
  exceto o `Host`.

O frontend chama `/api/...` **no próprio domínio do CloudFront**. Como a origem é a
mesma do ponto de vista do navegador, **não há CORS**. O CloudFront roteia: `/api/*`
vai ao API Gateway; todo o resto, ao S3.

O bucket S3 é **privado**, acessível só pelo CloudFront via **Origin Access Control
(OAC)** — ninguém acessa o S3 direto.

## Consequências

**Positivas**
- **Zero configuração de CORS.** Frontend e backend compartilham origem.
- **HTTPS** e cache de borda para o site, de graça, com o certificado padrão do
  CloudFront.
- Bucket privado (OAC) é o padrão de segurança recomendado pela AWS.
- Um único domínio público para divulgar.

**Negativas / trade-offs**
- **Acoplamento ao CloudFront:** a regra de SPA do CloudFront reescreve **403/404 →
  `index.html`** (para o React Router funcionar). Isso afeta a **API** se ela devolver
  403/404 — hoje o chat usa 200/422/429, então é seguro; mas é uma restrição a lembrar
  ao criar endpoints novos.
- Invalidação de cache necessária a cada deploy do frontend (o pipeline já faz).
- O `ALLOWED_ORIGINS` do backend ainda aponta para o domínio do CloudFront (defesa em
  profundidade), referenciado direto do recurso no Terraform.

## Alternativas consideradas

- **Domínios separados + CORS:** rejeitado — mais superfície de configuração e de erro,
  sem benefício para este projeto.
- **Lambda Function URL** em vez de API Gateway: não resolveria o CORS sozinho e
  perderíamos o roteamento unificado pelo CDN.
