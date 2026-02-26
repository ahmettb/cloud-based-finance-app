# Dummy code for initial plan/apply without throwing errors.
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

# Attach policy to allow Lambda to connect to VPC/internet and write cloudwatch logs
resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Attach policy to allow Lambda to send OpenTelemetry/X-Ray Traces
resource "aws_iam_role_policy_attachment" "lambda_xray_access" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}

# Attach inline policy for AWS Textract and AWS Bedrock (Claude 3)
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
      }
    ]
  })
}

# Fetch AWS Account ID dynamically for IAM policies
data "aws_caller_identity" "current" {}

# Store Database Password Securely in AWS SSM Parameter Store
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

# Backend Lambda (Private Subnet)
resource "aws_lambda_function" "backend_lambda" {
  function_name    = "backend_lambda"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.dummy_lambda.output_path
  source_code_hash = data.archive_file.dummy_lambda.output_base64sha256

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
}

# AI Lambda (Private Subnet)
resource "aws_lambda_function" "lambda_ai" {
  function_name    = "lambda_ai"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.dummy_lambda.output_path
  source_code_hash = data.archive_file.dummy_lambda.output_base64sha256

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
}

# API Gateway Permissions to Invoke Lambdas
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

# S3 Bucket for Uploading Receipts
resource "aws_s3_bucket" "receipts_bucket" {
  bucket = "${var.project_name}-receipts-storage-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-receipts-storage"
  }
}

# Attach policy to allow Lambda to read/write to S3 Bucket
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
