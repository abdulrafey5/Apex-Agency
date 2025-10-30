import os
import requests
import json
import logging

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_ENGINE = os.getenv("OLLAMA_ENGINE", "llama3.1:8b-instruct")
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "200"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_REQUEST_TIMEOUT_S = int(os.getenv("OLLAMA_REQUEST_TIMEOUT_S", "60"))

def call_worker_api(prompt):
    try:
        payload = {
            "model": OLLAMA_ENGINE,
            "prompt": prompt,
            "options": {
                "temperature": OLLAMA_TEMPERATURE,
                "num_predict": OLLAMA_MAX_TOKENS,
                "top_p": 0.9,
                "mirostat": 0
            }
        }

        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=OLLAMA_REQUEST_TIMEOUT_S)
        response.raise_for_status()

        # Accumulate streamed output
        final_text = ""
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "response" in data:
                    final_text += data["response"]
                if data.get("done", False):
                    break

        return final_text.strip()

    except Exception as e:
        logging.error(f"Ollama API failed: {e}")
        raise


