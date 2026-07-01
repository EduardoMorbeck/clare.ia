# 0002 — OIDC no CI/CD em vez de chave de acesso estática

- **Status:** Aceito
- **Data:** 2026-06-30

## Contexto

O deploy é automatizado pelo GitHub Actions (ver
[ADR-0001](0001-arquitetura-serverless-escala-a-zero.md)): um PR roda `terraform
plan`, o merge na `main` roda `terraform apply` + publica o frontend. Para isso o
pipeline precisa de credenciais da AWS.

O caminho tradicional é gerar uma **access key** (par `AKIA...`/secret) de um usuário
IAM e guardá-la como secret do repositório. Problemas:

- É um **segredo de longa duração**. Se vazar (log, fork, screenshot), dá acesso à
  conta até alguém perceber e revogar.
- O repositório é **público** — a superfície de exposição é maior.
- Exige **rotação manual**, que raramente acontece.

## Decisão

Autenticar o GitHub Actions na AWS via **OIDC (OpenID Connect)**, sem nenhuma chave
estática no repositório.

- Um **OIDC provider** na conta cadastra `token.actions.githubusercontent.com` como
  fonte de identidade confiável.
- Duas **roles** com `AssumeRoleWithWebIdentity`, cada uma com a *trust policy*
  travada no repo + evento (a claim `sub` do token):
  - `gha-plan` — assumível **só em Pull Request**; permissão **ReadOnlyAccess** (+
    escrita apenas no lock do state). É o que roda em PRs de terceiros.
  - `gha-apply` — assumível **só por jobs ligados ao Environment `production`**;
    escrita **escopada por ARN** aos recursos do projeto.
- A cada execução o GitHub emite um token OIDC de ~1h; a AWS o troca por
  **credenciais temporárias**. Nada persiste.

A access key estática que existia para o bootstrap foi **deletada** após o pipeline
provar que assume as roles.

## Consequências

**Positivas**
- **Zero segredo de longa duração** no repo. Não há o que vazar nem rotacionar.
- **Menor privilégio por evento:** PR só lê; apply só escreve, e só depois do gate de
  aprovação do Environment `production`.
- Credenciais de vida curta reduzem a janela de abuso.

**Negativas / trade-offs**
- Configuração inicial mais complexa (provider + trust policies + as claims certas).
- **Pegadinha documentada:** ao usar `environment: production` num job, o GitHub troca
  a claim `sub` de `...:ref:refs/heads/main` para `...:environment:production`. A trust
  policy da role de apply precisa apontar para esse `sub` — caso contrário, deadlock.
- Há um **break-glass**: se o OIDC quebrar, o usuário IAM admin entra no console com
  senha + MFA.

## Alternativas consideradas

- **Access key estática em secret:** rejeitada pelos motivos do contexto.
- **Uma única role para plan e apply:** rejeitada — separar por evento permite dar
  read-only ao job disparável por PR e isolar a escrita atrás do gate de aprovação.
