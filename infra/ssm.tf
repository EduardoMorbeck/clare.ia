# --- SSM Parameter Store: segredos fora do código ---
# As chaves de API dos provedores LLM não podem ir para o repositório nem ficar
# "chumbadas" na Lambda. Aqui elas viram parâmetros SecureString no SSM, sob o
# prefixo /clare-ia/. No passo 3.4 o app passa a lê-los no cold start.
#
# Os valores vêm da variável `provider_api_keys` (definida em terraform.tfvars,
# gitignorado). Sem tfvars, o mapa é vazio e nenhum parâmetro é criado.

resource "aws_ssm_parameter" "provider_keys" {
  # Iteramos pelos NOMES das chaves (não são segredos) — os VALORES é que são
  # sensíveis. `nonsensitive` é seguro aqui porque só expõe os nomes, e o
  # `for_each` não aceita um conjunto derivado de valor sensível.
  for_each = toset(nonsensitive(keys(var.provider_api_keys)))

  name  = "/${var.project_name}/${each.key}"
  type  = "SecureString"
  value = var.provider_api_keys[each.key]
}
