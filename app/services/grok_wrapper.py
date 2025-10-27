# /data/inception/app/services/grok_wrapper.py
import os, requests, logging

GROK_URL = os.environ.get("GROK_API_URL", "https://api.x.ai/v1/chat/completions")

def call_worker_api(prompt, timeout=60):
    from dotenv import load_dotenv
    load_dotenv('/data/inception/app/.env')  # Explicit path
    GROK_KEY = os.environ.get("GROK_API_KEY")
    logging.info(f"GROK_KEY loaded in web app: {bool(GROK_KEY)}")
    headers = {"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"} if GROK_KEY else {}
    payload = {
        "model": "grok-4-0709",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": 512
    }
    try:
        r = requests.post(GROK_URL, json=payload, headers=headers, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        # adapt to your response format
        if "choices" in j and j["choices"]:
            return j["choices"][0].get("message", {}).get("content") or j["choices"][0].get("text")
        return j
    except Exception:
        logging.exception("Worker API failed")
        raise

