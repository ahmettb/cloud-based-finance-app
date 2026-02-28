variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for tagging"
  default     = "paramnerede"
}

variable "db_password" {
  description = "Database admin password"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "Database admin username"
  default     = "postgresadmin"
}

variable "key_name" {
  description = "SSH key pair name"
  type        = string
  default     = "paramnerede-key"
}

variable "user_ip" {
  description = "Allowed IP address for SSH and DB access"
  type        = string
  default     = "85.118.178.13/32"
}

variable "langfuse_secret_key" {
  description = "Langfuse Secret Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "langfuse_public_key" {
  description = "Langfuse Public Key"
  type        = string
  default     = ""
}

variable "langfuse_host" {
  description = "Langfuse Host URL"
  type        = string
  default     = "https://cloud.langfuse.com"
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}
