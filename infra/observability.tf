# --- Observabilidade: log group da Lambda com retenção controlada ---
# Quando uma Lambda escreve o primeiro log, a AWS cria sozinha o log group
# `/aws/lambda/<função>` com retenção "nunca expira". Trazê-lo para o Terraform
# nos deixa (a) fixar uma retenção curta (higiene + custo) e (b) versionar essa
# decisão junto do resto da infra, em vez de depender de um clique no console.
#
# O NOME é o padrão que a Lambda usaria de qualquer forma, então a função
# continua escrevendo aqui sem precisar de nenhuma config extra — só passamos a
# ser nós a definir a retenção.
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-api"
  retention_in_days = var.log_retention_days
}

# ADOÇÃO DE RECURSO EXISTENTE (day-2 ops): o log group acima JÁ existe na AWS real
# (a Lambda o criou na 1ª invocação, lá na Fase 4). Sem isto, o `apply` falharia
# com "ResourceAlreadyExistsException". O bloco `import` faz o Terraform ADOTAR o
# group existente para o state no próximo apply — sem passo manual, direto pelo CD,
# e visível no `plan` do PR para revisão.
#
# APÓS o primeiro apply na main, este bloco pode ser removido em um PR de limpeza
# (uma vez no state, ele é no-op). LOCALSTACK: se for validar com `tflocal` num
# ambiente onde o group não exista, comente este bloco (não há o que importar).
import {
  to = aws_cloudwatch_log_group.lambda
  id = "/aws/lambda/${var.project_name}-api"
}
