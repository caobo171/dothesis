#!/usr/bin/env bash
# DoThesis E2E entrypoint: ephemeral infra → migrations → Playwright.
#
# Why a wrapper and not Playwright globalSetup: the webServer processes need
# DATABASE_URL at boot and the schema must exist before the API's lifespan
# primes the orchestrator Postgres pools — sequencing that inside Playwright
# would lean on undocumented globalSetup/webServer ordering. A script makes
# the order explicit and identical locally and in CI.
#
# Deliberately separate from dev.sh (own ports, own container names): the
# dev stack and an E2E run can coexist on one machine.
#
# Usage: web/e2e/run-e2e.sh [playwright args…]
#   e.g. web/e2e/run-e2e.sh tests/onboarding.spec.ts --headed
set -euo pipefail
cd "$(dirname "$0")/.."   # → web/

PG_NAME=dothesis-e2e-pg
MINIO_NAME=dothesis-e2e-minio
PG_PORT="${DOTHESIS_E2E_PG_PORT:-55432}"
MINIO_PORT="${DOTHESIS_E2E_MINIO_PORT:-9123}"

cleanup() { docker rm -f "$PG_NAME" "$MINIO_NAME" >/dev/null 2>&1 || true; rm -f "$(pwd)/.e2e-aws-config"; }
trap cleanup EXIT
cleanup   # clear leftovers from a crashed previous run

docker run -d --name "$PG_NAME" \
  -e POSTGRES_USER=e2e -e POSTGRES_PASSWORD=e2e -e POSTGRES_DB=dothesis_e2e \
  -p "${PG_PORT}:5432" postgres:16-alpine >/dev/null
docker run -d --name "$MINIO_NAME" \
  -p "${MINIO_PORT}:9000" minio/minio server /data >/dev/null

echo "==> waiting for postgres (:${PG_PORT})"
for _ in $(seq 1 60); do
  docker exec "$PG_NAME" pg_isready -U e2e -d dothesis_e2e >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$PG_NAME" pg_isready -U e2e -d dothesis_e2e >/dev/null

echo "==> waiting for minio (:${MINIO_PORT})"
for _ in $(seq 1 60); do
  curl -sf "http://localhost:${MINIO_PORT}/minio/health/ready" >/dev/null && break
  sleep 1
done
curl -sf "http://localhost:${MINIO_PORT}/minio/health/ready" >/dev/null

export DATABASE_URL="postgresql+psycopg://e2e:e2e@localhost:${PG_PORT}/dothesis_e2e"
export AWS_ENDPOINT_URL_S3="http://localhost:${MINIO_PORT}"
# Settings requires SESSION_SECRET even for alembic (env.py imports app config
# and there is no repo-root .env on CI).
export SESSION_SECRET="${SESSION_SECRET:-dothesis-e2e-secret}"
# alembic's migrations/env.py builds the FULL app Settings() (get_settings()),
# whose aws_region/s3_bucket/aws_access_key/aws_secret_key fields have no
# defaults — so the migration step, not just uvicorn, needs them in-env (no
# worktree .env supplies them on CI). Mirror the exact values playwright.config.ts
# hands the uvicorn webServer so alembic and the app agree on one MinIO identity.
export S3_BUCKET="${S3_BUCKET:-dothesis-e2e}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_ACCESS_KEY="${AWS_ACCESS_KEY:-minioadmin}"
export AWS_SECRET_KEY="${AWS_SECRET_KEY:-minioadmin}"
# Standard names too, for boto3's default credential chain (bucket-create below).
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"

# Force S3 path-style addressing. MinIO on a localhost/custom endpoint needs this or
# presigned download URLs come back virtual-hosted (bucket.localhost:9123/...), which the
# download leg can't reach. There is NO environment variable for this in botocore —
# DEFAULT_S3_CONFIG_VARS['addressing_style'] maps to no env var (verified against
# botocore/configprovider.py) — AWS_CONFIG_FILE is the real, supported mechanism, and it
# applies uniformly to every boto3 client in this process tree (the bucket-create script
# below AND the uvicorn app process webServer starts later both inherit this env). No app
# code change needed.
export AWS_CONFIG_FILE="$(pwd)/.e2e-aws-config"
cat > "$AWS_CONFIG_FILE" <<'CFG'
[default]
s3 =
  addressing_style = path
CFG

echo "==> alembic upgrade head"
(cd ../api && ./run.sh alembic upgrade head)

echo "==> creating MinIO bucket"
# Reuses the api venv's boto3 — no mc/aws-cli host dependency.
(cd ../api && ./run.sh python - <<'PY'
import os
import boto3
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["AWS_ENDPOINT_URL_S3"],
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    region_name="us-east-1",
)
try:
    s3.create_bucket(Bucket="dothesis-e2e")
except s3.exceptions.BucketAlreadyOwnedByYou:
    pass
print("bucket ready")
PY
)

# The export suite needs LibreOffice (run_export builds the PDF via soffice
# headless). Skip that suite loudly instead of failing mysteriously.
if command -v soffice >/dev/null 2>&1; then
  export DOTHESIS_E2E_HAS_SOFFICE=1
else
  echo "==> soffice not found — export.spec.ts will self-skip"
fi

echo "==> playwright test"
npx playwright test "$@"
