variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-west-1"
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms and budget notifications"
  type        = string
}

variable "trusted_ssh_cidr" {
  description = "Your public IP in CIDR notation (e.g. 1.2.3.4/32) — restricts SSH to this address only"
  type        = string

  validation {
    condition     = can(cidrhost(var.trusted_ssh_cidr, 0))
    error_message = "Must be a valid CIDR block such as 1.2.3.4/32."
  }
}

variable "ssh_public_key_path" {
  description = "Path to your SSH public key file to load onto the EC2 instance"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "cpu_alarm_threshold" {
  description = "CPU utilization percentage (0-100) that triggers the high-CPU alarm"
  type        = number
  default     = 80
}

variable "budget_limit_usd" {
  description = "Monthly spend limit in USD — an alert fires at 80% and 100%"
  type        = string
  default     = "5"
}
