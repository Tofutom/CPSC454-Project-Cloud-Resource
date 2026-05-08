#CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "cpsc454-high-cpu"
  alarm_description   = "ACTION REQUIRED: CPU is above ${var.cpu_alarm_threshold}% | SSH into the instance and run 'top' to find the process causing high load. If the issue persists, consider stopping the process or rebooting. | Project: CPSC454 Cloud Monitor"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = aws_instance.monitored.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = { Project = "cpsc454" }
}

resource "aws_cloudwatch_metric_alarm" "high_disk" {
  alarm_name          = "cpsc454-high-disk"
  alarm_description   = "ACTION REQUIRED: Root disk (/) is above 80% full | SSH in and run 'df -h' to see usage and 'du -sh /* 2>/dev/null | sort -rh | head' to find large files. Delete old logs or snapshots to free space. | Project: CPSC454 Cloud Monitor"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "disk_used_percent"
  namespace           = "CPSC454/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  # Dimensions must match what the CloudWatch agent sends.
  # InstanceId is injected via append_dimensions in the agent config.
  # path="/", fstype="xfs" are defaults for Amazon Linux 2023 root volume.
  dimensions = {
    InstanceId = aws_instance.monitored.id
    path       = "/"
    fstype     = "xfs"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = { Project = "cpsc454" }
}

resource "aws_cloudwatch_metric_alarm" "high_network_in" {
  alarm_name          = "cpsc454-high-network-in"
  alarm_description   = "SECURITY ALERT: Inbound traffic exceeded 5 MB in 1 minute -- this may indicate a port scan, DDoS attempt, or unexpected data transfer. Check your security group rules and review CloudTrail logs immediately. | Project: CPSC454 Cloud Monitor"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "NetworkIn"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 5000000  # 5 MB per 5-min sample
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = aws_instance.monitored.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = { Project = "cpsc454" }
}
