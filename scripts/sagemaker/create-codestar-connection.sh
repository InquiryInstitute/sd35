#!/usr/bin/env bash
# Create a CodeStar Connection to GitHub via AWS CLI so CodeBuild can use it.
# The connection starts in PENDING; you must complete the GitHub OAuth in the
# console once (link is printed). Then use the connection ARN with
# create-codebuild-sd35-project.sh as CODESTAR_CONNECTION_ARN.
#
# Usage:
#   AWS_PROFILE=admin ./scripts/sagemaker/create-codestar-connection.sh
#   # Optional: CONNECTION_NAME=sd35-github (default for this repo)

set -e
CONNECTION_NAME="${CONNECTION_NAME:-sd35-github}"
REGION="${AWS_REGION:-us-east-1}"

echo "Creating CodeStar Connection (GitHub): $CONNECTION_NAME ..."
OUT=$(aws codestar-connections create-connection \
  --provider-type GitHub \
  --connection-name "$CONNECTION_NAME" \
  --region "$REGION" \
  --output json 2>&1) || true

if [[ "$OUT" == *"ConnectionArn"* ]]; then
  ARN=$(echo "$OUT" | grep -o '"ConnectionArn": "[^"]*"' | cut -d'"' -f4)
  echo ""
  echo "Connection created (status: PENDING)."
  echo "ConnectionArn: $ARN"
  echo ""
  echo "Complete the connection in the console (one-time GitHub OAuth):"
  echo "  https://${REGION}.console.aws.amazon.com/codesuite/settings/connections?region=${REGION}"
  echo ""
  echo "Then create the CodeBuild project with:"
  echo "  export CODESTAR_CONNECTION_ARN=$ARN"
  echo "  export GITHUB_REPO=InquiryInstitute/sd35"
  echo "  ./scripts/sagemaker/create-codebuild-sd35-project.sh"
elif [[ "$OUT" == *"already exists"* || "$OUT" == *"ResourceAlreadyExistsException"* ]]; then
  echo "Connection '$CONNECTION_NAME' already exists. Listing to get ARN..."
  aws codestar-connections list-connections --provider-type GitHub --region "$REGION" --output table
  echo ""
  ARN=$(aws codestar-connections list-connections --provider-type GitHub --region "$REGION" --query "Connections[?ConnectionName=='$CONNECTION_NAME'].ConnectionArn" --output text)
  if [[ -n "$ARN" ]]; then
    echo "Use: export CODESTAR_CONNECTION_ARN=$ARN"
  fi
else
  echo "$OUT" >&2
  exit 1
fi
