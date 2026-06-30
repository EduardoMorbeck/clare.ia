# 0005 — Segredos no SSM, com o valor gerido fora de banda

- **Status:** Aceito
- **Data:** 2026-06-30

## Contexto

A aplicação precisa das **chaves de API dos provedores LLM** (Gemini, Cerebras, Groq,
Mistral). Elas não podem ir para o repositório (público) nem ficar "chumbadas" na
definição da Lambda. Além disso, o **CD roda sem ter os segredos em mãos** — o pipeline
não tem o `tfvars` local com as chaves. Surge uma tensão: o Terraform precisa
*gerenciar* os parâmetros de segredo, mas **não pode apagá-los nem sobrescrevê-los**
quando aplica sem os valores.

## Decisão

Guardar as chaves no **SSM Parameter Store** como **SecureString**, sob o prefixo
`/clare-ia/`. A aplicação as lê **no cold start** (`ssm_config.hydrate_env_from_ssm()`),
injetando-as em `os.environ` antes de montar o router de provedores; sem o prefixo
configurado, cai no fallback de `.env` (dev local).

Dois cuidados tornam isso compatível com o CD sem segredos:

1. **`for_each` sobre uma lista ESTÁTICA de nomes** (`provider_key_names`), não sobre o
   mapa de valores. Assim os parâmetros existem na infra mesmo quando o mapa de
   segredos está vazio — caso contrário, um apply sem segredos esvaziaria o `for_each`
   e **destruiria** os parâmetros em produção.
2. **`lifecycle { ignore_changes = [value] }`** em cada parâmetro. O Terraform gerencia
   a **existência** do parâmetro; o **valor** é semeado uma única vez a partir do tfvars
   local e nunca mais é tocado por plan/apply (local ou CI).

## Consequências

**Positivas**
- Segredos **fora do código** e fora da env var "chumbada"; rotacionáveis no console
  sem deploy.
- O **CD roda sem nunca ver os segredos** — separação limpa entre "gerenciar infra" e
  "gerenciar valores sensíveis".
- Parameter Store é **grátis** (tier standard), alinhado à restrição de custo.

**Negativas / trade-offs**
- O **valor inicial é gerido fora de banda** (semeadura manual). Não é totalmente
  "IaC puro": o Terraform não conhece o conteúdo do segredo — de propósito.
- Ler o SSM no cold start exige `fail-fast` no cliente boto3 (timeouts curtos), senão um
  SSM indisponível penduraria a inicialização da Lambda.

## Alternativas consideradas

- **Secrets Manager:** mais recursos (rotação automática), mas **tem custo por segredo**
  — desnecessário aqui; o Parameter Store cobre o caso de graça.
- **Variáveis de ambiente da Lambda com as chaves:** rejeitado — apareceriam no state e
  na config da função; o SSM mantém o segredo fora desses lugares.
- **Deixar o Terraform gerenciar o valor:** rejeitado — quebraria o CD sem segredos
  (ver Decisão).
