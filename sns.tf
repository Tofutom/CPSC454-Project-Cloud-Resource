resource "aws_sns_topic" "alerts" {
  name = "cpsc454-cloud-alerts"
  tags = { Project = "cpsc454" }
}

# Email subscription — AWS will send a confirmation email; you must click it before alerts sends
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
