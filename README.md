Setup Guide

Prerequisites: Terraform ≥ 1.6, Python 3.11+, AWS CLI configured with admin credentials for initial deployment.

Step 1 - Clone and configure
- cp terraform.tfvars.example terraform.tfvars
- Edit terraform.tfvars: set alert_email, trusted_ssh_cidr, and optionally aws_region

Step 2 - Deploy infrastructure
- terraform init
- terraform apply

- After apply, note the `ssh_command` output. Also retrieve the dashboard credentials:
- terraform output -raw dashboard_access_key_id
- terraform output -raw dashboard_secret_access_key

  
Step 3 - Confirm SNS email Subscription
- AWS sends a confirmation email to the alert address. Click the confirmation link before alarms can deliver.

Step 4 - Install dashboard dependencies
- pip install -r requirements.txt

Step 5 - Export credentials and run
- export AWS_ACCESS_KEY_ID=<dashboard key id>
- export AWS_SECRET_ACCESS_KEY=<dashboard secret>
- export AWS_DEFAULT_REGION=us-west-1
- python3 dashboard.py

- The dashboard launches immediately. Ctrl+C exits cleanly.
