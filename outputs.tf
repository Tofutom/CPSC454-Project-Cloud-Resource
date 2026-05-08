output "instance_id" {
  description = "EC2 instance ID of the monitored machine"
  value       = aws_instance.monitored.id
}

output "instance_public_ip" {
  description = "Public IPv4 address of the monitored EC2 instance"
  value       = aws_instance.monitored.public_ip
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "sns_topic_arn" {
  description = "SNS topic ARN — CloudWatch alarms publish here"
  value       = aws_sns_topic.alerts.arn
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ~/.ssh/id_rsa ec2-user@${aws_instance.monitored.public_ip}"
}

# Dashboard IAM credentials — written to Terraform state (sensitive)
# Retrieve with: terraform output -raw dashboard_access_key_id
output "dashboard_access_key_id" {
  description = "Access key ID for the dashboard IAM user"
  value       = aws_iam_access_key.dashboard.id
  sensitive   = true
}

output "dashboard_secret_access_key" {
  description = "Secret access key for the dashboard IAM user — store securely"
  value       = aws_iam_access_key.dashboard.secret
  sensitive   = true
}
