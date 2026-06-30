# --- SSM Parameter Store: segredos fora do código ---
# As chaves de API dos provedores LLM não podem ir para o repositório nem ficar
# "chumbadas" na Lambda. Aqui elas viram parâmetros SecureString no SSM, sob o
# prefixo /clare-ia/. No passo 3.4 o app passa a lê-los no cold start.
#
# Os valores vêm da variável `provider_api_keys` (definida em terraform.tfvars,
# gitignorado). Sem tfvars, o mapa é vazio e nenhum parâmetro é criado.

resource "aws_ssm_parameter" "provider_keys" {
  # IMPORTANTE (Fase 5 / CD): iteramos sobre uma lista ESTÁTICA de nomes
  # (var.provider_key_names), NÃO sobre as chaves do mapa de segredos. Assim os
  # parâmetros existem na infra mesmo quando o pipeline roda sem os valores em mãos
  # (o CI não tem o tfvars). Se o for_each dependesse do mapa, um apply sem segredos
  # esvaziaria o conjunto e DESTRUIRIA os 4 parâmetros — quebrando o app em produção.
  for_each = toset(var.provider_key_names)

  name = "/${var.project_name}/${each.key}"
  type = "SecureString"

  # O valor real é semeado UMA vez a partir do tfvars local. No CI (sem tfvars), o
  # lookup cai no placeholder — que nunca chega a ser gravado por causa do
  # ignore_changes abaixo. Ou seja: o Terraform gerencia a EXISTÊNCIA do parâmetro,
  # mas o VALOR é tratado fora de banda (semeadura local) e nunca sobrescrito pelo CD.
  value = lookup(var.provider_api_keys, each.key, "PLACEHOLDER_MANAGED_OUT_OF_BAND")

  lifecycle {
    # Tira o valor do controle do Terraform: nenhum plan/apply (local ou no CI) vai
    # propor alterá-lo. É o que permite ao CD rodar sem nunca tocar nos segredos.
    ignore_changes = [value]
  }
}
