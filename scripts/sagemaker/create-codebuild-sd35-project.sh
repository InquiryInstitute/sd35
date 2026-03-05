#!/usr/bin/env bash
# Create the CodeBuild project and IAM role for building SD 3.5 in the cloud.
# Requires: AWS CLI with admin (or sufficient IAM + codebuild permissions).
#
# Usage:
#   export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT:role/SageMaker-Inference-InqSD
#   export GITHUB_REPO=InquiryInstitute/sd35   # default for this repo
#   AWS_PROFILE=admin ./scripts/sagemaker/create-codebuild-sd35-project.sh
#
# For private GitHub repo: create a CodeStar Connection first:
#   AWS_PROFILE=admin ./scripts/sagemaker/create-codestar-connection.sh
# Complete the GitHub OAuth in the printed console URL, then pass CODESTAR_CONNECTION_ARN here.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_NAME="${CODEBUILD_PROJECT_NAME:-sd35}"
ROLE_NAME="${CODEBUILD_ROLE_NAME:-CodeBuild-SD35-ServiceRole}"
POLICY_NAME="${CODEBUILD_POLICY_NAME:-CodeBuild-SD35-Policy}"
REGION="${AWS_REGION:-us-east-1}"

SAGEMAKER_EXECUTION_ROLE_ARN="${SAGEMAKER_EXECUTION_ROLE_ARN:?Set SAGEMAKER_EXECUTION_ROLE_ARN (e.g. arn:aws:iam::ACCOUNT:role/SageMaker-Inference-InqSD)}"
GITHUB_REPO="${GITHUB_REPO:-InquiryInstitute/sd35}"
# Strip URL prefix if present
GITHUB_LOCATION="${GITHUB_REPO#https://github.com/}"
GITHUB_LOCATION="${GITHUB_LOCATION#http://github.com/}"
GITHUB_LOCATION="${GITHUB_LOCATION%.git}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

echo "Creating IAM role $ROLE_NAME for CodeBuild..."
cat > /tmp/codebuild-trust.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "codebuild.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF
aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file:///tmp/codebuild-trust.json 2>/dev/null || echo "Role $ROLE_NAME already exists."
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "arn:aws:iam::aws:policy/service-role/AWSCodeBuildServiceRole" 2>/dev/null || true

echo "Creating inline policy $POLICY_NAME..."
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" --policy-document file://"$SCRIPT_DIR/iam-codebuild-sd35-policy.json"
echo "Waiting for IAM role to be usable..."
sleep 10

echo "Creating CodeBuild project $PROJECT_NAME..."
if [[ -n "$CODESTAR_CONNECTION_ARN" ]]; then
  cat > /tmp/codebuild-source.json << SOURCE
{
  "type": "GITHUB",
  "location": "https://github.com/${GITHUB_LOCATION}",
  "gitCloneDepth": 1,
  "buildspec": "buildspec-sd35.yml",
  "insecureSsl": false,
  "reportBuildStatus": true,
  "auth": {
    "type": "CODECONNECTIONS",
    "resource": "${CODESTAR_CONNECTION_ARN}"
  }
}
SOURCE
else
  cat > /tmp/codebuild-source.json << SOURCE
{
  "type": "GITHUB",
  "location": "https://github.com/${GITHUB_LOCATION}",
  "gitCloneDepth": 1,
  "buildspec": "buildspec-sd35.yml",
  "insecureSsl": false,
  "reportBuildStatus": true
}
SOURCE
fi

cat > /tmp/codebuild-env.json << ENV
{
  "type": "LINUX_CONTAINER",
  "image": "aws/codebuild/standard:7.0",
  "computeType": "BUILD_GENERAL1_LARGE",
  "privilegedMode": true,
  "environmentVariables": [
    {"name": "SAGEMAKER_EXECUTION_ROLE_ARN", "value": "${SAGEMAKER_EXECUTION_ROLE_ARN}", "type": "PLAINTEXT"},
    {"name": "AWS_REGION", "value": "${REGION}", "type": "PLAINTEXT"}
  ]
}
ENV

aws codebuild create-project \
  --name "$PROJECT_NAME" \
  --source file:///tmp/codebuild-source.json \
  --artifacts "{\"type\":\"NO_ARTIFACTS\"}" \
  --environment file:///tmp/codebuild-env.json \
  --service-role "$ROLE_ARN" \
  --region "$REGION" && echo "Project created." || {
  echo "Project may already exist. Updating..."
  aws codebuild update-project \
    --name "$PROJECT_NAME" \
    --source file:///tmp/codebuild-source.json \
    --artifacts "{\"type\":\"NO_ARTIFACTS\"}" \
    --environment file:///tmp/codebuild-env.json \
    --service-role "$ROLE_ARN" \
    --region "$REGION"
}

echo ""
echo "Done. Next steps:"
echo "  1. Store HF_TOKEN in Parameter Store (for gated model):"
echo "     aws ssm put-parameter --name /cards/sd35/hf-token --type SecureString --value \"YOUR_HF_TOKEN\""
echo "  2. If using private GitHub: create a CodeStar Connection and re-run with CODESTAR_CONNECTION_ARN."
echo "  3. Start a build:"
echo "     aws codebuild start-build --project-name $PROJECT_NAME --region $REGION"
