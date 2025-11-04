# /data/inception/app/services/local_cea_client.py

import os
import requests
import json
import logging
import boto3
from botocore.exceptions import NoCredentialsError
import threading

# Default Ollama API endpoint and model name from /api/tags
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("OLLAMA_ENGINE", "gpt-oss:20b")  # Fixed per client requirement
CEA_MAX_TOKENS = int(os.environ.get("CEA_MAX_TOKENS", os.environ.get("OLLAMA_MAX_TOKENS", "200")))
CEA_TEMPERATURE = float(os.environ.get("CEA_TEMPERATURE", os.environ.get("OLLAMA_TEMPERATURE", "0.2")))
OLLAMA_NUM_THREAD = int(os.environ.get("OLLAMA_NUM_THREAD", "0"))  # 0 = library default
OLLAMA_NUM_GPU = int(os.environ.get("OLLAMA_NUM_GPU", "0"))  # 0 = auto/none
# Match Ollama service context length (1024) to avoid truncation
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", os.environ.get("CEA_NUM_CTX", "1024")))

# Lock to prevent concurrent Ollama requests that cause multiple runners (partial GPU offload)
_OLLAMA_LOCK = threading.Lock()

def read_s3_context():
    """Read company context from S3 bucket."""
    try:
        if os.environ.get("S3_CONTEXT_DISABLE", "").strip().lower() in ("1", "true", "yes"):  # allow disabling for perf
            return {}
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

def call_local_cea(prompt, stream=True, timeout=300, num_predict=None, temperature=None):
    """
    Calls the locally hosted CEA model (e.g., gpt-oss:20b via Ollama).
    Returns the model's generated text.
    Uses a lock to prevent concurrent requests that cause multiple runners (partial GPU offload).
    """
    # Read company context from S3
    s3_context = read_s3_context()
    if s3_context:
        # Truncate context if combined prompt would exceed context window
        context_str = str(s3_context)
        max_context_chars = 200  # Reserve space for prompt and response
        if len(context_str) > max_context_chars:
            context_str = context_str[:max_context_chars] + "..."
        prompt = f"Company Context: {context_str}\n\n{prompt}"
    
    # Truncate prompt if too long to fit in context window
    # Reserve ~100 tokens for response, so max prompt ~900 tokens (~3600 chars)
    max_prompt_chars = 3600
    if len(prompt) > max_prompt_chars:
        logging.warning(f"Prompt truncated from {len(prompt)} to {max_prompt_chars} chars")
        prompt = prompt[:max_prompt_chars] + "\n[Prompt truncated due to context limits]"

    url = f"{OLLAMA_URL}/api/generate"
    effective_tokens = int(num_predict) if num_predict else CEA_MAX_TOKENS
    effective_temp = float(temperature) if temperature is not None else CEA_TEMPERATURE

    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "10m")
    # Match Ollama service OLLAMA_CONTEXT_LENGTH=1024 to avoid truncation warnings
    # Cap at 1024 to match service config and prevent prompt truncation
    safe_num_ctx = min(OLLAMA_NUM_CTX, 1024)

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "num_predict": effective_tokens,
            "temperature": effective_temp,
        }
    }
    # Always set num_ctx to match service config and prevent truncation
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

    # Use lock to prevent concurrent Ollama requests that spawn multiple runners
    # This ensures we always use the single runner with full GPU (25/25 layers)
    with _OLLAMA_LOCK:
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

