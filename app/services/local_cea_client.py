# /data/inception/app/services/local_cea_client.py

import os
import requests
import json
import logging

# Default Ollama API endpoint and model name from /api/tags
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_ENGINE", "gpt-oss:20b")  # ✅ fixed model name

def call_local_cea(prompt, stream=False, timeout=180):
    """
    Calls the locally hosted CEA model (e.g., gpt-oss:20b via Ollama).
    Returns the model's generated text.
    """
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

