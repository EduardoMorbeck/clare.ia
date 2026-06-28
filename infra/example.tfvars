# Modelo de variáveis sensíveis. COPIE para `terraform.tfvars` e preencha com
# valores reais. O terraform.tfvars é gitignorado — nunca comite chaves reais.
#
#   cp example.tfvars terraform.tfvars   # (no Windows: Copy-Item)
#
# Só inclua as chaves dos provedores que você realmente usa; o `for_each` cria
# um parâmetro SSM SecureString por entrada, em /clare-ia/<NOME>.

provider_api_keys = {
  GEMINI_API_KEY   = "coloque-sua-chave-gemini-aqui"
  GROQ_API_KEY     = "coloque-sua-chave-groq-aqui"
  MISTRAL_API_KEY  = "coloque-sua-chave-mistral-aqui"
  CEREBRAS_API_KEY = "coloque-sua-chave-cerebras-aqui"
}
