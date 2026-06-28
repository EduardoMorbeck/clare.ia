# --- API Gateway: a porta HTTP pública da Lambda ---
# Usamos o REST API (apigateway v1) em vez do HTTP API (v2) por um motivo de
# ambiente: a licença atual do LocalStack NÃO inclui o apigatewayv2, então o v2
# não pode ser validado localmente. O REST v1 está disponível e cobre o mesmo
# caso de uso. O Mangum entende tanto o payload v1.0 (REST) quanto o v2.0 (HTTP),
# então o handler do backend não muda.

resource "aws_api_gateway_rest_api" "http" {
  name = "${var.project_name}-http"
}

# Recurso "catch-all" {proxy+}: casa com qualquer caminho (/health, /api/chat...)
# e deixa o FastAPI rotear. O recurso raiz "/" é tratado à parte (abaixo), pois
# o {proxy+} não casa com o próprio "/".
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.http.id
  parent_id   = aws_api_gateway_rest_api.http.root_resource_id
  path_part   = "{proxy+}"
}

# Método ANY no {proxy+}: aceita qualquer verbo HTTP.
resource "aws_api_gateway_method" "proxy" {
  rest_api_id   = aws_api_gateway_rest_api.http.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

# Integração AWS_PROXY: repassa a requisição inteira à Lambda (sempre via POST,
# exigência do tipo proxy) e devolve a resposta dela sem transformar.
resource "aws_api_gateway_integration" "proxy" {
  rest_api_id             = aws_api_gateway_rest_api.http.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.api.invoke_arn
}

# Método + integração para o caminho raiz "/" (não coberto pelo {proxy+}).
resource "aws_api_gateway_method" "root" {
  rest_api_id   = aws_api_gateway_rest_api.http.id
  resource_id   = aws_api_gateway_rest_api.http.root_resource_id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "root" {
  rest_api_id             = aws_api_gateway_rest_api.http.id
  resource_id             = aws_api_gateway_rest_api.http.root_resource_id
  http_method             = aws_api_gateway_method.root.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.api.invoke_arn
}

# Deployment + stage. O `triggers` força um novo deployment quando a definição
# das rotas muda; sem isso o stage poderia ficar servindo uma versão antiga.
resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.http.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy.id,
      aws_api_gateway_integration.proxy.id,
      aws_api_gateway_method.root.id,
      aws_api_gateway_integration.root.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "default" {
  rest_api_id   = aws_api_gateway_rest_api.http.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.api_stage_name
}

# Permissão para o API Gateway invocar a Lambda. Sem isso, o gateway recebe a
# requisição mas a Lambda recusa a invocação (AccessDenied).
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowInvokeFromRestApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  # Restringe a permissão a este API específico (qualquer stage/método/rota).
  source_arn = "${aws_api_gateway_rest_api.http.execution_arn}/*/*"
}
