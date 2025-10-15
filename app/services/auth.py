from flask import Blueprint, current_app, redirect, request, session, jsonify
import base64
import requests
import logging


auth_bp = Blueprint("auth", __name__)


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
r = requests.post(f"https://{cognito['domain']}/oauth2/token", data=data, headers=headers, timeout=15)
r.raise_for_status()
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
