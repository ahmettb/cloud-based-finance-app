output "bastion_public_ip" {
  description = "Public IP of Bastion Instance"
  value       = aws_instance.bastion.public_ip
}

output "nat_public_ip" {
  description = "Public IP of NAT Instance"
  value       = aws_instance.nat.public_ip
}

output "rds_endpoint" {
  description = "Connection endpoint for PostgreSQL"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_address" {
  description = "Hostname for RDS Connection (for tunnel)"
  value       = aws_db_instance.postgres.address
}

output "api_gateway_url" {
  description = "Base URL of the API Gateway"
  value       = aws_apigatewayv2_stage.api_stage.invoke_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID for Authentication"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_app_client_id" {
  description = "Cognito App Client ID for Frontend"
  value       = aws_cognito_user_pool_client.client.id
}
