# CloudTrail was done manually (not via Terraform) because the Terraform bug
# AWS provider 5.x goes into an infinite OperationAborted loop on CreateBucket
# when the specific bucket name was previously interrupted mid-creation.
#
# What was created manually (already live):
#   S3 bucket  : 537515433655-cpsc454-trail  (us-west-1, public access blocked)
#   CloudTrail : cpsc454-cloudtrail           (us-west-1, logging = true)
#   ARN        : arn:aws:cloudtrail:us-west-1:537515433655:trail/cpsc454-cloudtrail
#
# To verify status:
#   aws cloudtrail get-trail-status --name cpsc454-cloudtrail --region us-west-1
