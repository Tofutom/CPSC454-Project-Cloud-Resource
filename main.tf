terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.6"
}

provider "aws" {
  region = var.aws_region
}

# Networking

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "cpsc454-vpc", Project = "cpsc454" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "cpsc454-igw", Project = "cpsc454" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true
  tags = { Name = "cpsc454-public-subnet", Project = "cpsc454" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "cpsc454-rt", Project = "cpsc454" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Security Group

resource "aws_security_group" "ec2" {
  name        = "cpsc454-ec2-sg"
  description = "SSH restricted to trusted IP; all outbound allowed"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from trusted IP only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.trusted_ssh_cidr]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cpsc454-ec2-sg", Project = "cpsc454" }
}

# EC2 Key Pair

resource "aws_key_pair" "monitoring" {
  key_name   = "cpsc454-key"
  public_key = file(var.ssh_public_key_path)
}

# EC2 Instance

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "monitored" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t3.micro"
  key_name               = aws_key_pair.monitoring.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  monitoring             = true   # detailed monitoring: 1-min CPU/network data instead of 5-min

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
    tags        = { Name = "cpsc454-root-ebs", Project = "cpsc454" }
  }

  # Installs and starts the CloudWatch agent so disk + memory metrics are sent
  user_data = <<-EOF
    #!/bin/bash
    yum install -y amazon-cloudwatch-agent

    cat > /opt/aws/amazon-cloudwatch-agent/bin/config.json << 'CW_CONFIG'
    {
      "agent": {
        "metrics_collection_interval": 60,
        "run_as_user": "cwagent"
      },
      "metrics": {
        "namespace": "CPSC454/EC2",
        "append_dimensions": {
          "InstanceId": "$${aws:InstanceId}"
        },
        "metrics_collected": {
          "disk": {
            "measurement": ["disk_used_percent"],
            "resources": ["/"],
            "metrics_collection_interval": 60
          },
          "mem": {
            "measurement": ["mem_used_percent"],
            "metrics_collection_interval": 60
          }
        }
      }
    }
    CW_CONFIG

    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
      -a fetch-config \
      -m ec2 \
      -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json \
      -s
  EOF

  tags = { Name = "cpsc454-monitored", Project = "cpsc454" }
}
