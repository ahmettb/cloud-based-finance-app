data "archive_file" "dummy_lambda" {
  type        = "zip"
  output_path = "${path.module}/dummy_lambda.zip"
  
  source {
    content  = "exports.handler = async (event) => { return { statusCode: 200, body: 'Deployment successful. Update code later.' }; };"
    filename = "index.js"
  }
}

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-exec-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_xray_access" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}

resource "aws_iam_role_policy" "lambda_ai_services_policy" {
  name = "${var.project_name}-ai-services-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "textract:AnalyzeDocument",
          "textract:DetectDocumentText",
          "textract:StartDocumentAnalysis",
          "textract:GetDocumentAnalysis"
        ]
        Effect   = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*"
      },
      {
        Action = [
          "ssm:GetParameter"
        ]
        Effect   = "Allow"
        Resource = [
          "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/prod/db-password",
          "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/prod/langfuse-secret-key",
          "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/prod/langfuse-public-key"
        ]
      },
      {
        Action   = ["cloudwatch:PutMetricData"]
        Effect   = "Allow"
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "ParamNerede/Bedrock"
          }
        }
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

resource "aws_ssm_parameter" "db_password" {
  name        = "/${var.project_name}/prod/db-password"
  description = "Database password for ${var.project_name}"
  type        = "SecureString"
  value       = var.db_password
}

resource "aws_ssm_parameter" "langfuse_secret_key" {
  name        = "/${var.project_name}/prod/langfuse-secret-key"
  description = "Langfuse Secret Key"
  type        = "SecureString"
  value       = var.langfuse_secret_key
}

resource "aws_ssm_parameter" "langfuse_public_key" {
  name        = "/${var.project_name}/prod/langfuse-public-key"
  description = "Langfuse Public Key"
  type        = "String"
  value       = var.langfuse_public_key
}

resource "aws_lambda_function" "backend_lambda" {
  function_name    = "backend_lambda"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.dummy_lambda.output_path
  source_code_hash = data.archive_file.dummy_lambda.output_base64sha256

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      DB_HOST  = aws_db_instance.postgres.address
      DB_NAME  = aws_db_instance.postgres.db_name
      DB_USER  = aws_db_instance.postgres.username
      DB_PORT  = aws_db_instance.postgres.port
      DB_PASSWORD = "ssm:/${var.project_name}/prod/db-password"
      NODE_ENV = "production"
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID = aws_cognito_user_pool_client.client.id
      S3_BUCKET_NAME = aws_s3_bucket.receipts_bucket.bucket
      OCR_MAX_TOKENS = "320"
      REFRESH_TOKEN_DAYS = "30"
      AI_CACHE_TTL_SECONDS = "21600"
      OCR_MAX_FILE_BYTES = "3145728"
      ALLOWED_ORIGIN = "*"
      TOKEN_USE_ALLOWED = "access"
      TITAN_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
      LANGFUSE_SECRET_KEY = "ssm:/${var.project_name}/prod/langfuse-secret-key"
      LANGFUSE_PUBLIC_KEY = "ssm:/${var.project_name}/prod/langfuse-public-key"
      LANGFUSE_HOST       = var.langfuse_host
    }
  }

  timeout     = 30
  memory_size = 256

  tracing_config {
    mode = "Active"
  }
}

resource "aws_lambda_function" "lambda_ai" {
  function_name    = "lambda_ai"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.dummy_lambda.output_path
  source_code_hash = data.archive_file.dummy_lambda.output_base64sha256

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      NODE_ENV = "production"
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID = aws_cognito_user_pool_client.client.id
      S3_BUCKET_NAME = aws_s3_bucket.receipts_bucket.bucket
      DB_HOST  = aws_db_instance.postgres.address
      DB_NAME  = aws_db_instance.postgres.db_name
      DB_USER  = aws_db_instance.postgres.username
      DB_PORT  = aws_db_instance.postgres.port
      DB_PASSWORD = "ssm:/${var.project_name}/prod/db-password"
      OCR_MAX_TOKENS = "320"
      REFRESH_TOKEN_DAYS = "30"
      AI_CACHE_TTL_SECONDS = "21600"
      OCR_MAX_FILE_BYTES = "3145728"
      ALLOWED_ORIGIN = "*"
      TOKEN_USE_ALLOWED = "access"
      TITAN_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
    }
  }

  timeout     = 120
  memory_size = 512

  tracing_config {
    mode = "Active"
  }
}

resource "aws_lambda_permission" "apigw_invoke_backend" {
  statement_id  = "AllowAPIGatewayInvokeBackend"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_invoke_ai" {
  statement_id  = "AllowAPIGatewayInvokeAI"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lambda_ai.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_s3_bucket" "receipts_bucket" {
  bucket = "${var.project_name}-receipts-storage-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-receipts-storage"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "receipts" {
  bucket = aws_s3_bucket.receipts_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_iam_role_policy" "lambda_s3_policy" {
  name = "${var.project_name}-s3-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = [
          aws_s3_bucket.receipts_bucket.arn,
          "${aws_s3_bucket.receipts_bucket.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_sqs_queue" "lambda_dlq" {
  name                       = "${var.project_name}-lambda-dlq"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 60

  tags = {
    Name = "${var.project_name}-lambda-dlq"
  }
}

resource "aws_lambda_function_event_invoke_config" "backend_dlq" {
  function_name = aws_lambda_function.backend_lambda.function_name

  destination_config {
    on_failure {
      destination = aws_sqs_queue.lambda_dlq.arn
    }
  }
}

resource "aws_iam_role_policy" "lambda_sqs_policy" {
  name = "${var.project_name}-sqs-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["sqs:SendMessage"]
      Effect   = "Allow"
      Resource = aws_sqs_queue.lambda_dlq.arn
    }]
  })
}

resource "aws_lambda_alias" "backend_prod" {
  name             = "prod"
  function_name    = aws_lambda_function.backend_lambda.function_name
  function_version = "$LATEST"
}

resource "aws_lambda_alias" "ai_prod" {
  name             = "prod"
  function_name    = aws_lambda_function.lambda_ai.function_name
  function_version = "$LATEST"
}

resource "aws_lambda_function_event_invoke_config" "ai_concurrency" {
  function_name          = aws_lambda_function.lambda_ai.function_name
  maximum_retry_attempts = 0
}
