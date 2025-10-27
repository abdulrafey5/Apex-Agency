import os
import requests
import json
import logging

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_ENGINE = os.getenv("OLLAMA_ENGINE", "gpt-oss:20b")
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "512"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))

def call_worker_api(prompt):
    try:
        payload = {
            "model": OLLAMA_ENGINE,
            "prompt": prompt,
            "options": {
                "temperature": OLLAMA_TEMPERATURE,
                "num_predict": OLLAMA_MAX_TOKENS
            }
        }

        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True)
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


