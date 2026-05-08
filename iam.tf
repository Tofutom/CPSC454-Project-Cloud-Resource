#EC2 Instance Role (for CloudWatch Agent)

resource "aws_iam_role" "ec2" {
  name = "cpsc454-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Project = "cpsc454" }
}

# Allows the CloudWatch agent on EC2 to publish custom metrics
resource "aws_iam_role_policy_attachment" "ec2_cw_agent" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "cpsc454-ec2-profile"
  role = aws_iam_role.ec2.name
}

# Dashboard IAM User (least-privilege read-only)

resource "aws_iam_user" "dashboard" {
  name = "cpsc454-dashboard"
  tags = { Project = "cpsc454" }
}

resource "aws_iam_access_key" "dashboard" {
  user = aws_iam_user.dashboard.name
}

resource "aws_iam_user_policy" "dashboard_readonly" {
  name = "cpsc454-dashboard-readonly"
  user = aws_iam_user.dashboard.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadCloudWatchMetricsAndAlarms"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:GetMetricData",
          "cloudwatch:ListMetrics",
          "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      },
      {
        Sid    = "ReadEC2InstanceDetails"
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:DescribeVolumes"
        ]
        Resource = "*"
      },
      {
        Sid    = "ReadBudgets"
        Effect = "Allow"
        Action = ["budgets:ViewBudget"]
        Resource = "*"
      },
      {
        Sid      = "GetCallerIdentity"
        Effect   = "Allow"
        Action   = ["sts:GetCallerIdentity"]
        Resource = "*"
      }
    ]
  })
}
