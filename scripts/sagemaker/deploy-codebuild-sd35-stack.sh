#!/usr/bin/env bash
# Deploy the CodeBuild project via CloudFormation (avoids CLI "not authorized to access connection" when run by a user that can create stacks).
# Prerequisites: CodeStar/CodeConnections connection is AVAILABLE; role CodeBuild-SD35-ServiceRole exists with ECR, SageMaker, SSM, connection permissions.
#
# Usage:
#   export CODESTAR_CONNECTION_ARN=arn:aws:codestar-connections:us-east-1:ACCOUNT:connection/...
#   export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT:role/SageMaker-Inference-InqSD
#   AWS_PROFILE=admin ./scripts/sagemaker/deploy-codebuild-sd35-stack.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_NAME="${STACK_NAME:-sd35}"
REGION="${AWS_REGION:-us-east-1}"
GITHUB_REPO="${GITHUB_REPO:-InquiryInstitute/sd35}"

CODESTAR_CONNECTION_ARN="${CODESTAR_CONNECTION_ARN:?Set CODESTAR_CONNECTION_ARN}"
SAGEMAKER_EXECUTION_ROLE_ARN="${SAGEMAKER_EXECUTION_ROLE_ARN:?Set SAGEMAKER_EXECUTION_ROLE_ARN}"

echo "Deploying stack $STACK_NAME (CodeBuild project sd35)..."
aws cloudformation create-stack \
  --stack-name "$STACK_NAME" \
  --template-body "file://$SCRIPT_DIR/codebuild-sd35.yaml" \
  --parameters \
    "ParameterKey=ConnectionArn,ParameterValue=$CODESTAR_CONNECTION_ARN" \
    "ParameterKey=GitHubRepo,ParameterValue=$GITHUB_REPO" \
    "ParameterKey=SageMakerExecutionRoleArn,ParameterValue=$SAGEMAKER_EXECUTION_ROLE_ARN" \
    "ParameterKey=Region,ParameterValue=$REGION" \
  --region "$REGION" 2>&1 || {
  if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &>/dev/null; then
    echo "Stack exists. Updating..."
    aws cloudformation update-stack \
      --stack-name "$STACK_NAME" \
      --template-body "file://$SCRIPT_DIR/codebuild-sd35.yaml" \
      --parameters \
        "ParameterKey=ConnectionArn,ParameterValue=$CODESTAR_CONNECTION_ARN" \
        "ParameterKey=GitHubRepo,ParameterValue=$GITHUB_REPO" \
        "ParameterKey=SageMakerExecutionRoleArn,ParameterValue=$SAGEMAKER_EXECUTION_ROLE_ARN" \
        "ParameterKey=Region,ParameterValue=$REGION" \
      --region "$REGION" 2>&1
  else
    exit 1
  fi
}

echo "Waiting for stack to be ready..."
aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$REGION" 2>/dev/null || \
  aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" --region "$REGION" 2>/dev/null || true

echo "Done. Start a build with:"
echo "  aws codebuild start-build --project-name sd35 --region $REGION"
