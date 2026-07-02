#!/bin/bash
# Builds the frontend against the deployed API and syncs it to the S3
# bucket behind CloudFront. Run from the repo root, after the
# `fuel-route-planner` SAM stack has been deployed at least once.
set -euo pipefail
cd "$(dirname "$0")/.."

STACK_NAME=fuel-route-planner

API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text)
DISTRIBUTION_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" --output text)

echo "API_URL=$API_URL"
echo "BUCKET=$BUCKET"
echo "DISTRIBUTION_ID=$DISTRIBUTION_ID"

(cd frontend && VITE_API_BASE_URL="${API_URL%/}" npm run build)

aws s3 sync frontend/dist/ "s3://${BUCKET}/" --delete
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"

CLOUDFRONT_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" --output text)
echo "Deployed: $CLOUDFRONT_URL"
