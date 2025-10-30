import requests
import logging
import os


def grok_chat(messages, grok_config):
    # Try to get config from environment if not provided
    if not grok_config:
        grok_config = {
            "key": os.getenv("GROK_API_KEY"),
            "url": os.getenv("GROK_API_URL", "https://api.x.ai/v1/chat/completions"),
            "model": os.getenv("GROK_MODEL", "grok-4-fast")
        }

    if not grok_config or not grok_config.get("key"):
        raise RuntimeError("Grok API key not configured")

    # Tunables with sensible faster defaults
    max_tokens = int(os.getenv("GROK_MAX_TOKENS", "200"))
    temperature = float(os.getenv("GROK_TEMPERATURE", "0.3"))
    timeout_s = int(os.getenv("GROK_TIMEOUT_S", "20"))

    headers = {"Authorization": f"Bearer {grok_config['key']}", "Content-Type": "application/json"}
    payload = {
        "model": grok_config.get("model", "grok-4-fast"),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = requests.post(grok_config.get("url"), json=payload, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        logging.debug("Unexpected Grok response: %s", data)
        return str(data)[:1000]

