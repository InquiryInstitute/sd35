# SD 3.5

Stable Diffusion 3.5 project — SageMaker endpoints and tooling.

## Endpoints

- **inq-sd35** — synchronous SD 3.5 inference
- **inq-sd35-async** — asynchronous SD 3.5 inference

## Setup

```bash
pip install -r requirements.txt
```

Configure AWS credentials (e.g. `aws configure` or env vars) with access to invoke the SageMaker endpoints.

## Test endpoints

```bash
python test_sd35_endpoint.py
```

Tests both endpoints with a simple prompt and reports status. On success, writes a test image to `/tmp/<endpoint>-test.png`.
