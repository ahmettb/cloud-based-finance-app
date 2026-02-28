resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
  
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "api_stage" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_logs.arn

    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      path           = "$context.path"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      latency        = "$context.integrationLatency"
      errorMessage   = "$context.error.message"
      requestTime    = "$context.requestTime"
    })
  }
}

resource "aws_apigatewayv2_integration" "backend_integration" {
  api_id             = aws_apigatewayv2_api.api.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.backend_lambda.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "ai_integration" {
  api_id             = aws_apigatewayv2_api.api.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.lambda_ai.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "backend_route" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /backend/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.backend_integration.id}"
}

resource "aws_apigatewayv2_route" "ai_route" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /ai/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.ai_integration.id}"
}
