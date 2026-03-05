#!/usr/bin/env python3
"""
Quick test to check if SD 3.5 SageMaker endpoint is working.
Tests both inq-sd35 and inq-sd35-async endpoints.
"""
import json
import sys
import boto3
from pathlib import Path

def test_endpoint(endpoint_name, region="us-east-1"):
    """Test a SageMaker endpoint with a simple prompt."""
    print(f"\nTesting endpoint: {endpoint_name}")
    print("-" * 50)
    
    try:
        client = boto3.client("sagemaker-runtime", region_name=region)
        
        # Simple test prompt
        payload = {
            "prompt": "a red apple on a wooden table",
            "negative_prompt": ""
        }
        
        print(f"Invoking endpoint with prompt: '{payload['prompt']}'")
        response = client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps(payload)
        )
        
        result = json.loads(response["Body"].read())
        
        if "image" in result:
            # Save the image
            import base64
            image_data = base64.b64decode(result["image"])
            output_path = Path(f"/tmp/{endpoint_name}-test.png")
            output_path.write_bytes(image_data)
            print(f"✓ SUCCESS: Image generated and saved to {output_path}")
            print(f"  Image size: {len(image_data)} bytes")
            return True
        elif "error" in result:
            print(f"✗ ENDPOINT ERROR: {result['error']}")
            return False
        else:
            print(f"✗ UNEXPECTED RESPONSE: {result}")
            return False
            
    except client.exceptions.ValidationError as e:
        print(f"✗ ENDPOINT NOT FOUND: {e}")
        return False
    except Exception as e:
        error_msg = str(e)
        if "AccessDenied" in error_msg:
            print(f"✗ ACCESS DENIED: Check IAM permissions for sagemaker:InvokeEndpoint")
        else:
            print(f"✗ ERROR: {e}")
        return False

def main():
    print("=" * 50)
    print("SD 3.5 SageMaker Endpoint Test")
    print("=" * 50)
    
    # Test both endpoints
    endpoints = ["inq-sd35", "inq-sd35-async"]
    results = {}
    
    for endpoint in endpoints:
        results[endpoint] = test_endpoint(endpoint)
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for endpoint, success in results.items():
        status = "✓ WORKING" if success else "✗ NOT WORKING"
        print(f"{endpoint}: {status}")
    
    # Exit code
    if any(results.values()):
        print("\nAt least one endpoint is working!")
        sys.exit(0)
    else:
        print("\nNo endpoints are working. Check deployment status.")
        sys.exit(1)

if __name__ == "__main__":
    main()
