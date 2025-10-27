# /data/inception/app/services/local_cea_client.py

import os
import requests
import json
import logging
import boto3
from botocore.exceptions import NoCredentialsError

# Default Ollama API endpoint and model name from /api/tags
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_ENGINE", "gpt-oss:20b")  # CEA uses ChatGPT-OSS-20B with MXFP4-bit quantization on GPU

def read_s3_context():
    """Read company context from S3 bucket."""
    try:
        s3 = boto3.client('s3', region_name=os.environ.get("S3_REGION", "eu-north-1"))
        bucket = os.environ.get("S3_BUCKET", "inception-context")
        obj = s3.get_object(Bucket=bucket, Key="company_details.yaml")
        import yaml
        return yaml.safe_load(obj['Body'].read().decode('utf-8'))
    except Exception as e:
        logging.warning(f"Failed to read S3 context: {e}")
        return {}

def write_s3_context(context):
    """Write updated context to S3 (if needed for future)."""
    try:
        s3 = boto3.client('s3', region_name=os.environ.get("S3_REGION", "eu-north-1"))
        bucket = os.environ.get("S3_BUCKET", "inception-context")
        import yaml
        s3.put_object(Bucket=bucket, Key="company_details.yaml", Body=yaml.dump(context))
    except Exception as e:
        logging.warning(f"Failed to write S3 context: {e}")

def call_local_cea(prompt, stream=False, timeout=300):
    """
    Calls the locally hosted CEA model (e.g., gpt-oss:20b via Ollama).
    Returns the model's generated text.
    """
    # Read company context from S3
    s3_context = read_s3_context()
    if s3_context:
        prompt = f"Company Context: {s3_context}\n\n{prompt}"

    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": stream
    }

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        # Handle both stream and full responses
        if stream:
            text_output = ""
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        text_output += chunk.get("response", "")
                    except json.JSONDecodeError:
                        continue
            return text_output.strip()
        else:
            data = response.json()
            return data.get("response", "").strip()

    except requests.exceptions.RequestException as e:
        logging.exception(f"Local CEA call failed: {e}")
        raise RuntimeError(f"Failed to reach local CEA model: {e}")

    except Exception as e:
        logging.exception(f"Unexpected error in call_local_cea: {e}")
        raise

