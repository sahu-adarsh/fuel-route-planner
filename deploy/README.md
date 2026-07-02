# Deploying

Stack name: `fuel-route-planner`, region `us-east-1`, account `207423186601`.

Live URLs:
- Frontend: https://d12yi4wtavx758.cloudfront.net
- API: https://pjtcs90ffi.execute-api.us-east-1.amazonaws.com/

## First-time setup / infra changes (`template.yaml`)

Requires an OpenRouteService API key and a Django secret key (generate one with
`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`).

```bash
./deploy/package_backend.sh   # copies data/fuel_stations.json into backend/, runs sam build

sam deploy \
  --stack-name fuel-route-planner \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --no-confirm-changeset \
  --tags Project=fuel-route-planner \
  --parameter-overrides "OrsApiKey=<your-ors-key> DjangoSecretKey=<your-secret>"
```

`CorsAllowedOrigins` defaults to this stack's own CloudFront domain + localhost (see
`template.yaml`), so it doesn't need to be passed again unless the frontend moves to a
different domain. Re-run `SECRET_KEY` from the *existing* deployment (via
`aws lambda get-function-configuration --function-name fuel-route-planner-api --query
'Environment.Variables.SECRET_KEY' --output text`) rather than generating a new one, or
every deploy invalidates existing sessions/CSRF tokens for no reason.

## Backend code changes only

```bash
./deploy/package_backend.sh
sam deploy --stack-name fuel-route-planner  # reuses the last-used parameters
```

## Frontend changes

```bash
./deploy/deploy_frontend.sh
```

Builds against the deployed API URL, syncs `frontend/dist/` to S3, and invalidates
CloudFront. Requires the stack to already exist (reads its outputs).

## Known simplification

Django admin's static assets (CSS/JS) aren't collected or served in this deployment -
`/admin/` will load unstyled. Not worth solving here since there's no live database in
production (docs/decisions.md ADR-002) for admin to manage in the first place.
