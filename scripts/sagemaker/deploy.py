#!/usr/bin/env python3
"""
Build the SD inference image, push to ECR, and create a SageMaker real-time endpoint.
Requires: AWS CLI configured, IAM role ARN; either Docker (local) or --skip-build (e.g. image from CodeBuild).

Usage:
  export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT:role/YourSageMakerRole
  python scripts/sagemaker/deploy.py
  python scripts/sagemaker/deploy.py --skip-build   # when image built on AWS (e.g. CodeBuild)
  python scripts/sagemaker/deploy.py --endpoint-name inq-sd --instance-type ml.g4dn.xlarge
  python scripts/sagemaker/deploy.py --skip-build --sd35 --async --async-s3-bucket MY_BUCKET  # async (no 60s limit)

Then set in Supabase: supabase secrets set SAGEMAKER_ENDPOINT_NAME=inq-sd
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def run(cmd, check=True, capture=False):
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if check and result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(result.returncode)
    return result


def main():
    print("SageMaker deploy: building image, pushing to ECR, creating endpoint.", flush=True)
    ap = argparse.ArgumentParser(description="Deploy Stable Diffusion to SageMaker")
    ap.add_argument("--region", "-r", default=None, help="AWS region (default: from env or us-east-1)")
    ap.add_argument("--role", default=None, help="SageMaker execution role ARN (or set SAGEMAKER_EXECUTION_ROLE_ARN)")
    ap.add_argument("--sd35", action="store_true", help="Use SD 3.5 image (Dockerfile.sd35, endpoint inq-sd35)")
    ap.add_argument("--endpoint-name", "-e", default=None, help="Endpoint name (default: inq-sd35 if --sd35 else inq-sd)")
    ap.add_argument("--instance-type", "-i", default="ml.g4dn.xlarge", help="Instance type (default: ml.g4dn.xlarge)")
    ap.add_argument("--ecr-repo", default=None, help="ECR repository name (default: inq-sd35 if --sd35 else inq-sd)")
    ap.add_argument("--skip-build", action="store_true", help="Skip Docker build (image already in ECR)")
    ap.add_argument("--no-wait", action="store_true", help="Return after create_endpoint; do not wait for InService")
    ap.add_argument("--async", dest="async_inference", action="store_true", help="Create async inference endpoint (no 60s limit; requires S3)")
    ap.add_argument("--async-s3-bucket", default=None, help="S3 bucket for async input/output (required if --async)")
    args = ap.parse_args()
    if args.endpoint_name is None:
        args.endpoint_name = "inq-sd35" if args.sd35 else "inq-sd"
    if args.ecr_repo is None:
        args.ecr_repo = "inq-sd35" if args.sd35 else "inq-sd"
    if args.async_inference:
        if not args.async_s3_bucket:
            print("--async requires --async-s3-bucket (e.g. my-sagemaker-async-bucket)", file=sys.stderr)
            sys.exit(1)
        if not args.endpoint_name.endswith("-async"):
            args.endpoint_name = args.endpoint_name + "-async"

    role = args.role or __import__("os").environ.get("SAGEMAKER_EXECUTION_ROLE_ARN")
    if not role:
        print("Set SAGEMAKER_EXECUTION_ROLE_ARN or pass --role=arn:aws:iam::ACCOUNT:role/YourSageMakerRole", file=sys.stderr)
        sys.exit(1)

    region = args.region or __import__("os").environ.get("AWS_DEFAULT_REGION", "us-east-1")
    account = run(
        ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
        capture=True,
    ).stdout.strip()
    ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com"
    image = f"{ecr_uri}/{args.ecr_repo}:latest"

    if not args.skip_build:
        dockerfile = "Dockerfile.sd35" if args.sd35 else "Dockerfile"
        print("Building Docker image (%s)..." % dockerfile)
        r = subprocess.run(
            ["docker", "build", "-f", str(SCRIPT_DIR / dockerfile), "-t", args.ecr_repo, str(SCRIPT_DIR)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(r.stderr or r.stdout or "Docker build failed.", file=sys.stderr)
            sys.exit(1)
        run(["docker", "tag", args.ecr_repo + ":latest", image])
        print("Logging in to ECR...")
        subprocess.run(
            ["bash", "-c", f"aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {ecr_uri}"],
            check=True,
        )
        print("Creating ECR repository if needed...")
        r = subprocess.run(
            ["aws", "ecr", "create-repository", "--repository-name", args.ecr_repo, "--region", region],
            capture_output=True,
            check=False,
        )
        if r.returncode != 0 and "RepositoryAlreadyExistsException" not in (r.stderr or b"").decode():
            print(r.stderr.decode(), file=sys.stderr)
            sys.exit(1)
        print("Pushing image to ECR...")
        run(["docker", "push", image])

    print("Creating SageMaker model and endpoint (this can take several minutes)...")
    import boto3
    import os as _os
    sm = boto3.client("sagemaker", region_name=region)
    model_name = args.endpoint_name + "-model"
    config_name = args.endpoint_name + "-config"
    if args.async_inference:
        model_name = args.ecr_repo + "-model"

    container_env = {}
    if args.sd35:
        hf_token = _os.environ.get("HF_TOKEN", "").strip()
        if not hf_token and (REPO_ROOT / ".env").is_file():
            try:
                with open(REPO_ROOT / ".env") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("HF_TOKEN="):
                            hf_token = line.split("=", 1)[1].strip().strip("'\"").strip()
                            break
            except OSError:
                pass
        if hf_token:
            container_env["HF_TOKEN"] = hf_token
            print("  HF_TOKEN set for gated model (from env or .env).")
        else:
            print("  HF_TOKEN not set; if the model is gated, add it to .env or export HF_TOKEN.", flush=True)

    try:
        sm.create_model(
            ModelName=model_name,
            PrimaryContainer={"Image": image, "Environment": container_env},
            ExecutionRoleArn=role,
        )
        print("  Created model:", model_name)
    except Exception as e:
        err = getattr(e, "response", {}).get("Error", {}) or {}
        if err.get("Code") != "ValidationException" or "already existing" not in str(e):
            raise
        print("  Model already exists:", model_name)

    try:
        config_kw = {
            "EndpointConfigName": config_name,
            "ProductionVariants": [
                {
                    "VariantName": "AllTraffic",
                    "ModelName": model_name,
                    "InstanceType": args.instance_type,
                    "InitialInstanceCount": 1,
                }
            ],
        }
        if args.async_inference:
            config_kw["AsyncInferenceConfig"] = {
                "OutputConfig": {
                    "S3OutputPath": f"s3://{args.async_s3_bucket.rstrip('/')}/sagemaker-async-inference/output/",
                }
            }
        sm.create_endpoint_config(**config_kw)
        print("  Created endpoint config:", config_name)
    except Exception as e:
        err = getattr(e, "response", {}).get("Error", {}) or {}
        msg = str(e).lower()
        if err.get("Code") != "ValidationException" or ("already exist" not in msg and "already existing" not in msg):
            raise
        print("  Endpoint config already exists:", config_name)

    try:
        sm.describe_endpoint(EndpointName=args.endpoint_name)
        print("  Endpoint already exists:", args.endpoint_name)
    except Exception as e:
        err = getattr(e, "response", {}).get("Error", {}) or {}
        if err.get("Code") != "ValidationException" or "Could not find endpoint" not in str(e):
            raise
        try:
            sm.create_endpoint(
                EndpointName=args.endpoint_name,
                EndpointConfigName=config_name,
            )
            print("  Created endpoint:", args.endpoint_name)
        except Exception as e2:
            err2 = getattr(e2, "response", {}).get("Error", {}) or {}
            code2 = err2.get("Code", "")
            msg2 = str(e2).lower()
            if code2 == "ResourceLimitExceeded":
                print("  Quota exceeded: account limit for this instance type is in use.", file=sys.stderr)
                raise
            if code2 != "ValidationException" or ("already exist" not in msg2 and "already existing" not in msg2):
                raise
            print("  Endpoint already exists or creating:", args.endpoint_name)

    if args.no_wait:
        print("Endpoint creation started. Check status with:")
        print(f"  aws sagemaker describe-endpoint --endpoint-name {args.endpoint_name} --query EndpointStatus --output text")
        return
    print("Waiting for endpoint to be InService (often 5–10 min)...")
    waiter = sm.get_waiter("endpoint_in_service")
    waiter.wait(EndpointName=args.endpoint_name)
    print(f"Endpoint deployed: {args.endpoint_name}")


if __name__ == "__main__":
    main()
