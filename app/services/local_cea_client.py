# /data/inception/app/services/local_cea_client.py

import os
import requests
import json
import logging
import boto3
from botocore.exceptions import NoCredentialsError

# Default Ollama API endpoint and model name from /api/tags
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("OLLAMA_ENGINE", "gpt-oss:20b")  # Fixed per client requirement
CEA_MAX_TOKENS = int(os.environ.get("CEA_MAX_TOKENS", os.environ.get("OLLAMA_MAX_TOKENS", "200")))
CEA_TEMPERATURE = float(os.environ.get("CEA_TEMPERATURE", os.environ.get("OLLAMA_TEMPERATURE", "0.2")))
OLLAMA_NUM_THREAD = int(os.environ.get("OLLAMA_NUM_THREAD", "0"))  # 0 = library default
OLLAMA_NUM_GPU = int(os.environ.get("OLLAMA_NUM_GPU", "0"))  # 0 = auto/none
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", os.environ.get("CEA_NUM_CTX", "8192")))

def read_s3_context():
    """Read company context from S3 bucket."""
    try:
        s3 = boto3.client('s3', region_name=os.environ.get("S3_REGION", "eu-north-1"))
        bucket = os.environ.get("S3_BUCKET", "inception-context")
        obj = s3.get_object(Bucket=bucket, Key="company_details.yaml")
        import yaml
        raw = obj['Body'].read().decode('utf-8')
        # Cap context to avoid blowing prompt/ctx window
        if len(raw) > 4000:
            raw = raw[:4000]
        try:
            return yaml.safe_load(raw)
        except Exception:
            return {"raw": raw}
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

def call_local_cea(prompt, stream=False, timeout=300, num_predict=None, temperature=None):
    """
    Calls the locally hosted CEA model (e.g., gpt-oss:20b via Ollama).
    Returns the model's generated text.
    """
    # Read company context from S3
    s3_context = read_s3_context()
    if s3_context:
        prompt = f"Company Context: {s3_context}\n\n{prompt}"

    url = f"{OLLAMA_URL}/api/generate"
    effective_tokens = int(num_predict) if num_predict else CEA_MAX_TOKENS
    effective_temp = float(temperature) if temperature is not None else CEA_TEMPERATURE

    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "10m")
    # Safety: cap num_ctx to a sensible upper bound to avoid 400s if server is lower
    safe_num_ctx = max(2048, min(OLLAMA_NUM_CTX, 8192))

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "num_predict": effective_tokens,
            "temperature": effective_temp,
        }
    }
    # Only pass num_ctx if explicitly forced; otherwise let server default (avoids 400s on some builds)
    if os.environ.get("CEA_FORCE_NUM_CTX", "").strip().lower() in ("1", "true", "yes"):
        payload["options"]["num_ctx"] = safe_num_ctx
    # Only include stop sequences if provided via env to avoid API 400s
    stop_env = os.environ.get("CEA_STOP_SEQUENCES", "").strip()
    if stop_env:
        payload["options"]["stop"] = [s for s in stop_env.split("|") if s]
    # keep model in memory to avoid cold load between calls
    if keep_alive:
        payload["keep_alive"] = keep_alive
    if OLLAMA_NUM_THREAD:
        payload["options"]["num_thread"] = OLLAMA_NUM_THREAD
    if OLLAMA_NUM_GPU:
        payload["options"]["num_gpu"] = OLLAMA_NUM_GPU

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
        # Try to include server error body for debugging 400s
        err_text = ""
        try:
            err_text = f" body={response.text[:500]}" if 'response' in locals() and hasattr(response, 'text') else ""
        except Exception:
            pass
        logging.exception(f"Local CEA call failed: {e}{err_text}")
        raise RuntimeError(f"Failed to reach local CEA model: {e}{err_text}")

    except Exception as e:
        logging.exception(f"Unexpected error in call_local_cea: {e}")
        raise

