resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"

  tags = {
    Name = "${var.project_name}-alerts"
  }
}

resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "backend_lambda_errors" {
  alarm_name          = "${var.project_name}-backend-lambda-errors"
  alarm_description   = "Backend Lambda high error rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.backend_lambda.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-backend-errors-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "backend_lambda_throttles" {
  alarm_name          = "${var.project_name}-backend-lambda-throttles"
  alarm_description   = "Backend Lambda throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 3
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.backend_lambda.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-backend-throttle-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "backend_lambda_duration" {
  alarm_name          = "${var.project_name}-backend-lambda-high-duration"
  alarm_description   = "Backend Lambda high duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 10000
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.backend_lambda.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-backend-duration-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "ai_lambda_errors" {
  alarm_name          = "${var.project_name}-ai-lambda-errors"
  alarm_description   = "AI Lambda high error rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 3
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.lambda_ai.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-ai-errors-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project_name}-rds-high-cpu"
  alarm_description   = "RDS CPU above 80%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-rds-cpu-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${var.project_name}-rds-high-connections"
  alarm_description   = "RDS connections above 40"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 40
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-rds-connections-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "${var.project_name}-rds-low-storage"
  alarm_description   = "RDS free storage below 3GB"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 3000000000
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-rds-storage-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "apigw_5xx" {
  alarm_name          = "${var.project_name}-api-5xx-errors"
  alarm_description   = "API Gateway 5xx errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5xx"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-api-5xx-alarm"
  }
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-observability"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "# 🚀 ParamNerede - Infrastructure Observability Dashboard"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 8
        height = 6
        properties = {
          title   = "Lambda Invocations"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.backend_lambda.function_name, { label = "Backend", color = "#2ca02c" }],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.lambda_ai.function_name, { label = "AI Lambda", color = "#9467bd" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 1
        width  = 8
        height = 6
        properties = {
          title   = "Lambda Errors"
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.backend_lambda.function_name, { label = "Backend Errors", color = "#d62728" }],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.lambda_ai.function_name, { label = "AI Errors", color = "#ff7f0e" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 1
        width  = 8
        height = 6
        properties = {
          title   = "Lambda Duration (ms)"
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.backend_lambda.function_name, { label = "Backend Avg", stat = "Average", color = "#1f77b4" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.backend_lambda.function_name, { label = "Backend P99", stat = "p99", color = "#aec7e8" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.lambda_ai.function_name, { label = "AI Avg", stat = "Average", color = "#9467bd" }]
          ]
          period = 300
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 7
        width  = 8
        height = 6
        properties = {
          title   = "API Gateway Requests & Errors"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.api.id, { label = "Total Requests", color = "#2ca02c" }],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.api.id, { label = "5xx Errors", color = "#d62728" }],
            ["AWS/ApiGateway", "4xx", "ApiId", aws_apigatewayv2_api.api.id, { label = "4xx Errors", color = "#ff7f0e" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 7
        width  = 8
        height = 6
        properties = {
          title   = "RDS CPU & Connections"
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.postgres.identifier, { label = "CPU %", color = "#d62728" }],
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.postgres.identifier, { label = "Connections", color = "#1f77b4", yAxis = "right" }]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 7
        width  = 8
        height = 6
        properties = {
          title   = "RDS Disk I/O & Storage"
          metrics = [
            ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", aws_db_instance.postgres.identifier, { label = "Free Storage (bytes)", color = "#2ca02c" }],
            ["AWS/RDS", "ReadIOPS", "DBInstanceIdentifier", aws_db_instance.postgres.identifier, { label = "Read IOPS", color = "#1f77b4", yAxis = "right" }],
            ["AWS/RDS", "WriteIOPS", "DBInstanceIdentifier", aws_db_instance.postgres.identifier, { label = "Write IOPS", color = "#ff7f0e", yAxis = "right" }]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 13
        width  = 12
        height = 6
        properties = {
          title   = "API Gateway Latency (ms)"
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", aws_apigatewayv2_api.api.id, { label = "Avg Latency", stat = "Average", color = "#1f77b4" }],
            ["AWS/ApiGateway", "Latency", "ApiId", aws_apigatewayv2_api.api.id, { label = "P99 Latency", stat = "p99", color = "#d62728" }]
          ]
          period = 300
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 13
        width  = 12
        height = 6
        properties = {
          title   = "Lambda Throttles & Concurrent Executions"
          metrics = [
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.backend_lambda.function_name, { label = "Backend Throttles", color = "#d62728" }],
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.backend_lambda.function_name, { label = "Backend Concurrent", color = "#2ca02c" }],
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.lambda_ai.function_name, { label = "AI Concurrent", color = "#9467bd" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "text"
        x      = 0
        y      = 19
        width  = 24
        height = 1
        properties = {
          markdown = "## 🤖 AI / Bedrock Token Usage & Estimated Cost"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 20
        width  = 8
        height = 6
        properties = {
          title   = "Bedrock Token Usage (Input vs Output)"
          metrics = [
            ["ParamNerede/Bedrock", "InputTokens", "Endpoint", "chat", { label = "Chat Input", color = "#1f77b4" }],
            ["ParamNerede/Bedrock", "OutputTokens", "Endpoint", "chat", { label = "Chat Output", color = "#aec7e8" }],
            ["ParamNerede/Bedrock", "InputTokens", "Endpoint", "ocr", { label = "OCR Input", color = "#ff7f0e" }],
            ["ParamNerede/Bedrock", "OutputTokens", "Endpoint", "ocr", { label = "OCR Output", color = "#ffbb78" }]
          ]
          period = 3600
          stat   = "Sum"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 20
        width  = 8
        height = 6
        properties = {
          title   = "Estimated Bedrock Cost ($)"
          metrics = [
            ["ParamNerede/Bedrock", "EstimatedCost", "Endpoint", "chat", { label = "Chat $", color = "#2ca02c" }],
            ["ParamNerede/Bedrock", "EstimatedCost", "Endpoint", "ocr", { label = "OCR $", color = "#d62728" }],
            ["ParamNerede/Bedrock", "EstimatedCost", "Endpoint", "smart_extract", { label = "Extract $", color = "#9467bd" }],
            ["ParamNerede/Bedrock", "EstimatedCost", "Endpoint", "embedding", { label = "Embedding $", color = "#17becf" }]
          ]
          period = 3600
          stat   = "Sum"
          region = var.aws_region
          view   = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 20
        width  = 8
        height = 6
        properties = {
          title   = "Total Tokens by Endpoint"
          metrics = [
            ["ParamNerede/Bedrock", "InputTokens", "Endpoint", "chat", { label = "Chat" }],
            ["ParamNerede/Bedrock", "InputTokens", "Endpoint", "ocr", { label = "OCR" }],
            ["ParamNerede/Bedrock", "InputTokens", "Endpoint", "smart_extract", { label = "Extract" }],
            ["ParamNerede/Bedrock", "InputTokens", "Endpoint", "embedding", { label = "Embedding" }]
          ]
          period = 86400
          stat   = "Sum"
          region = var.aws_region
          view   = "bar"
        }
      }
    ]
  })
}

resource "aws_cloudwatch_metric_alarm" "bedrock_daily_cost" {
  alarm_name          = "${var.project_name}-bedrock-high-cost"
  alarm_description   = "Daily Bedrock cost exceeds $1"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 1.0
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "total_cost"
    expression  = "SUM(METRICS())"
    label       = "Total Daily Cost"
    return_data = true
  }

  metric_query {
    id = "chat_cost"
    metric {
      metric_name = "EstimatedCost"
      namespace   = "ParamNerede/Bedrock"
      period      = 86400
      stat        = "Sum"
      dimensions = {
        Endpoint = "chat"
      }
    }
  }

  metric_query {
    id = "ocr_cost"
    metric {
      metric_name = "EstimatedCost"
      namespace   = "ParamNerede/Bedrock"
      period      = 86400
      stat        = "Sum"
      dimensions = {
        Endpoint = "ocr"
      }
    }
  }

  metric_query {
    id = "extract_cost"
    metric {
      metric_name = "EstimatedCost"
      namespace   = "ParamNerede/Bedrock"
      period      = 86400
      stat        = "Sum"
      dimensions = {
        Endpoint = "smart_extract"
      }
    }
  }

  metric_query {
    id = "embed_cost"
    metric {
      metric_name = "EstimatedCost"
      namespace   = "ParamNerede/Bedrock"
      period      = 86400
      stat        = "Sum"
      dimensions = {
        Endpoint = "embedding"
      }
    }
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Name = "${var.project_name}-bedrock-cost-alarm"
  }
}

resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  name              = "/aws/apigateway/${var.project_name}-api"
  retention_in_days = 30

  tags = {
    Name        = "${var.project_name}-api-logs"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_log_group" "backend_lambda_logs" {
  name              = "/aws/lambda/backend_lambda"
  retention_in_days = 30

  tags = {
    Name        = "${var.project_name}-backend-logs"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_log_group" "ai_lambda_logs" {
  name              = "/aws/lambda/lambda_ai"
  retention_in_days = 30

  tags = {
    Name        = "${var.project_name}-ai-logs"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
