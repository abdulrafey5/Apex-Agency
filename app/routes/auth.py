from flask import Blueprint, current_app, redirect, request, session, jsonify
import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

auth_bp = Blueprint("auth", __name__)

# Create a session with connection pooling and retries for faster Cognito calls
_session = requests.Session()
retry_strategy = Retry(
    total=2,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=2, pool_maxsize=2)
_session.mount("https://", adapter)

@auth_bp.route("/login")
def login():
    cognito = current_app.config["COGNITO"]
    if not cognito.get("domain") or not cognito.get("client_id"):
        logging.error("Cognito not configured")
        return "Cognito not configured", 500

    return redirect(
        f"https://{cognito['domain']}/oauth2/authorize?"
        f"response_type=code&client_id={cognito['client_id']}&redirect_uri={cognito['redirect']}&scope=email+openid+profile"
    )

@auth_bp.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Missing 'code'.", 400

    cognito = current_app.config["COGNITO"]
    data = {
        "grant_type": "authorization_code",
        "client_id": cognito["client_id"],
        "code": code,
        "redirect_uri": cognito["redirect"],
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if cognito.get("secret"):
        auth = base64.b64encode(f"{cognito['client_id']}:{cognito['secret']}".encode()).decode()
        headers["Authorization"] = f"Basic {auth}"

    try:
        # Use session with connection pooling for faster requests
        r = _session.post(f"https://{cognito['domain']}/oauth2/token", data=data, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        logging.error("Cognito token request timed out after 10 seconds")
        return "Login timeout - Cognito service is slow. Please try again.", 504
    except Exception as e:
        logging.exception("Cognito token error")
        return f"Error retrieving tokens: {e}", 400

    tokens = r.json()
    session.update({
        "id_token": tokens.get("id_token"),
        "access_token": tokens.get("access_token"),
    })
    logging.info("User logged in via Cognito")
    return redirect("/chat-ui")

@auth_bp.route("/logout")
def logout():
    cognito = current_app.config["COGNITO"]
    session.clear()
    return redirect(f"https://{cognito['domain']}/logout?client_id={cognito['client_id']}&logout_uri={cognito['logout']}")

