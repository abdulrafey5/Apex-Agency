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

# === DB Credentials ===========================================================
# 🔐 PRODUCTION: DB credentials are fetched by DatabaseService from Secrets Manager.
# DO NOT fetch secrets here - let db_service.py handle it at runtime.
# This ensures password rotation works correctly.

# === Create Flask app ========================================================
app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)

# === Security & session configuration =======================================
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-key")
# Session persistence: 30 days (for thread history persistence across logins)
PERMANENT_SESSION_LIFETIME = 30 * 24 * 60 * 60  # 30 days in seconds
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=PERMANENT_SESSION_LIFETIME,
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
    os.getenv("SHARED_THREAD", "true").strip().lower() in ("1", "true", "yes")
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

# === Optional YAML initialization ===========================================
from utils.yaml_utils import load_yaml, save_yaml

if not MEMORY_FILE.exists():
    save_yaml(MEMORY_FILE, {"shared_context": {}, "conversation": []})

# ============================================================================#
# 🔥 CRITICAL: Warm up services at startup (removes first-login lag)
# ============================================================================#
try:
    from services.db_service import get_db_service
    from services.rag_service import RAGService

    _db = get_db_service()
    _rag = RAGService()
    print("✅ Core services warmed at startup")
except Exception as e:
    print(f"⚠️ Service warmup failed: {e}")

# === Register blueprints =====================================================
from routes.auth import auth_bp
from routes.chat import chat_bp

app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)

# === Root route ==============================================================
@app.route("/")
def root():
    return "✅ Inception backend running."

# === Optional warmup endpoint ===============================================
@app.route("/_warmup")
def warmup():
    return {"status": "ok"}

# === Entry point =============================================================
if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 3000)),
        debug=os.getenv("DEBUG", "false").lower() in ("1", "true"),
    )
