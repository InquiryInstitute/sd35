# SD 3.5

Stable Diffusion 3.5 project — SageMaker endpoints and tooling.

## Endpoints

- **inq-sd35** — synchronous SD 3.5 inference
- **inq-sd35-async** — asynchronous SD 3.5 inference (no 60s limit; used by CodeBuild)

## Quick test (existing endpoints)

```bash
pip install -r requirements.txt
python test_sd35_endpoint.py
```

Configure AWS credentials with access to invoke the SageMaker endpoints. On success, writes a test image to `/tmp/<endpoint>-test.png`.

---

## Deploy via AWS CodeBuild (recommended)

Build the Docker image in the cloud and create the **inq-sd35-async** endpoint. No local Docker required.

### 1. One-time: create CodeBuild project

**Option A — CLI (public repo or with CodeStar Connection):**

```bash
export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT:role/SageMaker-Inference-InqSD
# For private repo, create connection first:
#   ./scripts/sagemaker/create-codestar-connection.sh
#   export CODESTAR_CONNECTION_ARN=arn:aws:codestar-connections:...
./scripts/sagemaker/create-codebuild-sd35-project.sh
```

**Option B — CloudFormation:**

```bash
export CODESTAR_CONNECTION_ARN=arn:aws:codestar-connections:us-east-1:ACCOUNT:connection/...
export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT:role/SageMaker-Inference-InqSD
./scripts/sagemaker/deploy-codebuild-sd35-stack.sh
```

### 2. Store Hugging Face token (gated model)

```bash
aws ssm put-parameter --name /cards/sd35/hf-token --type SecureString --value "hf_..." --overwrite
```

### 3. Start a build

```bash
aws codebuild start-build --project-name sd35 --region us-east-1
```

The build runs `buildspec-sd35.yml`: builds the image, pushes to ECR `inq-sd35:latest`, then creates the **inq-sd35-async** endpoint. Override the async S3 bucket in the buildspec if needed (default: `inq-cards-sd35-async-548217737835`).

---

## Local deploy (Docker)

If you have Docker and want to build locally:

```bash
export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT:role/SageMaker-Inference-InqSD
export HF_TOKEN=hf_...   # if model is gated
python scripts/sagemaker/deploy.py --sd35
# Async (no 60s limit):
python scripts/sagemaker/deploy.py --skip-build --sd35 --async --async-s3-bucket YOUR_BUCKET
```

---

## Repo layout

- `buildspec-sd35.yml` — CodeBuild spec (build image, push ECR, create endpoint)
- `scripts/sagemaker/` — deploy script, Dockerfile, serve handler, CodeBuild/CloudFormation helpers
- `test_sd35_endpoint.py` — hit inq-sd35 and inq-sd35-async to verify they work
