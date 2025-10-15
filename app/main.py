#!/usr/bin/env python3
from pathlib import Path
import os
from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

# === Load environment ========================================================
ROOT = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")

# === Create Flask app ========================================================
app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)

# === Security & session configuration =======================================
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-key")
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# === Reverse proxy fix =======================================================
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# === Directory structure =====================================================
LOG_DIR = ROOT / "app" / "logs"
CHAT_DIR = ROOT / "storage" / "chat_history"
INSTRUCTIONS_DIR = ROOT / "storage" / "instructions"
AGENTS_DIR = INSTRUCTIONS_DIR / "agents"
MEMORY_FILE = INSTRUCTIONS_DIR / "memory.yaml"

for path in [LOG_DIR, CHAT_DIR, INSTRUCTIONS_DIR, AGENTS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# === Environment-based configuration ========================================
app.config["COGNITO"] = {
    "domain": os.getenv("COGNITO_DOMAIN"),
    "client_id": os.getenv("CLIENT_ID"),
    "secret": os.getenv("CLIENT_SECRET"),
    "redirect": os.getenv("REDIRECT_URI"),
    "logout": os.getenv("LOGOUT_REDIRECT"),
}

app.config["GROK"] = {
    "url": os.getenv("GROK_API_URL", "https://api.x.ai/v1/chat/completions"),
    "key": os.getenv("GROK_API_KEY"),
    "model": os.getenv("GROK_MODEL", "grok-4-fast"),
}

app.config["SHARED_THREAD"] = (
    os.getenv("SHARED_THREAD", "false").strip().lower() in ("1", "true", "yes")
)
app.config.update(
    CHAT_DIR=str(CHAT_DIR),
    LOG_DIR=str(LOG_DIR),
    INSTRUCTIONS_DIR=str(INSTRUCTIONS_DIR),
    AGENTS_DIR=str(AGENTS_DIR),
    MEMORY_FILE=str(MEMORY_FILE),
)

# === Logging setup ===========================================================
from utils.logger import setup_logging
setup_logging(LOG_DIR)

print("Loaded Cognito config:", app.config["COGNITO"])

# === Optional YAML initialization ===========================================
from utils.yaml_utils import load_yaml, save_yaml

if not MEMORY_FILE.exists():
    print("Creating empty YAML memory file...")
    save_yaml(MEMORY_FILE, {"shared_context": {}, "conversation": []})

# === Register blueprints =====================================================
from routes.auth import auth_bp
from routes.chat import chat_bp

# Important: no prefix → route is /chat-ui not /chat/chat-ui
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)

# === Root route ==============================================================
@app.route("/")
def root():
    return "✅ Inception backend running with YAML-ready configuration."

# === Entry point =============================================================
if __name__ == "__main__":
    import logging
    logging.info(f"Starting Inception backend... SHARED_THREAD={app.config['SHARED_THREAD']}")
    print(app.url_map)  # Debug: show all routes on startup
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 3000)),
        debug=os.getenv("DEBUG", "false").lower() in ("1", "true"),
    )

